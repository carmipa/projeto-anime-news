"""
Web Server module using aiohttp.
Integrates directly with the bot loop.
"""
import logging
import hmac
from aiohttp import web
import aiohttp_jinja2
import jinja2
import os
from datetime import datetime

from core.stats import stats
from utils.storage import p

log = logging.getLogger("AnimeBotWeb")

routes = web.RouteTableDef()


def _check_api_auth(request) -> bool:
    """Se WEB_API_SECRET estiver definido, exige Authorization: Bearer <segredo>."""
    try:
        from settings import WEB_API_SECRET
    except Exception:
        WEB_API_SECRET = None
    if not WEB_API_SECRET:
        return True
    auth = request.headers.get("Authorization", "").strip()
    expected = f"Bearer {WEB_API_SECRET}"
    if len(auth) != len(expected):
        return False
    return hmac.compare_digest(auth, expected)


@routes.get('/')
async def index(request):
    """Renderiza a página inicial."""
    return aiohttp_jinja2.render_template('index.html', request, {})

@routes.get('/api/stats')
async def api_stats(request):
    """API JSON para atualizar status via AJAX."""
    if not _check_api_auth(request):
        raise web.HTTPForbidden(text="API protegida: defina Authorization: Bearer ou WEB_API_SECRET.")
    last_scan = stats.last_scan_time.isoformat() if stats.last_scan_time else "Never"
    return web.json_response({
        "uptime": stats.format_uptime(),
        "scans": stats.scans_completed,
        "news_posted": stats.news_posted,
        "cache_hits": stats.cache_hits_total,
        "last_scan": last_scan
    })

async def start_web_server(host='127.0.0.1', port=8080):
    """Inicia o servidor web aiohttp."""
    try:
        app = web.Application()
        
        # Configura templates
        template_dir = p("web/templates")
        if not os.path.exists(template_dir):
            os.makedirs(template_dir, exist_ok=True)
            
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(template_dir))
        
        app.add_routes(routes)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        
        log.info(f"🌍 Web Dashboard iniciado em http://{host}:{port}")
        await site.start()
    except Exception as e:
        log.error(f"Falha ao iniciar Web Server: {e}")
