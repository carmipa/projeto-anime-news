FROM python:3.10-slim

# Metadata
LABEL maintainer="Paulo André Carminati"
LABEL description="Anime News Discord Bot - AnimeBootNews System"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Diretório de trabalho
WORKDIR /app

# Instala dependências do sistema (necessárias para certifi e SSL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements primeiro (melhor cache de layers)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia código do bot
# Copia todo o código do projeto
COPY . .

# Cria diretórios para dados persistentes (serão volumes) e um usuário não-root.
# UID/GID 1000 para compatibilidade com bind mounts do host (o primeiro usuário
# Linux costuma ser 1000). Se os arquivos montados do host tiverem outro dono,
# ajuste a propriedade no host ou use volumes nomeados.
RUN mkdir -p /app/data /app/logs \
    && groupadd -g 1000 appuser \
    && useradd -m -u 1000 -g appuser appuser \
    && chown -R appuser:appuser /app

# Roda como usuário não-root (segurança: evita root dentro do container)
USER appuser

# Healthcheck real: prova de vida do processo (resposta HTTP do dashboard) ou,
# com o dashboard desligado, idade da última varredura. O anterior testava se
# /app/config.json existia — um volume, portanto sempre presente: dizia
# "healthy" mesmo com o bot travado.
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]

# Comando de execução
CMD ["python", "-u", "main.py"]
