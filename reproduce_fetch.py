
import asyncio
import aiohttp
import feedparser
import logging
from core.filters import match_intel
from datetime import datetime

# Setup basic config for match_intel test
# Assuming a default guild config for testing
MOCK_CONFIG = {
    "123456789": {
        "filters": ["todos"], # Test with allow-all first
        "channel_id": "000000000"
    }
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("Test")

async def test_fetch(url):
    log.info(f"--- Testing URL: {url} ---")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    log.error(f"Status not 200: {resp.status}")
                    return (url, resp.status, 0)
                
                content = await resp.read()
                feed = feedparser.parse(content)
                
                log.info(f"Entries found: {len(feed.entries)}")
                
                for entry in feed.entries[:3]: # Check top 3
                    title = getattr(entry, "title", "No Title")
                    summary = getattr(entry, "summary", "")
                    link = getattr(entry, "link", "")
                    published = getattr(entry, "published", "No Date")
                    
                    log.info(f"Title: {title}")
                    log.info(f"Published: {published}")
                    
                    # Test Filter
                    # We pass the mock config. Since we used "todos", it should pass.
                    # You can change MOCK_CONFIG["123456789"]["filters"] to ["anime", "games"] to test strictness.
                    passed = match_intel("123456789", title, summary, MOCK_CONFIG)
                    log.info(f"Filter Match Result: {passed}")
                    
        except Exception as e:
            log.error(f"Error: {e}")

async def main():
    urls = [
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", # GundamInfo
        "https://www.animenewsnetwork.com/news/rss.xml" # ANN
    ]
    for u in urls:
        await test_fetch(u)

if __name__ == "__main__":
    asyncio.run(main())
