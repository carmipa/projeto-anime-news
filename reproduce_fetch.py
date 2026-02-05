
import asyncio
import aiohttp
import feedparser
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Test")

async def test_fetch(url):
    log.info(f"Testing URL: {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    log.error(f"Status not 200: {resp.status}")
                    return
                content = await resp.read()
                feed = feedparser.parse(content)
                if feed.bozo:
                    log.warning(f"Bozo exception: {feed.bozo_exception}")
                
                log.info(f"Entries found: {len(feed.entries)}")
                if len(feed.entries) > 0:
                    log.info(f"First entry title: {feed.entries[0].get('title')}")
        except Exception as e:
            log.error(f"Error: {e}")

async def main():
    urls = [
        "https://www.youtube.com/feeds/videos.xml?user=IGNentertainment",
        "https://www.youtube.com/feeds/videos.xml?user=CrunchyrollCollection",
        "https://www.animenewsnetwork.com/news/rss.xml"
    ]
    for u in urls:
        await test_fetch(u)

if __name__ == "__main__":
    asyncio.run(main())
