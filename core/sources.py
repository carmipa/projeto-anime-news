"""
Sources module - Carregamento e metadados das fontes de notícias.

Separado de core/scanner.py para que core/filters.py possa consultar os metadados
de uma fonte sem importar o scanner (que já importa os filtros).
"""
import os
from typing import Any, Dict, List

from utils.storage import p, load_json_safe

# Chaves aceitas no objeto de uma fonte dentro de sources.json.
_META_KEYS = ("name", "untrusted", "enabled", "note", "user_agent")

# User-Agent de navegador, usado só onde a fonte o exige.
# NÃO é o padrão de propósito: a Comic Natalie responde 405 a UA de navegador e
# 200 sem nenhum, enquanto a animeanime.jp faz exatamente o contrário. Não
# existe um UA que sirva as duas — por isso é decisão por fonte.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Cache do cadastro: o filtro consulta os metadados uma vez por item POR GUILD,
# logo reler o ficheiro a cada chamada faria I/O no caminho quente. Invalida
# sozinho quando o sources.json muda de mtime/tamanho.
_CACHE: Dict[str, Dict[str, Any]] | None = None
_CACHE_STAMP: tuple | None = None


def _file_stamp(path: str) -> tuple:
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def _iter_entries(data: Any):
    """Percorre sources.json e devolve cada entrada bruta (str ou dict)."""
    containers: List[Any]
    if isinstance(data, dict):
        containers = list(data.values())
    elif isinstance(data, list):
        containers = [data]
    else:
        return

    for category in containers:
        if isinstance(category, dict):
            for subcat in category.values():
                if isinstance(subcat, list):
                    yield from subcat
        elif isinstance(category, list):
            yield from category


def _normalize(entry: Any) -> Dict[str, Any] | None:
    """Converte uma entrada (string legada ou objeto) no dicionário de metadados."""
    if isinstance(entry, str):
        url = entry.strip()
        return {"url": url, "name": "", "untrusted": False, "enabled": True, "note": ""} if url else None

    if isinstance(entry, dict):
        url = str(entry.get("url", "")).strip()
        if not url:
            return None
        meta = {"url": url, "name": "", "untrusted": False, "enabled": True,
                "note": "", "user_agent": ""}
        for k in _META_KEYS:
            if k in entry:
                meta[k] = entry[k]
        meta["untrusted"] = bool(meta["untrusted"])
        meta["enabled"] = bool(meta["enabled"])
        # "browser" é atalho para o UA de navegador; qualquer outro texto é
        # usado tal e qual, para o caso de uma fonte exigir algo específico.
        if str(meta["user_agent"]).strip().lower() == "browser":
            meta["user_agent"] = BROWSER_USER_AGENT
        return meta

    return None


def load_source_meta() -> Dict[str, Dict[str, Any]]:
    """
    PROPÓSITO DE NEGÓCIO: devolve o cadastro completo de cada fonte (nome real do
    canal, se é fonte mista, se está ativa) para que o filtro decida pelo cadastro
    e não por adivinhação sobre o texto da URL. O nome real é o que impede um
    estúdio de anime de ser tratado como canal de games por engano.

    INVARIANTES DO DOMÍNIO:
    - Aceita os dois formatos: string solta (legado) e objeto com metadados.
    - Uma URL repetida em categorias diferentes aparece uma única vez; vence a
      PRIMEIRA ocorrência, para que a ordem do ficheiro seja a fonte da verdade.
    - Fonte sem metadados é confiável e ativa por omissão (comportamento legado).

    COMPORTAMENTO EM CASO DE FALHA: ficheiro ausente, vazio ou corrompido devolve
    dicionário vazio (o `load_json_safe` já loga o motivo); entrada sem `url` ou
    de tipo inesperado é ignorada em silêncio, sem derrubar a varredura.
    """
    global _CACHE, _CACHE_STAMP

    path = p("sources.json")
    stamp = _file_stamp(path)
    if _CACHE is not None and _CACHE_STAMP == stamp:
        return _CACHE

    data = load_json_safe(path, {})
    out: Dict[str, Dict[str, Any]] = {}
    for entry in _iter_entries(data):
        meta = _normalize(entry)
        if meta and meta["url"] not in out:
            out[meta["url"]] = meta

    _CACHE, _CACHE_STAMP = out, stamp
    return out


def load_sources() -> List[str]:
    """
    PROPÓSITO DE NEGÓCIO: lista plana das URLs que a varredura deve buscar nesta
    rodada — a entrada de todo o pipeline de notícias.

    INVARIANTES DO DOMÍNIO:
    - Só devolve fontes com `enabled: true` (uma fonte desativada não é buscada).
    - Sem duplicados e preservando a ordem de declaração no ficheiro.

    COMPORTAMENTO EM CASO DE FALHA: devolve lista vazia se `sources.json` não
    puder ser lido; quem chama já trata "nenhuma fonte" como aviso de configuração.
    """
    return [url for url, meta in load_source_meta().items() if meta["enabled"]]


def source_name(url: str) -> str:
    """Nome legível da fonte (vazio se não cadastrado)."""
    return load_source_meta().get(url, {}).get("name", "")


def source_headers(url: str) -> Dict[str, str]:
    """
    PROPÓSITO DE NEGÓCIO: devolver os cabeçalhos HTTP que ESTA fonte exige.
    Sem isto, fonte viva fica inacessível por um detalhe de User-Agent.

    INVARIANTES DO DOMÍNIO:
    - Por omissão não manda User-Agent nenhum (comportamento histórico do bot,
      e o que faz a Comic Natalie responder 200 em vez de 405).
    - Só manda UA quando a fonte o pede explicitamente no cadastro — medido
      caso a caso, nunca por suposição.

    COMPORTAMENTO EM CASO DE FALHA: fonte não cadastrada ou cadastro ilegível
    devolve dicionário vazio; nunca levanta.
    """
    ua = load_source_meta().get(url, {}).get("user_agent", "")
    return {"User-Agent": ua} if ua else {}
