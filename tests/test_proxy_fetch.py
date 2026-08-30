"""
Guardas do proxy de saída (Cloudflare) e da decisão de rotear.

Calibra o anti-regressão que custou caro no bot irmão: o log dizia "via proxy: True"
mesmo com CLOUDFLARE_PROXY_URL VAZIO, mascarando que o Reddit era batido direto do IP
do VPS. Aqui o par: com proxy configurado a URL é prefixada e o segredo viaja; com
proxy vazio a busca é DIRETA (nunca um prefixo com vazio, nunca o segredo).
"""
import asyncio

import core.scanner as sc
import core.sources as src


_RSS = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>'
    b'<item><title>x</title><link>http://x/</link>'
    b'<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item></channel></rss>'
)


class _FakeResp:
    status = 200
    headers = {}

    def __init__(self, body):
        self._body = body

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self):
        self.urls = []
        self.headers_seen = {}

    def get(self, url, headers=None, **kw):
        self.urls.append(url)
        self.headers_seen = dict(headers or {})
        return _FakeResp(_RSS)


# --- source_wants_proxy: a INTENÇÃO da fonte ---

def test_wants_proxy_por_dominio_candidato():
    assert src.source_wants_proxy("https://www.siliconera.com/feed/") is True


def test_wants_proxy_por_cadastro(monkeypatch):
    monkeypatch.setattr(src, "load_source_meta", lambda: {
        "https://x.test/feed": {"use_proxy": True},
        "https://y.test/feed": {"use_proxy": False},
    })
    assert src.source_wants_proxy("https://x.test/feed") is True
    assert src.source_wants_proxy("https://y.test/feed") is False
    assert src.source_wants_proxy("https://z.test/feed") is False  # não cadastrada


# --- roteamento REAL pelo _fetch_and_parse (com/sem proxy) ---

def test_fetch_roteia_via_proxy_quando_configurado(monkeypatch):
    monkeypatch.setattr(sc, "CLOUDFLARE_PROXY_URL", "https://proxy.test/")
    monkeypatch.setattr(sc, "CLOUDFLARE_PROXY_SECRET", "s3cr3t")
    monkeypatch.setattr(sc, "source_wants_proxy", lambda u: True)
    sess = _FakeSession()
    asyncio.run(sc._fetch_and_parse(sess, "https://feed.test/rss", {}, None))
    assert sess.urls[0] == "https://proxy.test/https://feed.test/rss"
    assert sess.headers_seen.get("X-Proxy-Secret") == "s3cr3t"


def test_fetch_direto_quando_proxy_vazio(monkeypatch):
    # A fonte QUER proxy, mas CLOUDFLARE_PROXY_URL está vazio: busca DIRETA, sem
    # prefixo e sem segredo. É a cicatriz do bot irmão, virada guarda.
    monkeypatch.setattr(sc, "CLOUDFLARE_PROXY_URL", "")
    monkeypatch.setattr(sc, "CLOUDFLARE_PROXY_SECRET", "s3cr3t")
    monkeypatch.setattr(sc, "source_wants_proxy", lambda u: True)
    sess = _FakeSession()
    asyncio.run(sc._fetch_and_parse(sess, "https://feed.test/rss", {}, None))
    assert sess.urls[0] == "https://feed.test/rss"
    assert "X-Proxy-Secret" not in sess.headers_seen


def test_fetch_direto_quando_fonte_nao_quer(monkeypatch):
    monkeypatch.setattr(sc, "CLOUDFLARE_PROXY_URL", "https://proxy.test/")
    monkeypatch.setattr(sc, "source_wants_proxy", lambda u: False)
    sess = _FakeSession()
    asyncio.run(sc._fetch_and_parse(sess, "https://feed.test/rss", {}, None))
    assert sess.urls[0] == "https://feed.test/rss"
    assert "X-Proxy-Secret" not in sess.headers_seen
