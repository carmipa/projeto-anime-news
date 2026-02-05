"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any
from utils.html import clean_html
from utils.logger import log  # GRC Logger
import re

# =========================================================
# FILTROS / CATEGORIAS
# =========================================================

# Terms to EXCLUDE (Clothing, Generic noise)
BLACKLIST = [
    "t-shirt", "apparel", "hoodie", "jacket", "clothing", "fashion",
    # "gunpla", "figure", "statue", "toy", "model kit", "ver.ka", "p-bandai", <-- Removed strict block on merch
    "tcg", "card game", "board game", "cosplay"
]

CAT_MAP = {
    "anime": [
        "anime", "film", "movie", "series", "season", "episode", 
        "pv", "trailer", "teaser", "ova", "ona", "special", 
        "streaming", "crunchyroll", "netflix"
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
        "gunpla", "gundam", "model kit", "ver.ka", "p-bandai", "hg", "mg", "pg", "rg", "robot spirits", "metal build"
    ],
    "games": [
        "game", "rpg", "console", "pc", "ps5", "xbox", "nintendo", "switch", "mobile game", "visual novel"
    ],
    "filmes": [
        "film", "movie", "live-action", "cinema", "theatrical"
    ]
}

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
    """
    Verifica se alguma keyword está presente no texto.
    Retorna a keyword encontrada ou String vazia.
    """
    if not keywords:
        return ""

    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(' + '|'.join(escaped_kws) + r')s?\b'
    
    match = re.search(pattern_str, text, re.IGNORECASE)
    return match.group(1) if match else ""


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any]) -> bool:
    """
    Decide se notícia deve ir para a guild.
    
    Returns: True se aprovado.
    """
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])

    if not isinstance(filters, list) or not filters:
        # log.debug(f"Guild {guild_id} sem filtros configurados.")
        return False

    content = f"{clean_html(title)} {clean_html(summary)}".lower()

    # 1. Bloqueia Blacklist
    blocked_word = _contains_any(content, BLACKLIST)
    if blocked_word:
        log.warning(f"🚫 [BLOCKED] Guild: {guild_id} | Filtro: BLACKLIST | Termo: '{blocked_word}' | Título: {title[:50]}...")
        return False

    # 2. "todos" libera tudo
    if "todos" in filters:
        log.info(f"✅ [ALLOWED] Guild: {guild_id} | Filtro: TODOS | Título: {title[:50]}...")
        return True

    # 3. Verifica categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        matched_kw = _contains_any(content, kws)
        
        if matched_kw:
            # Lógica Especial: GAMES ou FILMES apenas se tiver relação com ANIME
            if f in ["games", "filmes"]:
                anime_kws = CAT_MAP.get("anime", [])
                if not _contains_any(content, anime_kws):
                     log.debug(f"⚠️ [FILTER-{f.upper()}] Ignorado pois não possui termo de anime. Título: {title[:30]}...")
                     continue
            
            log.info(f"✅ [ALLOWED] Guild: {guild_id} | Filtro: {f.upper()} | Termo: '{matched_kw}' | Título: {title[:50]}...")
            return True

    # Se chegou aqui, não passou em nenhum filtro
    log.debug(f"❌ [IGNORED] Guild: {guild_id} | Não houve match em filtros ativos ({filters}) | Título: {title[:50]}...")
    return False
