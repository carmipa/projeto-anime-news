"""
Scanner module - Feed fetching and processing logic.
"""
import ssl
import asyncio
import logging
import re
import feedparser
import aiohttp
import certifi
from datetime import datetime, timedelta, timezone
from typing import List, Set, Tuple, Dict, Any
from urllib.parse import urlparse, urljoin

import discord
from discord.ext import tasks

from settings import LOOP_MINUTES, FEED_CONCURRENCY, MAX_ITENS_POR_FONTE
from core.sources import load_sources, source_headers  # noqa: F401 (load_sources reexportado: bot.cogs.info importa daqui)
from utils.storage import p, load_json_safe, save_json_safe
from utils.html import clean_html
from utils.cache import load_http_state, save_http_state, get_cache_headers, update_cache_state, cleanup_state
from utils.translator import t
from core.stats import stats, avaliar_varredura
from core.filters import match_intel
from bot.views.player import WatchView

from utils.logger import log, log_with_context  # GRC Logger
from utils.retry import retry_async, HTTP_RETRY_CONFIG, FEED_PARSE_RETRY_CONFIG
from utils.exceptions import NetworkError, FeedParseError
from utils.audit import audit_logger, AuditEventType, AuditSeverity
from utils.security import validate_url

# log = logging.getLogger("AnimeBotIntel") <-- Removed local logger

SCAN_LOCK = asyncio.Lock()


def _classify_entry_type(title: str, link: str, is_media: bool) -> str:
    """
    Classifica o tipo de item para fins visuais:
    - "launch": lançamentos / anúncios fortes (trailer, novo episódio, etc)
    - "video": vídeos em geral (YouTube/Twitch)
    - "repost": republicações / atualizações
    - "news": notícias padrão (default)
    """
    text = (title or "").lower()

    if is_media:
        # Para mídias, diferenciamos lançamentos de vídeos comuns
        launch_keywords = (
            "trailer",
            "pv",
            "teaser",
            "opening",
            "ending",
            "ost",
            "soundtrack",
            "new episode",
            "episode",
            "episódio",
            "estreia",
            "estreia",
            "season",
        )
        if any(kw in text for kw in launch_keywords):
            return "launch"
        return "video"

    # Lançamentos para notícias baseadas em texto (verificar ANTES de repost)
    launch_keywords_text = (
        "anunciado",
        "announced",
        "revealed",
        "lançamento",
        "estreia",
        "novo anime",
        "new anime",
        "season ",
        "trailer",
        "pv",
        "teaser",
    )
    if any(kw in text for kw in launch_keywords_text):
        return "launch"

    # Heurística simples para repost / atualização (apenas se não for lançamento)
    # Verifica palavras mais específicas primeiro
    repost_keywords = ("repost", "repostagem", "reprint", "republicado", "republication")
    if any(kw in text for kw in repost_keywords):
        return "repost"
    
    # "update" e "atualização" podem ser lançamentos também, então só marca como repost
    # se não tiver keywords de lançamento (já verificado acima)
    if "update" in text or "atualização" in text:
        # Se contém "update" mas também tem keywords de lançamento, já foi capturado acima
        # Se chegou aqui, é provavelmente uma atualização/repost
        return "repost"

    return "news"


def _get_embed_color(entry_type: str) -> discord.Color:
    """
    Define cores diferentes para cada tipo de card:
    - launch (lançamentos): verde
    - video (vídeos): roxo
    - repost (repostagens/atualizações): laranja
    - news (notícias gerais): vermelho padrão
    """
    if entry_type == "launch":
        return discord.Color.green()
    if entry_type == "video":
        return discord.Color.purple()
    if entry_type == "repost":
        return discord.Color.orange()
    # news / default
    return discord.Color.from_rgb(255, 0, 32)


def _format_publication_line(pub_dt: datetime | None) -> str:
    """
    Data/hora da publicação do feed: texto legível + timestamps do Discord
    (<t:unix:F> data/hora no fuso do usuário, <t:unix:R> relativo tipo 'há 2 horas').
    """
    from datetime import timezone

    now = datetime.now(timezone.utc)
    if pub_dt is None:
        dt = now
    else:
        dt = pub_dt
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
    unix_ts = int(dt.timestamp())
    label = dt.strftime("%d/%m/%Y %H:%M")
    return (
        f"🕒 **Postado em:** {label} (UTC) "
        f"· <t:{unix_ts}:F> · <t:{unix_ts}:R>"
    )


def _extract_entry_datetime(entry: Any) -> datetime | None:
    """Extrai data UTC do entry (published/updated)."""
    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=timezone.utc)
    except Exception:
        return None


