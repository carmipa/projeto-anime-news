"""
Filters module - Filtragem de notícias para garantir APENAS conteúdo de anime.

Objetivo: só aprovar itens que sejam claramente notícias/novidades de anime, manga,
estúdios ou distribuidoras de anime. Bloquear séries live-action, reality, esportes,
e qualquer conteúdo que não seja do universo anime.
"""
from typing import Dict, List, Any, Tuple
from core.sources import load_source_meta
from utils.html import clean_html
from utils.logger import log
import re
from urllib.parse import urlparse

# =========================================================
# FILTROS / CATEGORIAS
# =========================================================

# Terms to EXCLUDE (globais)
BLACKLIST = [
    # roupas
    "t-shirt", "apparel", "hoodie", "jacket", "clothing", "fashion",
    # "board game" removido: falsos positivos (ex.: trailer de jogos de tabuleiro)
    "tcg", "card game", "cosplay",

    # esportes / entretenimento genérico (ruído)
    "futebol", "fifa", "uefa",
    "champions league", "premier league", "la liga", "bundesliga",
    "libertadores", "world cup", "copa do mundo",
    "vôlei", "beisebol", "野球", "ベースボール", "サッカー",
    "world baseball classic", "clássico mundial de beisebol", "clássico mundial",
    "samurai japan", "serv japan", "侍ジャパン", "ワールドベースボールクラシック",
    "world baseball", "baseball classic", "beisebol clássico",

    # TV genérica / Reality / Séries não-anime / Live Action
    "reality show", "reality tv", "variety show",
    "live action series", "live action", "live-action", "ação ao vivo",
    "still watching netflix",
    "the anime effect",
    # "gameplay" cru (era "gameplay trailer", que não apanhava "gameplay
    # reveal"/"gameplay footage"): vídeo de jogabilidade não é notícia de anime,
    # mesmo quando o jogo usa um IP de anime. Notícia de "anime baseado em
    # jogo" continua a passar — não diz "gameplay" no título.
    "gameplay",
    # overview trailer / gameplay overview: falsos positivos em jogos com IP de anime (ex. Arknights)
    "season finale",
    "twice", "timelesz", "k-pop", "j-pop",
    "grwm", "get ready with me", "green room",
    "this is i", "este sou eu", "o namorado", "the boyfriend", "namorado mensal",
    "diamond truth", "peaky blinders", "love is blind", "casamento às cegas",
    "documentary", "documentário", "docuseries", "série documental",
    # "netflix japan/japão" removido: bloqueava clips oficiais de anime (ONE PIECE, etc.) no canal Netflix JP
    "netflix série", "netflix series",
]

# Bloqueios avaliados SÓ NO TÍTULO.
#
# A BLACKLIST acima olha título + resumo, e para descrição de vídeo isso é uma
# armadilha: quase todo canal oficial cola no rodapé da descrição um "check our
# merch store" ou "tour dates". Medido: com "merchandise" na lista global, 10
# episódios legítimos da Muse Asia (One-Punch Man, Iruma-kun, Rilakkuma...)
# foram bloqueados pelo boilerplate da descrição, e "tour" derrubou mais um.
# Anúncio de merch de verdade diz isso no TÍTULO — é onde se decide.
BLACKLIST_TITULO = [
    "figure", "figuarts", "nendoroid", "nendoroide", "figma", "prize figure",
    "statue", "estátua", "action figure", "boneco", "doll", "diorama",
    "model kit", "plamo", "gunpla", "collectible", "colecionável",
    "merchandise", "merch", "keychain", "chaveiro", "pelúcia", "plushie",
    "tour",
]

