
import asyncio
import aiohttp
import re
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger("Resolver")

URLS = [
    "https://www.youtube.com/c/SatoCompany",
    "https://www.youtube.com/@TokuSatoOficial",
    "https://www.youtube.com/@SatoAnimeOficial",
    "https://www.youtube.com/@movieplus-sato"
]

async def resolve(session, url):
    if not url.startswith("http"):
        url = "https://" + url
        
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        async with session.get(url, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                log.error(f"❌ {url} -> Status {resp.status}")
                return None
            
            content = await resp.text()
            
            # Look for <link rel="alternate" type="application/rss+xml" href="...">
            match = re.search(r'<link rel="alternate" type="application/rss\+xml" title="RSS" href="([^"]+)"', content)
            if match:
                rss = match.group(1)
                rss = match.group(1)
                log.info(f'{url} -> "{rss}",')
                return rss
            else:
                # Fallback: Try generic channelId regex again with looser constraints
                match_id = re.search(r'"channelId":"(UC[^"]+)"', content)
                if match_id:
                    cid = match_id.group(1)
                    rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
                    log.info(f'{url} -> "{rss}",')
                    return rss
                    
                log.warning(f"⚠️ {url} -> RSS/Channel ID not found")
                return None
    except Exception as e:
        log.error(f"🔥 {url} -> {e}")
        return None

async def main():
    log.info("Resolving Channels...")
    async with aiohttp.ClientSession() as session:
        tasks = [resolve(session, u) for u in URLS]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
