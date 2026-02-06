"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any
from utils.html import clean_html
from utils.logger import log
import re

# =========================================================
# FILTROS / CATEGORIAS
# =========================================================

# Terms to EXCLUDE
# Terms to EXCLUDE
BLACKLIST = [
    # merch / genéricos
    "t-shirt", "apparel", "hoodie", "jacket", "clothing", "fashion",
    "tcg", "card game", "board game", "cosplay",

    # esportes / futebol (ruído)
    "football", "soccer", "futebol", "fifa", "uefa",
    "champions league", "premier league", "la liga", "bundesliga",
    "libertadores", "world cup", "copa do mundo",

    # TV genérica / Reality / Séries não-anime
    "reality show", "reality tv", "netflix series", "live action series",
    "season finale", "now playing", "official teaser"
]

# Termos que GARANTEM que o conteúdo é "Anime-related"
STRICT_ANIME_KEYWORDS = [
    "anime", "animes", "manga", "mangas", "mangá", "mangás",
    "light novel", "visual novel", "otaku",
    "gundam", "ghibli", "shonen", "seinen", "shoujo", "josei",
    "isekai", "mecha", "tokusatsu", "chibi", "kawaii", "kaiju",

    # termos de “marca” que ajudam a ancorar no universo anime
    "crunchyroll", "aniplex", "kadokawa", "toho animation", "kyoani", "mappa",
    "ufotable", "wit studio", "bones", "production i.g", "science saru"
]

UNTRUSTED_SOURCES = [
    # Feeds genéricos que misturam games/filmes e precisam de filtro estrito
    "youtube.com/feeds/videos.xml?user=IGNentertainment",
    "youtube.com/feeds/videos.xml?user=Netflix",
    "youtube.com/feeds/videos.xml?user=NetflixJP",
    "youtube.com/feeds/videos.xml?channel_id=UCi4eH63_g45WyW6YqJVIWFA", # IGN Movie Trailers (exemplo) (usuario nao confirmou ID, mas boa pratica)
]

CAT_MAP = {
    "anime": [
        # termos realmente do ecossistema anime
        "anime", "animes",
        "manga", "mangas", "mangá", "mangás",
        "light novel", "visual novel",
        "pv", "trailer", "teaser", "ova", "ona", "special",
        "crunchyroll", "aniplex", "kadokawa",

        # REMOVIDO "netflix" daqui para não liberar automaticamente.
        # Se for Netflix, passará apenas se tiver STRICT kw (anime, manga...)
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
        "game", "rpg", "console", "pc", "ps5", "xbox", "nintendo", "switch", "mobile game", "visual novel"
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
    """Verifica se alguma keyword está presente no texto."""
    if not keywords:
        return ""

    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(' + '|'.join(escaped_kws) + r')s?\b'

    match = re.search(pattern_str, text, re.IGNORECASE)
    return match.group(1) if match else ""


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any], source: str = "") -> bool:
    """Decide se notícia deve ir para a guild."""
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])

    if not isinstance(filters, list) or not filters:
        return False

    content = f"{clean_html(title)} {clean_html(summary)}".lower()

    # Checa confiabilidade da fonte
    source_l = (source or "").lower()
    is_untrusted = any(u.lower() in source_l for u in UNTRUSTED_SOURCES)

    # 1. Bloqueia Blacklist
    blocked_word = _contains_any(content, BLACKLIST)
    if blocked_word:
        log.warning(f"🚫 [BLOCKED] Guild: {guild_id} | Filtro: BLACKLIST | Termo: '{blocked_word}' | Título: {title[:50]}...")
        return False

    # 2. "todos" = tudo relacionado a anime (exige termo estrito)
    if "todos" in filters:
        strict_match = _contains_any(content, STRICT_ANIME_KEYWORDS)

        # Regra de Ouro: Fonte Não Confiável EXIGE termo estrito
        if is_untrusted and not strict_match:
            log.debug(f"❌ [IGNORED] Fonte não confiável sem termo estrito | src={source[:30]}... | Título: {title[:50]}...")
            return False

        if not strict_match:
            log.debug(f"❌ [IGNORED] Guild: {guild_id} | TODOS ativo, mas sem termo estrito | Título: {title[:50]}...")
            return False

        log.info(f"✅ [ALLOWED] Guild: {guild_id} | Filtro: TODOS | Termo: '{strict_match}' | Título: {title[:50]}...")
        return True

    # 3. Verifica categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        matched_kw = _contains_any(content, kws)

        if matched_kw:
            # ✅ Regra: qualquer categoria “temática” precisa ter ao menos 1 termo estrito
            # Isso elimina séries/jogos/futebol que batem em palavras genéricas.
            # AGORA INCLUI "NEWS" PARA EVITAR "ANNOUNCEMENT" DE JOGOS NÃO-ANIME
            if f in ["anime", "news", "games", "filmes", "music", "musica"]:
                strict_match = _contains_any(content, STRICT_ANIME_KEYWORDS)
                if not strict_match:
                    log.debug(
                        f"⚠️ [FILTER-{f.upper()}] Ignorado pois não possui termo estrito de anime. "
                        f"Termo original: '{matched_kw}' | Título: {title[:50]}..."
                    )
                    continue

            log.info(f"✅ [ALLOWED] Guild: {guild_id} | Filtro: {f.upper()} | Termo: '{matched_kw}' | Título: {title[:50]}...")
            return True

    # Se chegou aqui, não passou em nenhum filtro
    log.debug(f"❌ [IGNORED] Guild: {guild_id} | Não houve match em filtros ativos ({filters}) | Título: {title[:50]}...")
    return False