# Termos que GARANTEM que o conteúdo é "Anime-related".
# Só entra aqui termo que, sozinho, prove o assunto. "trailer" e "episode" NÃO
# entram: existem em qualquer mídia. Termos japoneses são casados por substring
# (ver _matcher_for), por isso podem aparecer colados no meio da frase.
STRICT_ANIME_KEYWORDS = [
    "anime", "animes", "manga", "mangas", "mangá", "mangás",
    "light novel", "visual novel", "otaku",
    "ghibli", "shonen", "seinen", "shoujo", "josei",
    "isekai", "mecha", "chibi", "kawaii", "kaiju",
    "simulcast", "dublagem japonesa", "seiyuu",

    # japonês: sem estes o feed dos estúdios oficiais quase nunca casa.
    # 放送/配信 (transmissão/streaming) ficaram DE FORA de propósito: são
    # genéricos e deixariam passar dorama do Netflix Japan, que é fonte mista.
    "アニメ", "劇場版", "アニメ化", "声優", "原作",
    "第1話", "最終話", "主題歌", "キービジュアル", "ティザー",
    "漫画", "マンガ", "コミック", "ライトノベル", "ノベライズ",
    "テレビアニメ", "オリジナルアニメ", "アニメーション",

    # marcas/estúdios/distribuidores (âncoras fortes)
    "crunchyroll", "aniplex", "kadokawa", "toho animation", "kyoani", "mappa",
    "ufotable", "wit studio", "bones", "production i.g", "science saru",
    "cloverworks", "madhouse", "trigger studio", "studio trigger", "pierrot",
    "shueisha", "shonen jump", "muse asia", "ani-one", "hidive",
    "toei animation", "a-1 pictures", "pony canyon", "funimation",
    "集英社", "講談社", "小学館", "東映アニメーション", "サンライズ",

    # títulos/padrões comuns que confirmam anime
    "spy x family", "spyxfamily", "spy×family", "spy-family", "jujutsu kaisen", "shingeki",
    "one piece", "ワンピース", "naruto", "boruto", "bleach", "dragon ball",
    "demon slayer", "kimetsu", "鬼滅の刃", "chainsaw man", "チェンソーマン",
    "frieren", "フリーレン", "dandadan", "ダンダダン", "solo leveling",
    "attack on titan", "進撃の巨人", "my hero academia", "僕のヒーローアカデミア",
    "hunter x hunter", "sailor moon", "evangelion", "エヴァンゲリオン",
    "gundam", "ガンダム", "pokémon", "pokemon", "ポケモン", "digimon",
    "sakamoto days", "oshi no ko", "推しの子", "blue lock", "ブルーロック",
    "re:zero", "リゼロ", "overlord", "konosuba", "この素晴らしい",
    "pv", "key visual",
]

# Fontes "mistas" (streaming genérico, imprensa de games, canais de música):
# quem manda é o campo `untrusted` de cada fonte no sources.json.
#
# Esta lista é só a REDE DE SEGURANÇA para URL que não esteja cadastrada — por
# isso guarda apenas padrões de domínio/host, nunca channel_id. Marcar canal por
# channel_id aqui foi o que pôs TOHO animation, WIT STUDIO, KADOKAWAanime e
# Crunchyroll na cesta dos "mistos" (os comentários dos IDs estavam trocados),
# enquanto "ign"/"gametrailers" não pegavam nada: a URL desses feeds só tem o
# channel_id, não o nome do canal.
UNTRUSTED_SOURCE_HINTS = [
    "user=ignentertainment",
    "user=netflix",
    "user=netflixjp",
    "//ign.com", ".ign.com",
    "//gametrailers.com", ".gametrailers.com",
]

# Bloqueios adicionais SOMENTE quando a fonte é "untrusted"
# Aqui entram sinais de trailer/teaser de série/filme live-action etc.
UNTRUSTED_BLACKLIST = [
    "kokuho",
    "dollhouse",
    "the boyfriend",
    "o namorado",
    "this is i",
    "este sou eu",
    "green room",
    "grwm",
    "set tour",
    "canção de torcida",
    "song",
    "manager",
    "pressão",
    "circunstâncias",
    "circumstances",
    "情事",
    "事情",
    # Não usar "cast", "behind the scenes", "interview" etc.: PVs e docs de anime
    # usam esses termos; a API do Discord não permite mailto em botões e o filtro
    # estrito no título já reduz lixo em fontes untrusted.
    # Ronnie the Hawk e similares (live-action Netflix Japan)
    "ronnie the hawk",
    "ronnie hawkins",
    "ロニー・ザ・ホーク",
    "ロニー・ホーキン",
    # Netflix Brasil: promo/variedade (não notícia de anime)
    "pepita",
    "o povo fala",
]

