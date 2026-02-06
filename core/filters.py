"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any
from utils.html import clean_html
from utils.logger import log
import re
from urllib.parse import urlparse

# =========================================================
# FILTROS / CATEGORIAS
# =========================================================

# Terms to EXCLUDE (globais)
BLACKLIST = [
    # merch / genéricos
    "t-shirt", "apparel", "hoodie", "jacket", "clothing", "fashion",
    "tcg", "card game", "board game", "cosplay",

    # esportes / futebol (ruído)
    "football", "soccer", "futebol", "fifa", "uefa",
    "champions league", "premier league", "la liga", "bundesliga",
    "libertadores", "world cup", "copa do mundo",

    # TV genérica / Reality / Séries não-anime (genérico)
    "reality show", "reality tv",
    "live action series",
    "season finale", "now playing",
]

# Termos que GARANTEM que o conteúdo é "Anime-related"
STRICT_ANIME_KEYWORDS = [
    "anime", "animes", "manga", "mangas", "mangá", "mangás",
    "light novel", "visual novel", "otaku",
    "gundam", "ghibli", "shonen", "seinen", "shoujo", "josei",
    "isekai", "mecha", "tokusatsu", "chibi", "kawaii", "kaiju",

    # marcas/estúdios/distribuidores (âncoras fortes)
    "crunchyroll", "aniplex", "kadokawa", "toho animation", "kyoani", "mappa",
    "ufotable", "wit studio", "bones", "production i.g", "science saru",
]

# Hints para fontes "mistas" (YouTube genérico / streaming / agregadores)
# IMPORTANTE: usar pedaços do URL para bater independente de http/https e www.
UNTRUSTED_SOURCE_HINTS = [
    "youtube.com/feeds/videos.xml?user=ignentertainment",
    "youtube.com/feeds/videos.xml?user=netflix",
    "youtube.com/feeds/videos.xml?user=netflixjp",
    # Se você quiser incluir outros agregadores aqui, faça por domínio/trecho do feed:
    # "example.com/feed",
]

# Bloqueios adicionais SOMENTE quando a fonte é "untrusted"
# Aqui entram sinais de trailer/teaser de série/filme live-action etc.
UNTRUSTED_BLACKLIST = [
    "official teaser",
    "official trailer",
    "season ",
    " part ",
    "bridgerton",
    "fast and furious",
    "hollywood drift",
    "netflix series",
]

CAT_MAP = {
    "anime": [
        # termos realmente do ecossistema anime
        "anime", "animes",
        "manga", "mangas", "mangá", "mangás",
        "light novel", "visual novel",
        "pv", "trailer", "teaser", "ova", "ona", "special",
        "crunchyroll", "aniplex", "kadokawa",
        # "netflix" removido de propósito: Netflix só passa se tiver termo estrito.
    ],
    "news": [
        "news", "update", "announcement", "report", "interview",
        "production", "cast", "staff", "studio"
    ],
    "music": [
        "music", "ost", "soundtrack", "opening", "ending",
        "theme song", "op", "ed", "singer", "concert"
    ],
    "gunpla": [
        "gunpla", "gundam", "model kit", "ver.ka", "p-bandai", "hg", "mg", "pg", "rg",
        "robot spirits", "metal build"
    ],
    "games": [
        "game", "rpg", "console", "pc", "ps5", "xbox", "nintendo", "switch",
        "mobile game", "visual novel"
    ],
    "filmes": [
        "film", "movie", "live-action", "cinema", "theatrical"
    ]
}

# Alias para compatibilidade pt-br na config.json
CAT_MAP["musica"] = CAT_MAP["music"]

