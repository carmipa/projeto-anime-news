"""
Translator utilities - Localization and Google Translate wrapper.
"""
import json
import logging
import asyncio
from collections import OrderedDict
from typing import Dict, Any, Optional
from deep_translator import GoogleTranslator

from utils.exceptions import TranslationError
from utils.storage import p, load_json_safe

log = logging.getLogger("AnimeBotIntel")

# Cache LRU em memória para traduções: evita rehit no Google Translate para
# textos repetidos (boilerplates de feed, mesmo item em varreduras distintas).
_TRANSLATION_CACHE: "OrderedDict[tuple, str]" = OrderedDict()
_TRANSLATION_CACHE_MAX = 2000

# Quantas vezes se publicou sem traduzir desde o arranque. Sem contador, esta degradação
# só apareceria no canal — que foi exatamente como o incidente do bot irmão foi descoberto.
_degradacoes_totais = 0

# Assinaturas do texto padrão das páginas de erro do Google. `!!1` é o marcador que todas
# carregam. Falso positivo aqui é barato — publica-se o texto original, sempre aceitável;
# falso negativo é que custa caro, e custou: notícia substituída por página de erro.
_ASSINATURAS_DE_PAGINA_DE_ERRO = (
    "!!1",
    "that's an error",
    "that’s an error",
    "that's all we know",
    "that’s all we know",
)


def _traducao_utilizavel(trad) -> bool:
    """
    PROPÓSITO DE NEGÓCIO: decidir se o que voltou do tradutor é mesmo uma tradução, e não
    uma página de erro travestida de sucesso.

    INVARIANTES DO DOMÍNIO: só devolve True para string não vazia sem assinatura de página
    de erro do Google. A busca é no texto inteiro e em minúsculas — a assinatura aparece no
    meio da página, não no começo.

    COMPORTAMENTO EM CASO DE FALHA: o que não for `str` (None, bytes, objeto do tradutor)
    devolve False, sem levantar. Recusar de mais é seguro: quem chama publica o original.
    """
    if not isinstance(trad, str):
        return False
    if not trad.strip():
        return False
    baixo = trad.lower()
    return not any(a in baixo for a in _ASSINATURAS_DE_PAGINA_DE_ERRO)


def degradacoes_totais() -> int:
    """Quantas publicações saíram sem tradução desde o arranque."""
    return _degradacoes_totais


def _reset_degradacoes() -> None:
    """Zera o contador e o cache. Existe para os testes não herdarem estado."""
    global _degradacoes_totais
    _degradacoes_totais = 0
    _TRANSLATION_CACHE.clear()


class Translator:
    """Gerencia traduções e localizações."""
    
    def __init__(self):
        self.translations: Dict[str, dict] = {}
        self.default_lang = 'en_US'
        self.supported_langs = ['en_US', 'pt_BR', 'es_ES', 'it_IT']
        self._load_all()
    
    def _load_all(self):
        """Carrega todos arquivos de tradução."""
        for lang in self.supported_langs:
            try:
                # Caminho: translations/en_US.json
                path = p(f"translations/{lang}.json")
                data = load_json_safe(path, {})
                if data:
                    self.translations[lang] = data
                    log.info(f"🌍 Tradução carregada: {lang}")
                else:
                    log.warning(f"⚠️ Tradução vazia ou não encontrada: {lang}")
            except Exception as e:
                log.error(f"Erro ao carregar tradução {lang}: {e}")

    def detect_lang(self, guild_id: str, guild_locale: str = None, guild_lang_map: dict = None) -> str:
        """
        Detecta idioma do servidor.
        Prioridade: 
        1. Mapa em memória (para evitar re-ler disco no hot path)
        2. Config manual (config.json)
        3. Locale do servidor Discord
        4. Padrão (en_US)
        """
        # 1. Config manual (memória)
        if guild_lang_map and guild_id in guild_lang_map:
            return guild_lang_map[guild_id]

        # 2. Config manual (disco)
        config = load_json_safe(p("config.json"), {})
        if guild_id in config and "language" in config[guild_id]:
            return config[guild_id]["language"]
        
        # 2. Locale do Discord (ex: 'pt-BR' -> 'pt_BR')
        if guild_locale:
            # Converte enum para string e normaliza
            locale_str = str(guild_locale)
            normalized = locale_str.replace('-', '_')
            
            if normalized in self.supported_langs:
                return normalized
            
            # Mapas específicos
            maps = {
                'en-GB': 'en_US',
                'es-419': 'es_ES',
                'pt-BR': 'pt_BR'
            }
            return maps.get(locale_str, self.default_lang)
            
        return self.default_lang

    def get(self, key: str, lang: str = 'en_US', **kwargs) -> str:
        """
        Obtém texto traduzido por chave (ex: 'commands.help.title').
        Suporta formatação com **kwargs.
        """
        if lang not in self.translations:
            lang = self.default_lang

        keys = key.split('.')
        value = self.translations.get(lang, {})
        
        try:
            for k in keys:
                value = value[k]
            
            if isinstance(value, str):
                return value.format(**kwargs)
            return str(value)
            
        except (KeyError, TypeError):
            # Tenta fallback para inglês
            if lang != self.default_lang:
                return self.get(key, lang=self.default_lang, **kwargs)
            return key

