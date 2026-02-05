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

from utils.logger import log  # GRC Logger

# log = logging.getLogger("AnimeBotIntel") <-- Removed local logger

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
            
    # Remove duplicates and empty strings
    return list(set(u for u in urls if u))

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

def _log_next_run():
    next_run = datetime.now() + timedelta(minutes=LOOP_MINUTES)
    log.info(f"⏳ Próxima varredura: {next_run.strftime('%H:%M:%S')}")

async def run_scan_once(bot: discord.Client, trigger: str = "manual"):
    """
    Executa uma rodada de verificação de feeds.
    """
    # 🔎 Scan Start
    log.info(f"🔎 Iniciando varredura... (gatilho={trigger})")
    
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
                # 1. Fetch with Cache Headers
                headers = get_cache_headers(link_url, http_state)
                
                async with session.get(link_url, headers=headers, ssl=ssl_ctx, timeout=20) as resp:
                    if resp.status == 304:
                        cache_hits += 1
                        continue
                    
                    if resp.status != 200:
                        log.warning(f"⚠️ [HTTP] Status {resp.status} para {link_url}")
                        continue
                        
                    content = await resp.read()
                    
                    # Update cache state (ETag/Last-Modified)
                    update_cache_state(link_url, resp.headers, http_state)

                # 2. Parse Feed
                feed = feedparser.parse(content)
                if feed.bozo:
                    log.debug(f"🤡 [PARSER] Bozo exception parsing {link_url}: {feed.bozo_exception}")

                if not feed.entries:
                    continue

                # 3. Process Entries (Newest first usually)
                # We check newest to oldest, stop if we hit history? 
                # Or just check all? Checking all is safer for small feeds.
                for entry in feed.entries[:10]: # Check top 10
                    link = getattr(entry, "link", "")
                    if not link or link in history_set:
                        continue
                        
                    title = getattr(entry, "title", "No Title")
                    summary = getattr(entry, "summary", "")
                    
                    # Determine media type
                    is_media = "youtube.com" in link or "youtu.be" in link or "twitch.tv" in link

                    # 4. Check Filters per Guild
                    # We need to broadcast this news to ALL matching guilds
                    posted_anywhere = False
                    
                    for guild_id, guild_cfg in config.items():
                        if not match_intel(guild_id, title, summary, config):
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

                        # 5. Send to Discord
                        try:
                            log.info(f"📤 [SENDING] Enviando para canal {channel.name} ({channel_id})...")
                            if is_media:
                                msg_content = f"**{t_translated}**\n{link}"
                                view = WatchView(link)
                                await channel.send(content=msg_content, view=view)
                            else:
                                embed = discord.Embed(
                                    title=t_translated[:256],
                                    description=s_translated[:2000], # Limit desc
                                    url=link,
                                    color=discord.Color.from_rgb(255, 0, 32),
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
                                
                                # Try to find image
                                if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
                                    try:
                                        thumb_url = entry.media_thumbnail[0].get("url")
                                        if thumb_url:
                                            embed.set_thumbnail(url=thumb_url)
                                    except: pass
                                
                                await channel.send(embed=embed)

                            posted_anywhere = True
                            
                        except Exception as e:
                            log.error(f"❌ [DISCORD] Falha ao enviar no canal {channel_id}: {e}")
                    
                    # If sent to at least one guild, verify counting
                    if posted_anywhere:
                        sent_count += 1
                        # Mark as seen GLOBALLY (if logic allows)
                        # The original logic marked it as seen if 'posted_anywhere'.
                        history_set.add(link)
                        history_list.append(link)

            except Exception as e:
                log.error(f"🔥 [SCANNER] Erro processando feed {link_url}: {e}")

    save_history(history_list)
    cleaned = cleanup_state(http_state)
    if cleaned > 0:
        log.info(f"🧹 [CLEANUP] Limpeza de estado: {cleaned} entradas antigas removidas.")
        
    save_http_state(http_state)
    
    stats.last_scan_time    # Update Stats
    from core.stats import stats
    stats.scans_completed += 1
    stats.news_posted += sent_count
    # stats.cache_hits_total is not tracked easily here without modification, focusing on basics
    stats.last_scan_time = datetime.now()

    # Save History & State
    log.info(f"✅ [FINISHED] Varredura concluída. (Enviadas: {sent_count} | Trigger: {trigger})")
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
    
    @intelligence_gathering.before_loop
    async def _before_loop():
        await bot.wait_until_ready()
    
    loop_task = intelligence_gathering
    loop_task.start()
    log.info(f"🔄 Agendador de tarefas iniciado ({LOOP_MINUTES} min).")
