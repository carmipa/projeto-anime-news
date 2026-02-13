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

                    # 2. Parse Feed (com retry)
                    async def parse_feed():
                        feed = feedparser.parse(content)
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
                    for entry in feed.entries[:10]: # Check top 10
                        link = getattr(entry, "link", "")
                        title = getattr(entry, "title", "No Title")
                        
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
                                
                                embed_description = s_translated[:2000]
                                if is_media:
                                    # Para vídeos, mantém descrição completa e link visível
                                    embed_description = f"{s_translated[:1900]}\n\n🔗 **Assistir:** {link}"
                                
                                embed = discord.Embed(
                                    title=embed_title,
                                    description=embed_description,
                                    url=link,
                                    color=color,
                                    timestamp=datetime.now()
                                )
                                
                                author_name = t.get('embed.author', lang=target_lang)
                                embed.set_author(
                                    name=author_name,
                                    icon_url=bot.user.display_avatar.url if bot.user else None
                                )
                                
                                source_domain = urlparse(link).netloc
                                footer_text = t.get('embed.source', lang=target_lang, source=source_domain)
                                embed.set_footer(text=footer_text)
                                
                                # Try to find image (serve tanto para news quanto para vídeos)
                                if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                                    try:
                                        thumb_url = entry.media_thumbnail[0].get("url")
                                        if thumb_url:
                                            embed.set_thumbnail(url=thumb_url)
                                    except (IndexError, AttributeError, KeyError, TypeError) as e:
                                        log.debug(f"⚠️ [EMBED] Erro ao adicionar thumbnail: {e}")
                                    except Exception as e:
                                        log.warning(f"⚠️ [EMBED] Erro inesperado ao processar thumbnail: {e}")

                                # Para mídias (YouTube/Twitch), envia link no content para ativar preview do player
                                if is_media:
                                    # Envia o link do YouTube no content para que o Discord crie o preview automático com player
                                    # O embed mantém as informações e cores, e o link no content ativa o player embutido
                                    view = WatchView(link)
                                    log.debug(f"🎬 [MEDIA] Enviando vídeo com player embutido: {link[:60]}...")
                                    await channel.send(content=link, embed=embed, view=view)
                                else:
                                    await channel.send(embed=embed)

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
