import requests
import re
import time

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
    
    # Direct IDs
    "https://www.youtube.com/channel/UC6VPE3kztGEtFVcJI0oIiUg",
    "https://www.youtube.com/channel/UCcjqSFXBg2cGQg5r0YooMiA",
    "https://www.youtube.com/channel/UCejtUitnpnf8Be-v5NuDSLw",
    "https://www.youtube.com/channel/UCvTMfwm9vZWk2ebLcwSU-qA",
    "https://www.youtube.com/channel/UC8yS5dCzbiPGf1HnAwwcnhQ",

    # Studios
    "https://www.youtube.com/@KyoaniChannel",
    "https://www.youtube.com/@ufotable_inc",
    "https://www.youtube.com/@studio_pierrot",
    "https://www.youtube.com/@witstudio3461",
    "https://www.youtube.com/@j.c.staffchannel4630",
    "https://www.youtube.com/@ScienceSARU"
]

def resolve(url):
    try:
        if "/channel/" in url:
            cid = url.split("/channel/")[1].split("/")[0]
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        text = resp.text
        
        # Strategies to find Channel ID
        # 1. channelId key in JSON
        match = re.search(r'"channelId":"(UC[^"]+)"', text)
        if match:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={match.group(1)}"
            
        # 2. Meta tag
        match = re.search(r'<meta itemprop="channelId" content="([^"]+)">', text)
        if match:
             return f"https://www.youtube.com/feeds/videos.xml?channel_id={match.group(1)}"
             
        # 3. Canonical URL
        match = re.search(r'<link rel="canonical" href="https://www.youtube.com/channel/(UC[^"]+)">', text)
        if match:
             return f"https://www.youtube.com/feeds/videos.xml?channel_id={match.group(1)}"

        return None
    except Exception as e:
        return None

with open("resolved_feeds.txt", "w", encoding="utf-8") as f:
    for u in URLS:
        print(f"Resolving {u}...")
        rss = resolve(u)
        if rss:
            print(f"  FOUND: {rss}")
            f.write(f"{rss}\n")
        else:
            print(f"  NOT FOUND")
        time.sleep(1) # Polite delay