# Termos que dizem a que CATEGORIA um item pertence.
#
# Podem ser generosos: depois de casar categoria, o item ainda tem de passar
# pelo termo estrito de anime. Ser generoso aqui é seguro; ser pobre é caro —
# com só termos latinos, 53 itens de estúdios japoneses por dia caíam em
# "nenhuma categoria" e desapareciam mesmo tendo アニメ no título.
CAT_MAP = {
    "anime": [
        # termos realmente do ecossistema anime
        "anime", "animes",
        "manga", "mangas", "mangá", "mangás",
        "light novel", "visual novel",
        "pv", "trailer", "teaser", "ova", "ona", "special",
        "crunchyroll", "aniplex", "kadokawa",
        # japonês (casado por substring)
        # "第"/"話" ficaram de fora: casariam 電話/会話 e não trazem item novo
        # nenhum (quem só tem 第N話 no título não passa no termo estrito).
        "アニメ", "テレビアニメ", "アニメーション", "劇場版",
        "声優", "放送", "配信", "漫画", "マンガ", "コミック", "原作",
        "キャラクター", "ビジュアル", "予告", "公開",
        # "netflix" removido de propósito: Netflix só passa se tiver termo estrito.
    ],
    "news": [
        "news", "update", "announcement", "report",
        "production", "studio",
        "ニュース", "発表", "情報", "解禁", "決定", "速報",
    ],
    "music": [
        "music", "ost", "soundtrack", "opening", "ending",
        "theme song", "op", "ed", "singer", "concert",
        "主題歌", "音楽", "挿入歌", "ライブ", "オープニング", "エンディング",
    ],
    "games": [
        "game", "rpg", "console", "pc", "ps5", "xbox", "nintendo", "switch",
        "mobile game", "visual novel",
        "ゲーム", "アプリ", "スマホゲーム",
    ],
    "filmes": [
        "film", "movie", "cinema", "theatrical", "anime film", "anime movie",
        "映画", "劇場", "上映", "劇場公開",
    ]
}

# Nomes antigos de categoria que ainda vivem em config.json de servidores
# configurados antes das renomeações. Sem tradução, `CAT_MAP.get(nome, [])`
# devolve lista vazia e o filtro rejeita TUDO em silêncio — filtro sem keywords
# é indistinguível de "nada casou". O log de 2026-02 deste bot ainda mostra
# `Filtro: GUNPLA`, categoria que já não existe.
LEGACY_FILTER_ALIASES = {
    "musica": "music",
    "música": "music",
    "filme": "filmes",
    "movies": "filmes",
    "noticias": "news",
    "notícias": "news",
    "gunpla": "anime",   # herdado do bot de Gundam; aqui merch não é categoria
}


def normalize_filters(filters: List[str]) -> List[str]:
    """
    PROPÓSITO DE NEGÓCIO: traduzir nomes de categoria antigos para os atuais,
    para que um servidor configurado há meses continue a receber notícias em
    vez de emudecer sem aviso.

    INVARIANTES DO DOMÍNIO:
    - Preserva a ordem e não duplica.
    - Nome desconhecido é descartado (não vira categoria fantasma).

    COMPORTAMENTO EM CASO DE FALHA: entrada que não seja lista devolve lista
    vazia — o chamador já trata "sem filtros" como "não publicar nada".
    """
    if not isinstance(filters, list):
        return []
    saida: List[str] = []
    for f in filters:
        if not isinstance(f, str):
            continue
        nome = LEGACY_FILTER_ALIASES.get(f.lower().strip(), f.lower().strip())
        if nome in FILTER_OPTIONS and nome not in saida:
            saida.append(nome)
    return saida

FILTER_OPTIONS = {
    "todos": ("TUDO", "🌟"),
    "anime": ("Anime", "🎬"),
    "news": ("News", "📰"),
    "music": ("Music", "🎵"),
    "games": ("Games", "🎮"),
    "filmes": ("Filmes", "🎥"),
}


# =========================================================
# HELPER FUNCTIONS
# =========================================================

# Cache de matchers por keyword: compila a regex de cada termo UMA vez.
# ("regex", <padrão compilado>) para palavras alfanuméricas (word boundaries + plural),
# ("substr", <termo lower>) para frases/termos com caracteres especiais (busca simples).
_KEYWORD_MATCHER_CACHE: Dict[str, Tuple[str, Any]] = {}

