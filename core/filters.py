"""
Filters module - News filtering and categorization logic.
"""
from typing import Dict, List, Any
from utils.html import clean_html
import re

# =========================================================
# FILTROS / CATEGORIAS
# =========================================================

# Terms to EXCLUDE (Video Games, Toys, Clothing)
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

def _contains_any(text: str, keywords: List[str]) -> bool:
    """
    Verifica se alguma keyword está presente no texto usando Regex.
    
    Usa word boundaries (\b) para evitar matches parciais.
    Suporta plural opcional ('s?').
    
    Args:
        text: Texto a verificar (já em lowercase)
        keywords: Lista de palavras-chave (em lowercase)
    
    Returns:
        True se pelo menos uma keyword foi encontrada
    """
    if not keywords:
        return False

    # Escapa keywords para segurança no regex
    # Monta padrão: (?<!:)\b(?:kw1|kw2|...|kwn)s?\b
    escaped_kws = [re.escape(k) for k in keywords]
    pattern_str = r'(?<!:)\b(?:' + '|'.join(escaped_kws) + r')s?\b'
    
    return bool(re.search(pattern_str, text))


def match_intel(guild_id: str, title: str, summary: str, config: Dict[str, Any]) -> bool:
    """
    Decide se notícia deve ir para a guild.
    
    Lógica:
      1. Junta title + summary
      2. Bloqueia se tiver termo da BLACKLIST (Games, Merch, etc)
      3. Se filtro 'todos' ativo -> Aprova
      4. Se categorias específicas ativas -> Verifica keywords
    
    Args:
        guild_id: ID da guild
        title: Título da notícia
        summary: Resumo da notícia
        config: Configuração carregada
    
    Returns:
        True se notícia deve ser postada
    """
    g = config.get(str(guild_id), {})
    filters = g.get("filters", [])

    if not isinstance(filters, list) or not filters:
        return False

    content = f"{clean_html(title)} {clean_html(summary)}".lower()

    # 1. Bloqueia Blacklist (Games, Toys, Merch)
    if _contains_any(content, BLACKLIST):
        return False

    # 2. "todos" libera tudo (que não seja blacklist)
    if "todos" in filters:
        return True

    # 3. Verifica categorias específicas
    for f in filters:
        kws = CAT_MAP.get(f, [])
        if kws and _contains_any(content, kws):
            return True

    return False
