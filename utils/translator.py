"""
Translator utilities - localização das strings de UI (translations/*.json).

PROPÓSITO DE NEGÓCIO:
    Fornecer os textos da própria interface do bot (autor e rodapé do embed) no
    idioma do servidor. NÃO traduz o conteúdo das notícias.

    A tradução AUTOMÁTICA do conteúdo (via Google Translate / deep_translator) foi
    REMOVIDA em 2026-08-30: o serviço devolvia página de erro (`Error 500 …!!1`) para
    o IP da VPS como se fosse tradução, degradando publicações em silêncio. As
    notícias passam a sair no idioma ORIGINAL. Se um dia se quiser tradução, o
    caminho decidido pelo Paulo é um botão sob demanda, não a automática.

INVARIANTES DO DOMÍNIO:
    - `get` sempre devolve uma string: a tradução da chave, o fallback em inglês, ou
      a própria chave — nunca levanta por chave ausente.
    - Idiomas suportados: en_US, pt_BR, es_ES, it_IT; padrão en_US.

COMPORTAMENTO EM CASO DE FALHA:
    Arquivo de tradução ausente/corrompido é logado e o idioma fica sem entradas;
    `get` cai no fallback en_US e, por fim, na própria chave.
"""
import logging
from typing import Dict

from utils.storage import p, load_json_safe

log = logging.getLogger("AnimeBotIntel")


class Translator:
    """Gerencia a localização das strings de UI."""

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

        # 3. Locale do Discord (ex: 'pt-BR' -> 'pt_BR')
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
