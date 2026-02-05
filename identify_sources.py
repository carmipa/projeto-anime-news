
import aiohttp
import asyncio
import feedparser
import json
from utils.storage import p

async def identify():
    with open("sources.json", "r") as f:
        data = json.load(f)
    
    urls = []
    for cat in data["youtube_feeds"].values():
        urls.extend(cat)
        
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        feed = feedparser.parse(content)
                        title = feed.feed.get("title", "Unknown")
                        print(f"{title} -> {url}")
            except:
                pass

if __name__ == "__main__":
    asyncio.run(identify())