# Kana, kanji e hangul contam como \w para o módulo re, mas japonês e coreano
# não separam palavras por espaço: `\b主題歌\b` NUNCA casa dentro de
# `アニメ主題歌決定`. Toda keyword com um destes caracteres é casada por
# substring, como já se faz para frases com pontuação.
_CJK_RE = re.compile(
    r'[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯ｦ-ﾟ]'
)


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _matcher_for(kw: str) -> Tuple[str, Any]:
    """
    PROPÓSITO DE NEGÓCIO: compilar UMA vez a forma de procurar cada termo do
    filtro, escolhendo a estratégia certa para o idioma do termo. Termo mal
    casado é notícia perdida (ou lixo publicado) sem nenhum sinal no log.

    INVARIANTES DO DOMÍNIO:
    - Termo com kana/kanji/hangul é casado por substring (não há fronteira de
      palavra em japonês).
    - Termo alfanumérico latino mantém fronteira de palavra + plural opcional,
      para "op" não casar dentro de "opening".
    - O resultado é memorizado por termo; a compilação nunca se repete.

    COMPORTAMENTO EM CASO DE FALHA: termo que não compile como regex cai para
    substring em vez de derrubar a varredura.
    """
    cached = _KEYWORD_MATCHER_CACHE.get(kw)
    if cached is not None:
        return cached

    kw_lower = kw.lower()
    matcher: Tuple[str, Any]
    if _has_cjk(kw_lower):
        matcher = ("substr", kw_lower)
    elif kw_lower.replace(" ", "").replace("-", "").isalnum():
        try:
            matcher = ("regex", re.compile(r'\b' + re.escape(kw_lower) + r's?\b', re.IGNORECASE))
        except re.error:
            matcher = ("substr", kw_lower)
    else:
        matcher = ("substr", kw_lower)

    _KEYWORD_MATCHER_CACHE[kw] = matcher
    return matcher


def _contains_any(text: str, keywords: List[str]) -> str:
    """Verifica se alguma keyword está presente no texto.
    Retorna a keyword que bateu (ou "" se não bateu).
    Usa busca case-insensitive e suporta caracteres especiais.
    """
    if not keywords:
        return ""

    text_lower = text.lower()

    for kw in keywords:
        kind, val = _matcher_for(kw)
        # Para palavras simples, usa word boundaries (regex pré-compilada)
        if kind == "regex":
            if val.search(text_lower):
                return kw
        # Para frases ou termos com caracteres especiais, usa busca simples
        elif val in text_lower:
            return kw

    return ""


def _is_untrusted_source(source: str) -> bool:
    """
    PROPÓSITO DE NEGÓCIO: dizer se uma fonte é "mista" — canal de streaming
    genérico, imprensa de games, canal de música — caso em que a notícia só passa
    se o termo de anime estiver no TÍTULO, não no resumo. É o que impede um
    trailer de dorama do Netflix de entrar num canal de notícias de anime.

    INVARIANTES DO DOMÍNIO:
    - O cadastro em sources.json (`untrusted`) é a autoridade. Fonte cadastrada
      nunca é reclassificada por heurística de texto de URL.
    - A heurística por hints só vale para URL não cadastrada, e olha para
      domínio/host — nunca para channel_id, que não diz nada sobre o canal.

    COMPORTAMENTO EM CASO DE FALHA: fonte vazia ou cadastro ilegível devolve
    False (trata como confiável), que é o comportamento legado; nunca levanta.
    """
    source_l = (source or "").lower()
    if not source_l:
        return False

    meta = load_source_meta().get(source)
    if meta is not None:
        return bool(meta.get("untrusted", False))

    # Fonte fora do cadastro: rede de segurança por domínio/host.
    if any(h.lower() in source_l for h in UNTRUSTED_SOURCE_HINTS):
        return True

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
    """
    Decide se a notícia deve ser publicada na guild.
    Só retorna True se o conteúdo for reconhecidamente de anime/manga (termo estrito).
    Notícias que não forem de anime são bloqueadas (blacklist ou falta de termo estrito).
    """
    g = config.get(str(guild_id), {})
    filters = normalize_filters(g.get("filters", []))

    if not filters:
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

    # 1b) Blacklist de merch/colecionáveis: só o título decide (o resumo é
    # boilerplate de loja em metade dos canais oficiais).
    blocked_title = _contains_any(title_clean, BLACKLIST_TITULO)
    if blocked_title:
        log.warning(
            f"🚫 [BLOCKED] Guild: {guild_id} | Filtro: BLACKLIST_TITULO | Termo: '{blocked_title}' | Título: {title[:50]}..."
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
            # Regra: todas as categorias precisam ter ao menos 1 termo estrito de anime
            # (garante que só passem notícias de anime, nunca conteúdo genérico)
            if f in CAT_MAP:
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
