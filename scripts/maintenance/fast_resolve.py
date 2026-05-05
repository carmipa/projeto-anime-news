import asyncio
import aiohttp
import re

async def get(session, url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            match = re.search(r'channelId":"(UC[^"]+)"', text)
            if match:
                print(f"{url} :: {match.group(1)}")
            else:
                print(f"{url} :: NOT FOUND")
    except Exception as e:
        print(f"{url} :: ERROR {e}")

async def main():
    urls = [
    "https://www.youtube.com/c/SatoCompany",
    "https://www.youtube.com/@TokuSatoOficial",
    "https://www.youtube.com/@SatoAnimeOficial",
    "https://www.youtube.com/@movieplus-sato"
    ]
    async with aiohttp.ClientSession() as session:
        for u in urls:
            await get(session, u)

if __name__ == "__main__":
    asyncio.run(main())