# Instância global
t = Translator()


async def translate_to_target(text: str, target_lang: str) -> str:
    """
    Traduz texto para idioma alvo usando Google Translate.
    target_lang: 'pt', 'en', 'es', 'it'
    """
    if not text:
        return ""

    # Mapeia códigos internos (pt_BR) para códigos Google (pt)
    google_map = {
        'pt_BR': 'pt',
        'en_US': 'en',
        'es_ES': 'es',
        'it_IT': 'it'
    }
    target = google_map.get(target_lang, 'en')

    # Cache hit: retorna sem chamar a rede
    cache_key = (target, text)
    cached = _TRANSLATION_CACHE.get(cache_key)
    if cached is not None:
        _TRANSLATION_CACHE.move_to_end(cache_key)
        return cached

    # O CONTRATO NÃO MUDA: esta função devolve a tradução OU o texto original, e nunca
    # levanta. Os chamadores em core/scanner.py usam o retorno direto para montar o embed;
    # propagar exceção daqui partiria a varredura. A `TranslationError` é levantada e
    # absorvida DENTRO desta fronteira — serve para nomear e registar a causa, não para a
    # empurrar para cima.
    global _degradacoes_totais
    try:
        try:
            loop = asyncio.get_running_loop()
            trad = await loop.run_in_executor(
                None,
                lambda: GoogleTranslator(source="auto", target=target).translate(text)
            )
        except Exception as e:
            raise TranslationError(
                "falha ao contactar o serviço de tradução",
                details={"erro": f"{type(e).__name__}: {e}", "idioma": target},
            ) from e

        if not _traducao_utilizavel(trad):
            # O DEFEITO PRINCIPAL, medido no bot irmão (projeto-bot-games) em 2026-08-30:
            # o `deep_translator` NÃO levanta quando o Google responde com página de erro —
            # devolve o TEXTO da página como se fosse a tradução. Este bloco tinha apenas
            # `if trad:`, que uma string de erro satisfaz. No bot irmão o resultado foi
            # notícias publicadas com título e resumo `Error 500 (Server Error)!!1...`, a
            # página de erro GRAVADA no cache, e o link marcado como enviado — a notícia
            # verdadeira nunca mais sairia.
            raise TranslationError(
                "resposta bem-sucedida com conteúdo de página de erro",
                details={"amostra": str(trad or "")[:120], "idioma": target},
            )
    except TranslationError as falha:
        # O motivo deixou de ser descartado. Antes era `except Exception as e: return text`
        # com o `e` capturado e NUNCA usado — a regra "nunca descartar o motivo de uma
        # rejeição" violada à letra, e a razão de a falha ser invisível.
        _degradacoes_totais += 1
        log.warning(
            "🌐 %s (%s). Publicando o texto original.",
            falha.message, falha.details,
        )
        return text

    # Só o que passou na validação é memorizado. Cachear inválido faria o erro repetir-se
    # para todo texto igual, mesmo depois de o serviço voltar ao normal.
    _TRANSLATION_CACHE[cache_key] = trad
    _TRANSLATION_CACHE.move_to_end(cache_key)
    if len(_TRANSLATION_CACHE) > _TRANSLATION_CACHE_MAX:
        _TRANSLATION_CACHE.popitem(last=False)
    return trad
