"""
Scanner module - Feed fetching and processing logic.
"""
import ssl
import asyncio
import logging
import feedparser
import aiohttp
import certifi
from datetime import datetime, timedelta
from typing import List, Set, Tuple, Dict, Any
from urllib.parse import urlparse

import discord
from discord.ext import tasks

from settings import LOOP_MINUTES
from utils.storage import p, load_json_safe, save_json_safe
from utils.html import clean_html
from utils.cache import load_http_state, save_http_state, get_cache_headers, update_cache_state, cleanup_state
from utils.translator import t, translate_to_target
from core.stats import stats
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

def load_sources() -> List[str]:
    """Carrega todas as URLs de sources.json em uma lista plana."""
    data = load_json_safe(p("sources.json"), {})
    urls = []
    
    # Percorre recursivamente ou por categorias conhecidas
    # sources.json structure: {"category": {"sub": ["url", ...]}}
    for category in data.values():
        if isinstance(category, dict):
            for subcat in category.values():
                if isinstance(subcat, list):
                    urls.extend(subcat)
        elif isinstance(category, list):
            urls.extend(category)
            
    # Ordered deduplication
    seen = set()
    out = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

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
            return

        history_list, history_set = _load_history()
        http_state = load_http_state()
        config = load_json_safe(p("config.json"), {})
        
        sent_count = 0
        cache_hits = 0
        
        # SSL context for aiohttp
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())

        async with aiohttp.ClientSession() as session:
            for link_url in urls:
                try:
                    # Pequena pausa para garantir que o event loop do Discord respire e não dê timeout
                    await asyncio.sleep(0.1)
                    
                    # Validação de segurança da URL
                    try:
                        validated_url = validate_url(link_url)
                    except Exception as e:
                        log.warning(f"⚠️ [SECURITY] URL inválida ignorada: {link_url} - {e}")
                        audit_logger.log(
                            AuditEventType.SECURITY_CHECK_FAILED,
                            severity=AuditSeverity.WARNING,
                            details={"url": link_url, "reason": str(e)}
                        )
                        continue
                    
                    # 1. Fetch with Cache Headers (com retry)
                    async def fetch_feed():
                        headers = get_cache_headers(validated_url, http_state)
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
                            cache_hits += 1
                            continue
                        
                        # Update cache state (ETag/Last-Modified)
                        update_cache_state(validated_url, resp.headers, http_state)
                    
                    except NetworkError as e:
                        log.warning(f"⚠️ [HTTP] Erro ao buscar feed {validated_url}: {e}")
                        audit_logger.log(
                            AuditEventType.SCAN_FAILED,
                            severity=AuditSeverity.WARNING,
                            details={"url": validated_url, "error": str(e)}
                        )
                        continue

                    # 2. Parse Feed (com retry e em thread separada para não travar o loop do Discord)
                    async def parse_feed():
                        feed = await asyncio.to_thread(feedparser.parse, content)
                        if feed.bozo:
                            raise FeedParseError(f"Erro parsing {validated_url}: {feed.bozo_exception}")
                        return feed
                    
                    try:
                        feed = await retry_async(parse_feed, config=FEED_PARSE_RETRY_CONFIG)
                    except FeedParseError as e:
                        log.debug(f"🤡 [PARSER] Erro parsing {validated_url}: {e}")
                        continue

                    if not feed.entries:
                        continue

                    # 3. Process Entries (Newest first usually)
                    for entry in feed.entries[:30]: # Verifica últimos 30 posts (evita perder em canais ativos)
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


                            # Determine Language
                            target_lang = t.detect_lang(guild_id)
                            
                            # Translate
                            t_translated = await translate_to_target(clean_html(title), target_lang)
                            s_translated = await translate_to_target(clean_html(summary), target_lang)

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
                                
                                from datetime import timezone
                                pub_dt = None
                                try:
                                    st = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
                                    if st:
                                        # st is struct_time (year, month, day, hour, min, sec...)
                                        pub_dt = datetime(*st[:6], tzinfo=timezone.utc)
                                except Exception:
                                    pass

                                embed_ts = pub_dt if pub_dt else datetime.now()
                                if getattr(embed_ts, 'tzinfo', None) is None:
                                    embed_ts = embed_ts.replace(tzinfo=timezone.utc)
                                
                                postado_str = _format_publication_line(pub_dt)

                                embed_description = s_translated[:2000]
                                # Discord não aceita botões link com mailto: — dica de e-mail só no texto
                                email_hint = "\n\n✉️ _Para compartilhar por e-mail, copie o link da notícia._"
                                if is_media:
                                    # Para vídeos, mantém descrição completa e link visível
                                    embed_description = f"{s_translated[:1800]}\n\n🔗 **Assistir:** {link}\n\n{postado_str}{email_hint}"
                                else:
                                    embed_description = f"{s_translated[:1880]}\n\n{postado_str}{email_hint}"

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
                                
                                if not is_media and hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                                    try:
                                        thumb_url = entry.media_thumbnail[0].get("url")
                                        if thumb_url:
                                            embed.set_thumbnail(url=thumb_url)
                                    except (IndexError, AttributeError, KeyError, TypeError) as e:
                                        log.debug(f"⚠️ [EMBED] Erro ao adicionar thumbnail: {e}")
                                    except Exception as e:
                                        log.warning(f"⚠️ [EMBED] Erro inesperado ao processar thumbnail: {e}")
                                elif is_media and ("youtube.com" in link or "youtu.be" in link):
                                    # Thumbnail manual para YouTube (garante que o embed customizado fique bonito)
                                    yt_thumb = _get_youtube_thumbnail(link)
                                    if yt_thumb:
                                        embed.set_thumbnail(url=yt_thumb)

                                # Botões: apenas http(s). mailto: quebra a API (50035) — nunca adicionar.
                                view = _build_news_share_view(link, t_translated)

                                # Para mídias (YouTube/Twitch): o Discord sempre mostra o preview do link
                                # *depois* de todo o texto do content — por isso data/e-mail não podem ficar
                                # no mesmo content se quisermos abaixo do player.
                                # Solução: 1ª mensagem = título + URL + botões; 2ª = resposta só com meta
                                # (sem mention), fica visualmente “embaixo” do vídeo.
                                if is_media:
                                    media_view = _build_media_share_view(link, t_translated)

                                    content = f"**{t_translated}**\n{link}"
                                    log.debug(f"🎬 [MEDIA] Enviando vídeo com player nativo: {link[:60]}...")
                                    main_msg = await channel.send(
                                        content=content,
                                        view=media_view,
                                    )
                                    meta_lines = (
                                        f"{postado_str}\n\n"
                                        "✉️ _Para compartilhar por **e-mail**, copie o link do vídeo "
                                        "(mensagem acima)._"
                                    )
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
        
        # Update Stats
        from core.stats import stats
        stats.scans_completed += 1
        stats.news_posted += sent_count
        stats.cache_hits_total += cache_hits
        stats.last_scan_time = datetime.now()

        # Audit log
        audit_logger.log(
            AuditEventType.SCAN_COMPLETED,
            severity=AuditSeverity.INFO,
            details={
                "trigger": trigger,
                "sent_count": sent_count,
                "cache_hits": cache_hits,
                "total_feeds": len(urls)
            }
        )

        # Save History & State
        log.info(f"✅ [FINISHED] Varredura concluída. (Enviadas: {sent_count} | Cache hits: {cache_hits} | Trigger: {trigger})")
        
        # Persist Last Scan Time in http_state for status command (survives restart)
        http_state["_meta"] = {
            "last_scan": datetime.now().isoformat(),
            "last_run_trigger": trigger
        }
        save_http_state(http_state)

        if trigger != "loop":
            _log_next_run()


# =========================================================
# LOOP MANAGEMENT
# =========================================================

loop_task = None

def start_scheduler(bot: discord.Client):
    """Inicia o loop agendado."""
    global loop_task
    
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
