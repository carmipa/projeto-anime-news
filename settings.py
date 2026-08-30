# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

# Obrigatório
TOKEN = os.getenv("DISCORD_TOKEN")

# Operação (opcional via env)
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
try:
    LOOP_MINUTES = int(os.getenv("LOOP_MINUTES", "720"))
except ValueError:
    LOOP_MINUTES = 720

# Quantos feeds buscar/parsear em paralelo por varredura (bounded).
# Default 3 (não 8): evasão de rate-limit por IP. Bater 8 feeds ao mesmo tempo no
# mesmo provedor (YouTube) é o que dispara o bloqueio do IP de datacenter da VPS —
# medido no bot irmão. Concorrência baixa + jitter espalha as requisições.
try:
    FEED_CONCURRENCY = int(os.getenv("FEED_CONCURRENCY", "3"))
except ValueError:
    FEED_CONCURRENCY = 3
if FEED_CONCURRENCY < 1:
    FEED_CONCURRENCY = 1

# Jitter aleatório (segundos) antes de cada fetch, dentro do semáforo: espalha as
# requisições no tempo em vez de dispará-las em rajada. Portado do gundam.
try:
    FEED_JITTER_MIN = float(os.getenv("FEED_JITTER_MIN", "0.5"))
except ValueError:
    FEED_JITTER_MIN = 0.5
try:
    FEED_JITTER_MAX = float(os.getenv("FEED_JITTER_MAX", "2.5"))
except ValueError:
    FEED_JITTER_MAX = 2.5
FEED_JITTER_MIN = max(0.0, FEED_JITTER_MIN)
FEED_JITTER_MAX = max(FEED_JITTER_MIN, FEED_JITTER_MAX)

# Proxy de saída (Cloudflare Worker): rota o fetch para fora do IP de datacenter,
# que fontes como Siliconera/YouTube bloqueiam. A URL do worker é prefixada à URL
# do feed; o segredo viaja em X-Proxy-Secret só quando de fato roteando (não vaza
# para a origem). Vazio = busca direta. Só as fontes com "use_proxy": true no
# cadastro (ou de domínio candidato) são roteadas — não sobrecarrega o worker.
CLOUDFLARE_PROXY_URL = os.getenv("CLOUDFLARE_PROXY_URL", "").strip()
CLOUDFLARE_PROXY_SECRET = os.getenv("CLOUDFLARE_PROXY_SECRET", "").strip()

# Teto de publicações por fonte em cada varredura. Um canal que sobe 15 vídeos
# num dia não pode ocupar o canal sozinho; o resto fica para a rodada seguinte
# (o feed vem do mais recente para o mais antigo, e a janela é de 24h).
# 0 = sem limite.
try:
    MAX_ITENS_POR_FONTE = int(os.getenv("MAX_ITENS_POR_FONTE", "5"))
except ValueError:
    MAX_ITENS_POR_FONTE = 5
if MAX_ITENS_POR_FONTE < 0:
    MAX_ITENS_POR_FONTE = 0

# Web dashboard (segurança: por padrão só localhost; em Docker use WEB_HOST=0.0.0.0 com cuidado)
WEB_ENABLED = os.getenv("WEB_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
try:
    WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
except ValueError:
    WEB_PORT = 8080
# Se definido, /api/stats exige header: Authorization: Bearer <segredo>
WEB_API_SECRET = os.getenv("WEB_API_SECRET", "").strip() or None