FILTER_OPTIONS = {
    "todos": ("TUDO", "🌟"),
    "anime": ("Anime", "🎬"),
    "news": ("News", "📰"),
    "music": ("Music", "🎵"),
    "gunpla": ("Gunpla", "🤖"),
    "games": ("Games", "🎮"),
    "filmes": ("Filmes", "🎥"),
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _contains_any(text: str, keywords: List[str]) -> str:
    """Verifica se alguma keyword está presente no texto.
    Retorna a keyword que bateu (ou "" se não bateu).
    """
    if not keywords:
        return ""

    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(' + '|'.join(escaped_kws) + r')s?\b'
    match = re.search(pattern_str, text, re.IGNORECASE)
    return match.group(1) if match else ""


def _is_untrusted_source(source: str) -> bool:
    """Determina se a fonte é 'mista' (precisa de regras extras)."""
    source_l = (source or "").lower()
    if not source_l:
        return False

    # Bate por hints (trechos do URL do feed)
    if any(h in source_l for h in UNTRUSTED_SOURCE_HINTS):
        return True

    # Heurística extra: YouTube + certas palavras-chave no próprio URL do feed
    # (evita depender do formato exato)
    host = urlparse(source_l).netloc
    if host in ("www.youtube.com", "youtube.com"):
        if "user=netflix" in source_l or "user=netflixjp" in source_l or "user=ignentertainment" in source_l:
            return True

    return False


# =========================================================
# MAIN MATCH LOGIC
# =========================================================

def match_intel(
    guild_id: str,
    title: str,
    summary: str,
    config: Dict[str, Any],
    source: str = ""
) -> bool:
    """Decide se notícia deve ir para a guild."""
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])

    if not isinstance(filters, list) or not filters:
        return False

    content = f"{clean_html(title)} {clean_html(summary)}".lower()

    is_untrusted = _is_untrusted_source(source)

    # 1) Blacklist global (sempre bloqueia)
    blocked_word = _contains_any(content, BLACKLIST)
    if blocked_word:
        log.warning(
            f"🚫 [BLOCKED] Guild: {guild_id} | Filtro: BLACKLIST | Termo: '{blocked_word}' | Título: {title[:50]}..."
        )
        return False

    # 2) Blacklist extra SOMENTE para fontes untrusted (não mata trailer bom de fonte confiável)
    if is_untrusted:
        bad = _contains_any(content, UNTRUSTED_BLACKLIST)
        if bad:
            log.warning(
                f"🚫 [BLOCKED] Guild: {guild_id} | Filtro: UNTRUSTED_BLACKLIST | Termo: '{bad}' "
                f"| Src: {source[:60]}... | Título: {title[:50]}..."
            )
            return False

    # 3) "todos" = tudo RELACIONADO A ANIME (exige termo estrito)
    if "todos" in filters:
        strict_match = _contains_any(content, STRICT_ANIME_KEYWORDS)
        if not strict_match:
            log.debug(
                f"❌ [IGNORED] Guild: {guild_id} | TODOS ativo, mas sem termo estrito | Título: {title[:50]}..."
            )
            return False

        log.info(
            f"✅ [ALLOWED] Guild: {guild_id} | Filtro: TODOS | Termo: '{strict_match}' | Título: {title[:50]}..."
        )
        return True

    # 4) Categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        matched_kw = _contains_any(content, kws)

        if matched_kw:
            # Regra: categorias temáticas precisam ter ao menos 1 termo estrito
            # (inclui news para evitar "announcement" de coisas fora do universo anime)
            if f in ["anime", "news", "games", "filmes", "music", "musica"]:
                strict_match = _contains_any(content, STRICT_ANIME_KEYWORDS)
                if not strict_match:
                    log.debug(
                        f"⚠️ [FILTER-{f.upper()}] Ignorado pois não possui termo estrito de anime. "
                        f"Termo original: '{matched_kw}' | Título: {title[:50]}..."
                    )
                    continue

            log.info(
                f"✅ [ALLOWED] Guild: {guild_id} | Filtro: {f.upper()} | Termo: '{matched_kw}' | Título: {title[:50]}..."
            )
            return True

    log.debug(
        f"❌ [IGNORED] Guild: {guild_id} | Não houve match em filtros ativos ({filters}) | Título: {title[:50]}..."
    )
    return False
