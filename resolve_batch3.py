import asyncio
import aiohttp
import re

URLS = [
    # General & Publishers
    "https://www.youtube.com/@AniplexUSA",
    "https://www.youtube.com/@KADOKAWAanime",
    "https://www.youtube.com/@aniplex",
    "https://www.youtube.com/@primevideoaunz",
    "https://www.youtube.com/@netflixanime",
    "https://www.youtube.com/@IGN",
    "https://www.youtube.com/@Netflix",
    "https://www.youtube.com/@TOHOanimation",
    "https://www.youtube.com/@TMSanimeJP",
    "https://www.youtube.com/@TheAnimeSelect",
    "https://www.youtube.com/@AniSelect",
    
    # Direct IDs (Verify validity)
    "https://www.youtube.com/channel/UC6VPE3kztGEtFVcJI0oIiUg",
    "https://www.youtube.com/channel/UCcjqSFXBg2cGQg5r0YooMiA",
    "https://www.youtube.com/channel/UCejtUitnpnf8Be-v5NuDSLw",
    "https://www.youtube.com/channel/UCvTMfwm9vZWk2ebLcwSU-qA",
    "https://www.youtube.com/channel/UC8yS5dCzbiPGf1HnAwwcnhQ",

    # Studios (Missing Website RSS)
    "https://www.youtube.com/@KyoaniChannel",
    "https://www.youtube.com/@ufotable_inc",
    "https://www.youtube.com/@studio_pierrot",
    "https://www.youtube.com/@witstudio3461",
    "https://www.youtube.com/@j.c.staffchannel4630",
    "https://www.youtube.com/@ScienceSARU"
]

async def resolve(session, url):
    # If it's already a channel ID URL, just formatting it is enough,
    # but let's check if it exists just to be safe.
    if "/channel/" in url:
        cid = url.split("/channel/")[1].split("/")[0]
        rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        print(f"✅ {url} -> {rss}")
        return

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        async with session.get(url, headers=headers, timeout=10) as resp:
            text = await resp.text()
            
            # 1. Try meta tag
            match = re.search(r'<meta itemprop="channelId" content="([^"]+)">', text)
            if match:
                cid = match.group(1)
                rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
                print(f"✅ {url} -> {rss}")
                return

            # 2. Try JSON config
            match = re.search(r'"channelId":"(UC[^"]+)"', text)
            if match:
                cid = match.group(1)
                rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
                print(f"✅ {url} -> {rss}")
                return
                
            print(f"❌ {url} -> Not Found")

    except Exception as e:
        print(f"⚠️ {url} -> Error {e}")

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [resolve(session, u) for u in URLS]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
