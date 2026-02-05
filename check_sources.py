import json, sys, requests

def iter_urls(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from iter_urls(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_urls(v)
    elif isinstance(obj, str) and obj.startswith("http"):
        yield obj

# Handle file opening directly if stdin is empty (fallback)
if not sys.stdin.isatty():
    data = json.load(sys.stdin)
else:
    with open("sources.json", "r") as f:
        data = json.load(f)

urls = list(dict.fromkeys(iter_urls(data)))  # dedup preservando ordem

print(f"Testando {len(urls)} URLs...\n")
for u in urls:
    try:
        r = requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        status = r.status_code
        # Simple check for XML/RSS content
        is_xml = "xml" in r.headers.get("Content-Type", "") or "<feed" in r.text or "<rss" in r.text
        ok = (status == 200 and is_xml)
        print(f"{'OK ' if ok else 'BAD'} {status}  {u}")
    except Exception as e:
        print(f"ERR      {u}  -> {e}")
