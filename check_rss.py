import asyncio
import aiohttp

SITES = [
    # Studios
    "https://studioghibli.com.br",
    "https://www.mappa.co.jp/en",
    "https://www.ufotable.com/en",
    "https://www.witstudio.co.jp",
    "https://www.madhouse.co.jp",
    "https://www.toei-animation.com",
    "https://www.sunrise-inc.co.jp",
    "https://www.bnfw.co.jp/en",
    "https://www.st-trigger.co.jp",
]

PATHS = [
    "/feed",
    "/rss",
    "/feed.xml",
    "/rss.xml",
    "/news/feed",
    "/news/rss",
    "/en/feed",
    "/en/rss"
]

async def check_site(session, base_url):
    print(f"Checking {base_url}...")
    
    # Clean trailing slash for appending
    clean = base_url.rstrip("/")
    
    found = []
    for p in PATHS:
        url = clean + p
        try:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    ct = resp.headers.get("content-type", "").lower()
                    if "xml" in ct or "rss" in ct or "atom" in ct:
                        print(f"  [SUCCESS] Found feed: {url} ({ct})")
                        found.append(url)
        except:
            pass
            
    if not found:
        print(f"  [FAILED] No obvious feed found for {base_url}")

async def main():
    async with aiohttp.ClientSession() as session:
        for s in SITES:
            await check_site(session, s)

if __name__ == "__main__":
    asyncio.run(main())
