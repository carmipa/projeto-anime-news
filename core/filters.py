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

    # esportes / entretenimento genérico (ruído)
    "futebol", "fifa", "uefa",
    "champions league", "premier league", "la liga", "bundesliga",
    "libertadores", "world cup", "copa do mundo",
    "vôlei", "beisebol", "野球", "ベースボール", "サッカー",
    "world baseball classic", "clássico mundial de beisebol", "clássico mundial",
    "samurai japan", "serv japan", "侍ジャパン", "ワールドベースボールクラシック",
    "world baseball", "baseball classic", "beisebol clássico",

    # TV genérica / Reality / Séries não-anime (genérico)
    "reality show", "reality tv", "variety show",
    "live action series", "set tour",
    "season finale", "now playing",
    "twice", "timelesz", "k-pop", "j-pop",
    "grwm", "get ready with me", "green room", "tour",
    "this is i", "este sou eu", "o namorado", "the boyfriend",
    "netflix japan", "netflix japão", "netflix série", "netflix series",
]

# Termos que GARANTEM que o conteúdo é "Anime-related"
STRICT_ANIME_KEYWORDS = [
    "anime", "animes", "manga", "mangas", "mangá", "mangás",
    "light novel", "visual novel", "otaku",
    "gundam", "ghibli", "shonen", "seinen", "shoujo", "josei",
    "isekai", "mecha", "chibi", "kawaii", "kaiju",

    # marcas/estúdios/distribuidores (âncoras fortes)
    "crunchyroll", "aniplex", "kadokawa", "toho animation", "kyoani", "mappa",
    "ufotable", "wit studio", "bones", "production i.g", "science saru",

    # títulos/padrões comuns que confirmam anime
    "spy x family", "spyxfamily", "spy×family", "spy-family", "jujutsu kaisen", "shingeki", "one piece", "naruto",
    "pv", "key visual", "teaser trailer",
]

# Hints para fontes "mistas" (YouTube genérico / streaming / agregadores)
# IMPORTANTE: usar pedaços do URL para bater independente de http/https e www.
UNTRUSTED_SOURCE_HINTS = [
    "user=ignentertainment",
    "user=netflix",
    "user=netflixjp",
    "channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", # Netflix Japan
    "channel_id=UClp1Q_Ui80Wf69A6YI67S3w", # Netflix
    "channel_id=UC0-5Baz14QkUcJ6fAYAkbAQ", # Sato Company
    "channel_id=UCivtAzCENYI1jb6Clxydvdw", # TokuSato
    "channel_id=UCTOaq4HfNMstuJfZxHszxgw", # Sato Anime
]

# Bloqueios adicionais SOMENTE quando a fonte é "untrusted"
# Aqui entram sinais de trailer/teaser de série/filme live-action etc.
UNTRUSTED_BLACKLIST = [
    "official teaser",
    "official trailer",
    "bridgerton",
    "fast and furious",
    "hollywood drift",
    "netflix series",
    "netflix japan",
    "netflix japão",
    "netflix reality",
    "kokuho",
    "dollhouse",
    "the boyfriend",
    "o namorado",
    "this is i",
    "este sou eu",
    "green room",
    "grwm",
    "set tour",
    "behind the scenes",
    "canção de torcida",
    "song",
    "manager",
    "pressão",
    "circunstâncias",
    "circumstances",
    "情事",
    "事情",
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
    Usa busca case-insensitive e suporta caracteres especiais.
    """
    if not keywords:
        return ""

    text_lower = text.lower()
    
    # Primeiro tenta com regex para palavras completas (quando possível)
    for kw in keywords:
        kw_lower = kw.lower()
        # Para palavras simples, usa word boundaries
        if kw_lower.replace(" ", "").replace("-", "").isalnum():
            pattern = r'\b' + re.escape(kw_lower) + r's?\b'
            if re.search(pattern, text_lower, re.IGNORECASE):
                return kw
        # Para frases ou termos com caracteres especiais, usa busca simples
        elif kw_lower in text_lower:
            return kw
    
    return ""


def _is_untrusted_source(source: str) -> bool:
    """Determina se a fonte é 'mista' (precisa de regras extras)."""
    source_l = (source or "").lower()
    if not source_l:
        return False

    # Bate por hints (trechos do URL do feed)
    if any(h.lower() in source_l for h in UNTRUSTED_SOURCE_HINTS):
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
    title_clean = clean_html(title).lower()
    summary_clean = clean_html(summary).lower()
    content = f"{title_clean} {summary_clean}"

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

    # 3) "todos" = tudo RELACIONADO A ANIME
    if "todos" in filters:
        # Para fontes untrusted, exigimos que o termo estrito esteja no TÍTULO
        # Isso evita falsos positivos por conta de boilerplates no resumo/descrição.
        check_text = title_clean if is_untrusted else content
        strict_match = _contains_any(check_text, STRICT_ANIME_KEYWORDS)
        
        if not strict_match:
            log.debug(
                f"❌ [IGNORED] Guild: {guild_id} | {'(UNTRUSTED)' if is_untrusted else 'TODOS'} "
                f"Sem termo estrito no {'TÍTULO' if is_untrusted else 'conteúdo'} | Título: {title[:50]}..."
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
                check_text = title_clean if is_untrusted else content
                strict_match = _contains_any(check_text, STRICT_ANIME_KEYWORDS)
                
                if not strict_match:
                    log.debug(
                        f"⚠️ [FILTER-{f.upper()}] Ignorado pois não possui termo estrito no "
                        f"{'TÍTULO' if is_untrusted else 'conteúdo'}. "
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