# Discord API: botões link só aceitam http(s) ou discord — mailto: gera 50035.
_DISCORD_LINK_BUTTON_URL_MAX = 512


def _ensure_https_button_url(url: str) -> str:
    """Garante URL segura para Button(style=link). Nunca mailto:, javascript:, etc."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        raise ValueError(
            "URL de botão rejeitada: Discord só aceita http(s) em link buttons "
            f"(recebido: {u[:60]!r}…)"
        )
    if len(u) > _DISCORD_LINK_BUTTON_URL_MAX:
        u = u[: _DISCORD_LINK_BUTTON_URL_MAX]
    return u


def _whatsapp_share_url(link: str, title: str) -> str:
    from urllib.parse import quote

    link = _ensure_https_button_url(link.strip())
    base = "https://api.whatsapp.com/send?text="
    full = quote(f"{title}\n\n{link}", safe="")
    if len(base) + len(full) <= _DISCORD_LINK_BUTTON_URL_MAX:
        return base + full
    short = quote(link, safe="")
    return (base + short)[:_DISCORD_LINK_BUTTON_URL_MAX]


def _twitter_share_url(link: str, title: str) -> str:
    from urllib.parse import quote

    link = _ensure_https_button_url(link.strip())
    uq = quote(link, safe="")
    base = "https://twitter.com/intent/tweet?url="
    suffix = "&text="
    room = _DISCORD_LINK_BUTTON_URL_MAX - len(base) - len(uq) - len(suffix)
    if room < 8:
        return (base + uq)[:_DISCORD_LINK_BUTTON_URL_MAX]
    tq = quote(title[:room], safe="")
    out = base + uq + suffix + tq
    return out[:_DISCORD_LINK_BUTTON_URL_MAX]


def _build_news_share_view(link: str, t_translated: str) -> discord.ui.View:
    """Somente links https — sem mailto (API Discord proíbe)."""
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="Leia Mais",
            url=_ensure_https_button_url(link),
            emoji="📖",
            style=discord.ButtonStyle.link,
        )
    )
    view.add_item(
        discord.ui.Button(
            label="WhatsApp",
            url=_whatsapp_share_url(link, t_translated),
            emoji="🟢",
            style=discord.ButtonStyle.link,
        )
    )
    view.add_item(
        discord.ui.Button(
            label="Compartilhar / X",
            url=_twitter_share_url(link, t_translated[:400]),
            emoji="📣",
            style=discord.ButtonStyle.link,
        )
    )
    return view


def _build_media_share_view(link: str, t_translated: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="Assistir Agora / Watch Now",
            url=_ensure_https_button_url(link),
            emoji="▶️",
            style=discord.ButtonStyle.link,
        )
    )
    view.add_item(
        discord.ui.Button(
            label="WhatsApp",
            url=_whatsapp_share_url(link, t_translated),
            emoji="🟢",
            style=discord.ButtonStyle.link,
        )
    )
    view.add_item(
        discord.ui.Button(
            label="Compartilhar / X",
            url=_twitter_share_url(link, t_translated[:400]),
            emoji="📣",
            style=discord.ButtonStyle.link,
        )
    )
    return view


def _extract_youtube_id(url: str) -> str:
    """Extrai o ID do vídeo de uma URL do YouTube."""
    if not url:
        return ""
    
    # Formatos comuns:
    # watch?v=ID
    # shorts/ID
    # youtu.be/ID
    parsed = urlparse(url)
    if parsed.netloc in ("youtube.com", "www.youtube.com"):
        if "/shorts/" in parsed.path:
            return parsed.path.split("/shorts/")[1].split("?")[0]
        # query v=ID
        from urllib.parse import parse_qs
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
    elif parsed.netloc == "youtu.be":
        return parsed.path.strip("/")
    
    return ""


def _normalize_youtube_url(url: str) -> str:
    """Normaliza URLs do YouTube para o formato watch?v=ID."""
    yid = _extract_youtube_id(url)
    if yid:
        return f"https://www.youtube.com/watch?v={yid}"
    return url


def _get_youtube_thumbnail(url: str) -> str:
    """Gera a URL da thumbnail HQ do YouTube."""
    yid = _extract_youtube_id(url)
    if yid:
        return f"https://img.youtube.com/vi/{yid}/hqdefault.jpg"
    return ""


def _extract_best_image_url(entry: Any, link: str, summary: str) -> str:
    """
    Tenta extrair a melhor imagem possível do item do feed.
    Ordem:
    1) media_thumbnail
    2) media_content (type=image)
    3) links/enclosures (rel=enclosure ou type=image)
    4) primeira <img src=...> no summary/content
    5) fallback YouTube thumbnail
    """
    try:
        thumbs = getattr(entry, "media_thumbnail", None)
        if thumbs and isinstance(thumbs, list):
            url = thumbs[0].get("url", "")
            if url.startswith(("http://", "https://")):
                return url
    except Exception:
        pass

    try:
        media = getattr(entry, "media_content", None)
        if media and isinstance(media, list):
            for item in media:
                url = item.get("url", "")
                ctype = (item.get("type", "") or "").lower()
                if url.startswith(("http://", "https://")) and ("image" in ctype or not ctype):
                    return url
    except Exception:
        pass

    try:
        links = getattr(entry, "links", None) or []
        if isinstance(links, list):
            for item in links:
                href = item.get("href", "")
                rel = (item.get("rel", "") or "").lower()
                ctype = (item.get("type", "") or "").lower()
                if href.startswith(("http://", "https://")) and (rel == "enclosure" or "image" in ctype):
                    return href
    except Exception:
        pass

    html_blob = summary or ""
    try:
        content_list = getattr(entry, "content", None)
        if content_list and isinstance(content_list, list):
            html_blob += " " + " ".join((c.get("value", "") for c in content_list if isinstance(c, dict)))
    except Exception:
        pass

    if html_blob:
        m = re.search(r"<img[^>]+src=[\"']([^\"']+)[\"']", html_blob, re.IGNORECASE)
        if m:
            src = m.group(1).strip()
            if src.startswith(("http://", "https://")):
                return src
            if src.startswith("//"):
                return "https:" + src
            if src.startswith("/"):
                return urljoin(link, src)

    if "youtube.com" in link or "youtu.be" in link:
        return _get_youtube_thumbnail(link)

    return ""

def _load_history() -> Tuple[List[str], Set[str]]:
    hist_list = load_json_safe(p("history.json"), [])
    # Garante que é lista
    if not isinstance(hist_list, list):
        hist_list = []
    return hist_list, set(hist_list)

def save_history(hist_list: List[str]):
    # Maintain max size (e.g. 1000)
    if len(hist_list) > 1000:
        hist_list = hist_list[-1000:]
    save_json_safe(p("history.json"), hist_list)

def _log_next_run(when: datetime | None = None):
    if when is None:
        when = datetime.now() + timedelta(minutes=LOOP_MINUTES)
    log.info(f"⏳ Próxima varredura: {when.strftime('%H:%M:%S')}")


# Sentinela para "feed não modificado" (HTTP 304), distinto de None (erro).
_CACHE_HIT = object()


async def _fetch_and_parse(session, link_url, http_state, ssl_ctx):
    """
    Busca e faz o parse de UM feed. Seguro para rodar concorrentemente
    (só faz operações sync sobre http_state entre awaits, sem interleaving).

    Retorna (link_url, feed) em sucesso, (link_url, _CACHE_HIT) em 304,
    ou (link_url, None) em qualquer falha (já logada/auditada). Nunca levanta,
    para não abortar o asyncio.gather das outras fontes.
    """
    try:
        # Validação de segurança da URL (SSRF)
        try:
            validated_url = validate_url(link_url)
        except Exception as e:
            log.warning(f"⚠️ [SECURITY] URL inválida ignorada: {link_url} - {e}")
            audit_logger.log(
                AuditEventType.SECURITY_CHECK_FAILED,
                severity=AuditSeverity.WARNING,
                details={"url": link_url, "reason": str(e)}
            )
            return link_url, None

        # 1. Fetch com Cache Headers (com retry)
        async def fetch_feed():
            headers = get_cache_headers(validated_url, http_state)
            headers.update(source_headers(validated_url))  # User-Agent por fonte, se o cadastro exigir
            async with session.get(validated_url, headers=headers, ssl=ssl_ctx, timeout=20) as resp:
                if resp.status == 304:
                    return None, resp  # Cache hit
                if resp.status != 200:
                    raise NetworkError(f"HTTP {resp.status} para {validated_url}")
                content = await resp.read()
                return content, resp

        try:
            content, resp = await retry_async(fetch_feed, config=HTTP_RETRY_CONFIG)
            if content is None:  # Cache hit (304)
                return link_url, _CACHE_HIT
            update_cache_state(validated_url, resp.headers, http_state)
        except NetworkError as e:
            log.warning(f"⚠️ [HTTP] Erro ao buscar feed {validated_url}: {e}")
            audit_logger.log(
                AuditEventType.SCAN_FAILED,
                severity=AuditSeverity.WARNING,
                details={"url": validated_url, "error": str(e)}
            )
            return link_url, None

        # 2. Parse Feed (em thread separada, com retry)
        #
        # `bozo` NÃO é sinónimo de feed inutilizável: o feedparser liga essa
        # bandeira para qualquer desvio da norma (encoding mal declarado,
        # namespace não declarado, entidade solta) e mesmo assim devolve as
        # entradas. Descartar por `bozo` fazia um feed inteiro desaparecer por
        # um detalhe cosmético — e o único vestígio era uma linha de DEBUG.
        # Regra: só é falha se não sobrou entrada nenhuma.
        async def parse_feed():
            feed = await asyncio.to_thread(feedparser.parse, content)
            if feed.bozo and not feed.entries:
                raise FeedParseError(f"Erro parsing {validated_url}: {feed.bozo_exception}")
            return feed

        try:
            feed = await retry_async(parse_feed, config=FEED_PARSE_RETRY_CONFIG)
        except FeedParseError as e:
            log.warning(f"⚠️ [PARSER] Feed ilegível, 0 entradas: {validated_url} - {e}")
            audit_logger.log(
                AuditEventType.SCAN_FAILED,
                severity=AuditSeverity.WARNING,
                details={"url": validated_url, "error": str(e), "stage": "parse"}
            )
            return link_url, None

        if feed.bozo and feed.entries:
            log.info(
                f"🩹 [PARSER] {validated_url} veio malformado ({type(feed.bozo_exception).__name__}) "
                f"mas rendeu {len(feed.entries)} entradas — aproveitado."
            )

        return link_url, feed

    except Exception as e:
        log_with_context(
            log,
            logging.ERROR,
            f"Erro buscando feed: {e}",
            details={"url": link_url},
            event_type="SCAN_ERROR",
            exc_info=e
        )
        audit_logger.log(
            AuditEventType.SCAN_FAILED,
            severity=AuditSeverity.ERROR,
            details={"url": link_url, "error": str(e), "error_type": type(e).__name__}
        )
        return link_url, None


async def run_scan_once(bot: discord.Client, trigger: str = "manual"):
    """
    Executa uma rodada de verificação de feeds.
    """
    if SCAN_LOCK.locked():
        log.warning(f"⏭️ [SKIP] Varredura já em execução. Ignorando trigger={trigger}")
        return

    async with SCAN_LOCK:
        # 🔎 Scan Start
        log.info(f"🔎 Iniciando varredura... (gatilho={trigger})")
        
        # Audit log
        audit_logger.log(
            AuditEventType.SCAN_STARTED,
            severity=AuditSeverity.INFO,
            details={"trigger": trigger}
        )
        
        urls = load_sources()
        if not urls:
            log.warning("⚠️ [CONFIG] Nenhuma fonte encontrada em sources.json")
            # Catálogo vazio é a ANOMALIA que a telemetria de ausência existe para
            # apanhar — não pode sair em silêncio (§3.6). Registra, audita e persiste.
            veredito = avaliar_varredura(
                fontes_totais=0, feeds_falhos=0, feeds_vazios=0, itens_sem_data=0,
                itens_examinados=0, enviadas=0, semeados=0, cache_hits=0,
                ciclos_sem_envio=0,
            )
            stats.ultimo_veredito = veredito
            log.error("🔴 [VEREDITO] %s — %s", veredito["veredito"],
                      " · ".join(veredito["motivos"]))
            audit_logger.log(
                AuditEventType.SCAN_COMPLETED,
                severity=AuditSeverity.ERROR,
                details={"trigger": trigger, "total_feeds": 0,
                         "veredito": veredito["veredito"],
                         "veredito_motivos": veredito["motivos"]},
            )
            estado = load_http_state()
            estado.setdefault("_meta", {})
            estado["_meta"]["ultimo_veredito"] = veredito
            estado["_meta"]["last_scan"] = datetime.now().isoformat()
            save_http_state(estado)
            return

        history_list, history_set = _load_history()
        http_state = load_http_state()
        config = load_json_safe(p("config.json"), {})
        guild_lang_map = {gid: gcfg.get("language") for gid, gcfg in config.items() if "language" in gcfg}

        # Fontes já vistas em varreduras anteriores. Fonte NOVA tem o seu
        # acervo marcado como visto sem publicar: senão, acrescentar uma fonte
        # despeja de uma vez tudo o que ela publicou nas últimas 24h no canal.
        meta = http_state.get("_meta") or {}
        if "known_sources" in meta:
            fontes_conhecidas = set(meta.get("known_sources") or [])
        else:
            # Migração de uma versão que não gravava known_sources: as URLs que
            # já estão no cache HTTP são exatamente as que o bot já buscou
            # alguma vez. Sem isto, o primeiro arranque após a atualização
            # trataria TODAS as fontes como novas e não publicaria nada.
            fontes_conhecidas = {u for u in http_state if not u.startswith("_")}
            if fontes_conhecidas:
                log.info(
                    f"🔁 [MIGRAÇÃO] known_sources ausente; {len(fontes_conhecidas)} fontes "
                    f"do cache HTTP assumidas como já conhecidas."
                )
        primeira_execucao = not history_list and not fontes_conhecidas
        fontes_semeadas: List[str] = []

        sent_count = 0
        semeados = 0
        limitados = 0
        cache_hits = 0
        # Contadores de saúde da varredura. Sem isto, fonte morta é
        # indistinguível de "não houve notícia": o resumo só dizia quantas
        # foram enviadas, e o WARNING de cada falha perdia-se no meio do log.
        feeds_falhos: List[str] = []
        feeds_vazios = 0
        itens_sem_data = 0
        itens_examinados = 0  # itens novos que chegaram ao check de data (denominador)

        # Telemetria de ausência (§3.6): histórico de ciclos seguidos sem publicar,
        # que distingue "dia sem notícia" de "bot mudo".
        try:
            ciclos_sem_envio_anterior = int(meta.get("ciclos_sem_envio", 0) or 0)
        except (TypeError, ValueError):
            ciclos_sem_envio_anterior = 0

        now_utc = datetime.now(timezone.utc)
        window_start = now_utc - timedelta(days=1)

        limite_txt = MAX_ITENS_POR_FONTE if MAX_ITENS_POR_FONTE > 0 else "sem limite"
        log.info(
            f"🛡️ [INGEST] Política ativa: feeds estruturados | janela=hoje/ontem | "
            f"máx por fonte/rodada={limite_txt}"
        )
        if primeira_execucao:
            log.warning(
                "🌱 [PRIMEIRA EXECUÇÃO] Histórico vazio: esta varredura vai apenas "
                "marcar o acervo atual como visto, sem publicar. A próxima já publica "
                "normalmente."
            )
        
        # SSL context for aiohttp
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())

        async with aiohttp.ClientSession() as session:
            # === Fase 1: FETCH + PARSE concorrente (bounded por semaforo) ===
            # Antes cada feed era buscado em serie (gargalo). Agora ate
            # FEED_CONCURRENCY feeds sao buscados/parseados em paralelo.
            sem = asyncio.Semaphore(FEED_CONCURRENCY)

            async def _bounded_fetch(url):
                async with sem:
                    return await _fetch_and_parse(session, url, http_state, ssl_ctx)

            fetched = await asyncio.gather(*[_bounded_fetch(u) for u in urls])
            log.info(f"📥 [FETCH] {len(fetched)} fontes processadas (concorrencia={FEED_CONCURRENCY}).")

            # === Fase 2: processa entradas e envia ao Discord em SERIE ===
            # (mantem ordem deterministica e evita rate-limit do Discord)
            for link_url, feed in fetched:
                if feed is _CACHE_HIT:
                    cache_hits += 1
                    continue
                if feed is None:
                    feeds_falhos.append(link_url)
                    continue  # erro de fetch/parse ja logado na Fase 1

                # Fonte que o bot nunca varreu antes (recém-adicionada ao
                # sources.json) entra em modo semeadura: o acervo dela é
                # marcado como visto, sem publicar. Sem isto, adicionar 8
                # fontes despeja ~70 mensagens de uma vez no canal.
                #
                # A marcação acontece ANTES do teste de feed vazio: uma fonte
                # que respondeu sem entradas não tem acervo para engolir, e se
                # continuasse "nova" acabaria por semear — ou seja, engolir — o
                # primeiro lote no dia em que voltasse a publicar.
                fonte_nova = link_url not in fontes_conhecidas
                modo_semeadura = primeira_execucao or (fonte_nova and bool(history_list))
                if fonte_nova:
                    fontes_conhecidas.add(link_url)
                    if modo_semeadura and feed.entries:
                        fontes_semeadas.append(link_url)

                enviados_desta_fonte = 0

                try:
                    if not feed.entries:
                        feeds_vazios += 1
                        log.warning(f"⚠️ [FEED VAZIO] 200 OK mas 0 entradas: {link_url}")
                        continue

                    # 3. Process Entries (Newest first usually)
                    for entry in feed.entries:
                        link = getattr(entry, "link", "")
                        title = getattr(entry, "title", "No Title")
                        
                        # Normalize YouTube URLs (Shorts -> Watch para melhor preview)
                        if "youtube.com" in link or "youtu.be" in link:
                            link = _normalize_youtube_url(link)
                        
                        if not link or link in history_set:
                            if link in history_set:
                                # Log skipped item at DEBUG level (or INFO if debugging)
                                log.debug(f"📜 [HISTORY] Item já processado: {title[:50]}...")
                            continue
                            
                        summary = getattr(entry, "summary", "")

                        # Item NOVO (passou o dedup de history) que chega ao check de data.
                        # É o denominador que torna itens_sem_data um gatilho CALIBRADO:
                        # a PROPORÇÃO de itens novos descartados por falta de data, não um
                        # limiar cru — se a maioria cai sem data, a extração de data quebrou.
                        itens_examinados += 1
                        pub_dt = _extract_entry_datetime(entry)
                        if pub_dt is None:
                            itens_sem_data += 1
                            log.debug(f"⏭️ [DATE] Item sem data, ignorado: {title[:80]}...")
                            continue

                        if pub_dt < window_start or pub_dt > now_utc:
                            log.debug(f"⏭️ [DATE] Fora da janela (hoje/ontem): {title[:80]}... | pub={pub_dt.isoformat()}")
                            continue

                        # Semeadura: marca como visto e segue, sem publicar.
                        if modo_semeadura:
                            history_set.add(link)
                            history_list.append(link)
                            semeados += 1
                            continue

                        # Teto por fonte: um canal que sobe 15 vídeos num dia
                        # não pode ocupar o canal sozinho. Como o feed vem do
                        # mais recente para o mais antigo, o teto corta a cauda.
                        if 0 < MAX_ITENS_POR_FONTE <= enviados_desta_fonte:
                            limitados += 1
                            log.debug(
                                f"⏭️ [TETO] {link_url} já rendeu {enviados_desta_fonte} "
                                f"nesta rodada; resto fica para a próxima."
                            )
                            continue

                        # Determine media type
                        is_media = "youtube.com" in link or "youtu.be" in link or "twitch.tv" in link

                        # log 1x por item, não 1x por guild
                        log.debug(f"🧪 [ITEM] src={link_url} | title={title[:80]}...")

                        # 4. Check Filters per Guild
                        # We need to broadcast this news to ALL matching guilds
                        posted_channels = []
                        
                        for guild_id, guild_cfg in config.items():
                            if not match_intel(guild_id, title, summary, config, source=link_url):
                                continue
                                
                            channel_id = guild_cfg.get("channel_id")
                            if not channel_id:
                                continue
                                
                            channel = bot.get_channel(int(channel_id))
                            if not channel:
                                log.error(f"❌ [CONFIG] Canal {channel_id} não encontrado ou sem permissão de ver!")
                                continue


                            # Idioma só para as strings de UI do embed (autor/rodapé).
                            # O CONTEÚDO da notícia sai no idioma ORIGINAL: a tradução
                            # automática foi removida em 2026-08-30 — o Google devolvia
                            # página de erro (500 no IP da VPS) como se fosse tradução,
                            # degradando publicações em silêncio.
                            target_lang = t.detect_lang(guild_id, guild_lang_map=guild_lang_map)
                            t_translated = clean_html(title)
                            s_translated = clean_html(summary)

                            # 5. Classifica tipo e envia para o Discord
                            try:
                                log.info(f"📤 [SENDING] Enviando para canal {channel.name} ({channel_id})...")

                                # Classifica o tipo de item (lançamento, vídeo, repost, news)
                                entry_type = _classify_entry_type(title, link, is_media)
                                color = _get_embed_color(entry_type)

                                # Monta embed padrão com cor baseada no tipo
                                # Para vídeos, adiciona indicador visual no título ou descrição
                                embed_title = t_translated[:256]
                                if is_media and entry_type == "video":
                                    embed_title = f"▶️ {embed_title}"
                                
                                embed_ts = pub_dt
                                
                                postado_str = _format_publication_line(pub_dt)

                                embed_description = s_translated[:2000]
                                if is_media:
                                    # Para vídeos, mantém descrição completa e link visível
                                    embed_description = f"{s_translated[:1800]}\n\n🔗 **Assistir:** {link}\n\n{postado_str}"
                                else:
                                    embed_description = f"{s_translated[:1900]}\n\n{postado_str}"

                                embed_url = None if is_media else link

                                embed = discord.Embed(
                                    title=embed_title,
                                    description=embed_description,
                                    url=embed_url,
                                    color=color,
                                    timestamp=embed_ts
                                )
                                
                                author_name = t.get('embed.author', lang=target_lang)
                                embed.set_author(
                                    name=author_name,
                                    icon_url=bot.user.display_avatar.url if bot.user else None
                                )
                                
                                source_domain = urlparse(link).netloc
                                footer_text = t.get('embed.source', lang=target_lang, source=source_domain)
                                embed.set_footer(text=footer_text)
                                
                                best_image_url = _extract_best_image_url(entry, link, summary)
                                if best_image_url:
                                    try:
                                        if not is_media:
                                            # Para notícia textual, imagem grande melhora visualização do card
                                            embed.set_image(url=best_image_url)
                                        else:
                                            embed.set_thumbnail(url=best_image_url)
                                    except Exception as e:
                                        log.debug(f"⚠️ [EMBED] Falha ao aplicar imagem do item: {e}")

                                # Botões: apenas http(s). mailto: quebra a API (50035) — nunca adicionar.
                                view = _build_news_share_view(link, t_translated)

                                # Para mídias (YouTube/Twitch): o preview do link vem depois do content.
                                # 1ª mensagem = título + URL + botões; 2ª = resposta só com data/hora (sem mention).
                                if is_media:
                                    media_view = _build_media_share_view(link, t_translated)

                                    content = f"**{t_translated}**\n{link}"
                                    log.debug(f"🎬 [MEDIA] Enviando vídeo com player nativo: {link[:60]}...")
                                    main_msg = await channel.send(
                                        content=content,
                                        view=media_view,
                                    )
                                    meta_lines = postado_str
                                    try:
                                        await channel.send(
                                            content=meta_lines,
                                            reference=main_msg,
                                            mention_author=False,
                                        )
                                    except Exception as meta_err:
                                        log.warning(
                                            f"⚠️ [MEDIA] Não foi possível enviar linha de meta abaixo do vídeo: {meta_err}"
                                        )
                                else:
                                    await channel.send(embed=embed, view=view)

                                posted_channels.append(str(channel_id))
                                log.debug(f"✅ [POSTED] Tipo: {entry_type} | Cor: {color} | Mídia: {is_media} | Link: {link[:60]}...")
                                
                            except Exception as e:
                                log.error(f"❌ [DISCORD] Falha ao enviar no canal {channel_id}: {e}")
                        
                        # If sent to at least one guild, verify counting
                        if posted_channels:
                            sent_count += 1
                            enviados_desta_fonte += 1
                            # Mark as seen GLOBALLY (if logic allows)
                            history_set.add(link)
                            history_list.append(link)
                            log.debug(f"✅ [POSTED] link={link} | channels={','.join(posted_channels)}")

                except Exception as e:
                    log_with_context(
                        log,
                        logging.ERROR,
                        f"Erro processando feed: {e}",
                        details={"url": link_url},
                        event_type="SCAN_ERROR",
                        exc_info=e
                    )
                    audit_logger.log(
                        AuditEventType.SCAN_FAILED,
                        severity=AuditSeverity.ERROR,
                        details={"url": link_url, "error": str(e), "error_type": type(e).__name__}
                    )

        save_history(history_list)
        cleaned = cleanup_state(http_state)
        if cleaned > 0:
            log.info(f"🧹 [CLEANUP] Limpeza de estado: {cleaned} entradas antigas removidas.")
            
        save_http_state(http_state)
        
        # Update Stats (stats vem do import de módulo no topo; reimportar aqui
        # tornava `stats` local à função e quebrava usos anteriores no early-return)
        stats.scans_completed += 1
        stats.news_posted += sent_count
        stats.cache_hits_total += cache_hits
        # errors_count existia e nunca era incrementado: ficava sempre 0,
        # dando a impressão de que nenhuma fonte tinha falhado.
        stats.errors_count += len(feeds_falhos)
        stats.last_scan_time = datetime.now()

        # === Telemetria de ausência: veredito da varredura (§3.6) ===
        # Semeadura NÃO conta como ciclo sem envio: enviar 0 ao marcar o acervo de
        # uma fonte nova é esperado, e vira publicação no próximo ciclo (lente boa-fé).
        if sent_count == 0 and semeados == 0:
            ciclos_sem_envio = ciclos_sem_envio_anterior + 1
        else:
            ciclos_sem_envio = 0
        veredito = avaliar_varredura(
            fontes_totais=len(urls),
            feeds_falhos=len(feeds_falhos),
            feeds_vazios=feeds_vazios,
            itens_sem_data=itens_sem_data,
            itens_examinados=itens_examinados,
            enviadas=sent_count,
            semeados=semeados,
            cache_hits=cache_hits,
            ciclos_sem_envio=ciclos_sem_envio,
        )
        stats.ultimo_veredito = veredito
        _sev_veredito = {
            "OK": AuditSeverity.INFO,
            "ATENCAO": AuditSeverity.WARNING,
            "ANOMALIA": AuditSeverity.ERROR,
        }.get(veredito["veredito"], AuditSeverity.WARNING)

        # Audit log
        audit_logger.log(
            AuditEventType.SCAN_COMPLETED,
            severity=_sev_veredito,
            details={
                "trigger": trigger,
                "sent_count": sent_count,
                "cache_hits": cache_hits,
                "total_feeds": len(urls),
                "feeds_falhos": len(feeds_falhos),
                "feeds_vazios": feeds_vazios,
                "itens_sem_data": itens_sem_data,
                "veredito": veredito["veredito"],
                "veredito_motivos": veredito["motivos"],
            }
        )

        # Save History & State
        log.info(
            f"✅ [FINISHED] Varredura concluída. "
            f"(Enviadas: {sent_count} | Semeadas: {semeados} | "
            f"Retidas pelo teto: {limitados} | Cache hits: {cache_hits} | "
            f"Fontes: {len(urls)} | Falhas: {len(feeds_falhos)} | "
            f"Vazias: {feeds_vazios} | Itens sem data: {itens_sem_data} | "
            f"Trigger: {trigger})"
        )
        # O veredito é a manchete: OK em INFO, ATENÇÃO/ANOMALIA em WARNING, com o
        # motivo ao lado — para "está tudo bem" e "metade das fontes morreu" nunca
        # terem a mesma cara no log.
        _emoji_v = {"OK": "🟢", "ATENCAO": "🟡", "ANOMALIA": "🔴"}.get(veredito["veredito"], "⚪")
        _msg_v = f"{_emoji_v} [VEREDITO] {veredito['veredito']} — " + " · ".join(veredito["motivos"])
        if veredito["veredito"] == "OK":
            log.info(_msg_v)
        else:
            log.warning(_msg_v)
        if fontes_semeadas:
            log.info(
                "🌱 [SEMEADURA] %d fonte(s) nova(s) tiveram o acervo marcado como visto "
                "sem publicar; a partir da próxima varredura publicam normalmente:\n%s",
                len(fontes_semeadas),
                "\n".join(f"   - {u}" for u in fontes_semeadas),
            )
        if feeds_falhos:
            # URL inteira, uma por linha: é isto que permite decidir se a fonte
            # morreu ou se foi bloqueio pontual, sem ter de reproduzir à mão.
            log.warning(
                "⚠️ [FONTES COM FALHA] %d de %d:\n%s",
                len(feeds_falhos), len(urls),
                "\n".join(f"   - {u}" for u in feeds_falhos),
            )
        
        # Persist Last Scan Time in http_state for status command (survives restart).
        # `known_sources` mora aqui porque cleanup_state preserva chaves com "_";
        # é o que distingue fonte nova (semeia) de fonte já varrida (publica).
        http_state["_meta"] = {
            "last_scan": datetime.now().isoformat(),
            "last_run_trigger": trigger,
            "known_sources": sorted(fontes_conhecidas),
            "ciclos_sem_envio": ciclos_sem_envio,
            "ultimo_veredito": veredito,
        }
        save_http_state(http_state)

        if trigger != "loop":
            _log_next_run()


# =========================================================
# LOOP MANAGEMENT
# =========================================================

loop_task = None

def start_scheduler(bot: discord.Client):
    """
    PROPÓSITO DE NEGÓCIO: pôr de pé o relógio que dispara a varredura periódica
    de notícias. É chamado do `on_ready`, que o discord.py reexecuta a cada
    reconexão do gateway — coisa que acontece sozinha em produção.

    INVARIANTES DO DOMÍNIO:
    - No máximo UM agendador vivo por processo. O `@tasks.loop` é declarado
      DENTRO da função, logo cada chamada fabricava um objeto `Loop` novo: não
      havia o `RuntimeError` de "already launched" que protege um loop de
      módulo, o loop antigo continuava a correr e só se perdia a referência.
      Medido: duas chamadas = dois loops ativos, ambos disparando varredura.
    - Chamada repetida é no-op: mantém o agendador existente e o seu horário.

    COMPORTAMENTO EM CASO DE FALHA: se o loop guardado tiver morrido (cancelado
    ou terminado com exceção), um novo é criado no lugar; a função nunca levanta.
    """
    global loop_task

    if loop_task is not None and loop_task.is_running():
        log.info("🔄 Agendador já ativo — chamada ignorada (reconexão do gateway).")
        return loop_task

    @tasks.loop(minutes=LOOP_MINUTES)
    async def intelligence_gathering():
        await run_scan_once(bot, trigger="loop")
        if intelligence_gathering.next_iteration:
            _log_next_run(intelligence_gathering.next_iteration)

    @intelligence_gathering.before_loop
    async def _before_loop():
        await bot.wait_until_ready()

    loop_task = intelligence_gathering
    loop_task.start()
    log.info(f"🔄 Agendador de tarefas iniciado ({LOOP_MINUTES} min).")
    return loop_task
