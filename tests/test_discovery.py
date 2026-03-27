
import feedparser
import requests
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("DiscoveryTest")

def test_url(url):
    log.info(f"--- Testing {url} ---")
    
    # Method 1: Direct feedparser (Synchronous, but allows auto-discovery)
    log.info("Method 1: feedparser.parse(url)")
    d = feedparser.parse(url)
    log.info(f"  Entries: {len(d.entries)}")
    if len(d.entries) > 0:
        log.info(f"  Success! Title: {d.entries[0].title}")
    else:
        log.warning(f"  Failed. Bozo: {d.bozo}")

    # Method 2: Fetch content then parse (Current Bot Logic)
    log.info("Method 2: requests.get() -> feedparser.parse(content)")
    try:
        resp = requests.get(url, timeout=10)
        content = resp.content
        d2 = feedparser.parse(content)
        log.info(f"  Entries: {len(d2.entries)}")
        if len(d2.entries) > 0:
            log.info(f"  Success!")
        else:
            log.warning("  Failed (0 entries)")
            # Check if there is a link tag pointing to RSS in the HTML
            if b'application/rss+xml' in content:
                log.info("  FOUND RSS LINK IN HTML! logic is missing extraction.")
            else:
                log.info("  No RSS link found in HTML body.")
                
    except Exception as e:
        log.error(f"  Request failed: {e}")

if __name__ == "__main__":
    urls = [
        "https://www.youtube.com/channel/UC6pGdL66_Y_oNOf8vS_nS2w", # Standard Channel
        "https://www.animenewsnetwork.com/" # Site root
    ]
    for u in urls:
        test_url(u)
