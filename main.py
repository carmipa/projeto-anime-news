# =========================================================
# AnimeBootNews Bot v1.0
# main.py (Modularized)
# =========================================================

# ---------------------------------------------------------
# PREFLIGHT DE AMBIENTE — antes de qualquer import de terceiros.
#
# PROPÓSITO DE NEGÓCIO: dizer em português o que falta instalar, em vez de
# morrer com um ModuleNotFoundError cru. Nesta máquina o `python` do PATH é o
# 3.14 e não tem NENHUMA dependência do bot; só a .venv funciona. Quem roda
# `python main.py` fora da venv leva um traceback que não explica nada.
#
# INVARIANTES DO DOMÍNIO: usa só a biblioteca padrão e roda antes de tudo —
# um import de terceiros acima desta secção anula a verificação.
#
# COMPORTAMENTO EM CASO DE FALHA: imprime o interpretador em uso, a lista do
# que falta e o comando exato de correção, e sai com código 1.
# ---------------------------------------------------------
import importlib.util
import sys

_DEPENDENCIAS = [
    ("discord", "discord.py"),
    ("aiohttp", "aiohttp"),
    ("aiohttp_jinja2", "aiohttp-jinja2"),
    ("jinja2", "jinja2"),
    ("feedparser", "feedparser"),
    ("dotenv", "python-dotenv"),
    ("certifi", "certifi"),
    ("colorlog", "colorlog"),
    ("bs4", "beautifulsoup4"),
]

_faltando = [pip for mod, pip in _DEPENDENCIAS if importlib.util.find_spec(mod) is None]
if _faltando:
    print("=" * 70)
    print("AnimeBootNews nao pode iniciar: faltam dependencias.")
    print(f"Interpretador em uso: {sys.executable}")
    print(f"Versao: {sys.version.split()[0]}")
    print(f"Faltando: {', '.join(_faltando)}")
    print("-" * 70)
    if sys.platform == "win32":
        print("Corrija com:   .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        print("Ou rode com:   .venv\\Scripts\\python.exe main.py")
    else:
        print("Corrija com:   python -m pip install -r requirements.txt")
    print("=" * 70)
    sys.exit(1)

import logging
import asyncio
import discord
import os
from logging.handlers import RotatingFileHandler
from discord.ext import commands

from settings import TOKEN, COMMAND_PREFIX, WEB_ENABLED, WEB_HOST, WEB_PORT
from utils.logger import log, setup_logger # Adjusted to reuse existing logger if possible, but implementing rotation manually here for robustness

# Setup Advanced Logging with Rotation
os.makedirs("logs", exist_ok=True)
formatter = logging.Formatter("%(asctime)s - [%(levelname)s] - %(message)s")
file_handler = RotatingFileHandler("logs/bot.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
file_handler.setFormatter(formatter)

# Attach to the existing colorlog logger
log.addHandler(file_handler)

from utils.storage import p, load_json_safe
from bot.views.filter_dashboard import FilterDashboard
from core.scanner import start_scheduler, run_scan_once
from web.server import start_web_server
from utils.config_validator import ConfigValidator
from utils.security import validate_discord_token
from utils.audit import audit_logger, AuditEventType, AuditSeverity
from utils.exceptions import ConfigurationError


# Configuração de Logs - REMOVIDO (Centralizado em utils.logger)
# logging.basicConfig(...) 
# log = logging.getLogger("AnimeBootNews")


# =========================================================
# SETUP DO BOT
# =========================================================

async def main():
    # Intents
    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True

    # Bot Instance
    bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

    # =========================================================
    # EVENTOS
    # =========================================================
    
    @bot.command()
    @commands.is_owner()
    async def sync(ctx):
        """Comando manual para sincronizar comandos Slash."""
        try:
            # Sync global
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Sincronizado {len(synced)} comandos globalmente.")
            
            # Sync na guild atual também (garantia)
            if ctx.guild:
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced_guild = await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ Sincronizado {len(synced_guild)} comandos na guild: {ctx.guild.name}")
        except Exception as e:
            await ctx.send(f"❌ Erro ao sincronizar: {e}")

    @bot.event
    async def on_ready():
        log.info(f"✅ Bot conectado como: {bot.user} (ID: {bot.user.id})")
        
        # Audit log - Bot iniciado
        audit_logger.log(
            AuditEventType.BOT_STARTED,
            severity=AuditSeverity.INFO,
            details={"bot_id": bot.user.id, "bot_name": str(bot.user)}
        )
        
        # Validar configuração na inicialização
        try:
            validation_results = ConfigValidator.validate_all()
            if validation_results["errors"]:
                log.warning(f"⚠️ Avisos de validação: {validation_results['errors']}")
            else:
                log.info("✅ Configuração validada com sucesso")
        except Exception as e:
            log.error(f"❌ Erro ao validar configuração: {e}")
            audit_logger.log(
                AuditEventType.ERROR_OCCURRED,
                severity=AuditSeverity.ERROR,
                details={"error": "config_validation_failed", "message": str(e)}
            )
        
        # Web dashboard (127.0.0.1 por padrão — ver settings WEB_HOST / WEB_ENABLED)
        if WEB_ENABLED:
            await start_web_server(host=WEB_HOST, port=WEB_PORT)
        else:
            log.info("🌐 Web dashboard desligado (WEB_ENABLED=false).")
        
        # Registrar Views Persistentes
        cfg = load_json_safe(p("config.json"), {})
        if isinstance(cfg, dict):
            for gid in cfg.keys():
                try:
                    bot.add_view(FilterDashboard(int(gid)))
                    log.info(f"View persistente registrada para guild {gid}")
                    audit_logger.log(
                        AuditEventType.COG_LOADED,
                        severity=AuditSeverity.INFO,
                        guild_id=int(gid),
                        details={"component": "FilterDashboard"}
                    )
                except Exception as e:
                    log.error(f"Erro view guild {gid}: {e}")
                    audit_logger.log(
                        AuditEventType.COG_FAILED,
                        severity=AuditSeverity.ERROR,
                        guild_id=int(gid),
                        details={"component": "FilterDashboard", "error": str(e)}
                    )

        # 2. Sync Comandos (Slash)
        try:
            # Sincroniza global (pode demorar) ou por guild
            # Para dev, sync por guild é mais rápido e garante update imediato
            # IMPORTANTE: É necessário copiar os globais para a guild antes de syncar a guild
            for guild in bot.guilds:
                bot.tree.copy_global_to(guild=discord.Object(id=guild.id))
                synced = await bot.tree.sync(guild=discord.Object(id=guild.id))
                log.info(f"Comandos sincronizados (copy_global) em: {guild.name} ({len(synced)} comandos)")
                audit_logger.log(
                    AuditEventType.COG_LOADED,
                    severity=AuditSeverity.INFO,
                    guild_id=guild.id,
                    details={"component": "slash_commands", "count": len(synced)}
                )
        except Exception as e:
            log.error(f"Falha no sync de comandos: {e}")
            audit_logger.log(
                AuditEventType.COG_FAILED,
                severity=AuditSeverity.ERROR,
                details={"component": "slash_commands", "error": str(e)}
            )

        # 3. Iniciar Loop de Scanner
        start_scheduler(bot)

    # =========================================================
    # CARREGAR COGS
    # =========================================================
    
    # Função wrapper para injetar o bot no run_scan_once
    # Isso permite que os comandos chamem o scan manualmente
    async def bound_scan(trigger="manual"):
        await run_scan_once(bot, trigger)

    try:
        # Carrega extensões normais (que têm setup(bot))
        await bot.load_extension("bot.cogs.status")
        await bot.load_extension("bot.cogs.info")
        await bot.load_extension("bot.cogs.audit")  # Comandos de auditoria
        
        # Admin e Dashboard precisam da função de scan injetada
        # Como load_extension não aceita args, importamos e setup manual 
        # ou usamos uma abordagem de injeção. 
        # Simplificação: Passamos via bot instance ou setup manual.
        
        # Abordagem Híbrida: Carregar Status normalmente, e Admin/Dashboard manualmente
        from bot.cogs.admin import setup as setup_admin
        from bot.cogs.dashboard import setup as setup_dashboard
        
        await setup_admin(bot, bound_scan)
        await setup_dashboard(bot, bound_scan)
        
        log.info("🧩 Cogs carregados com sucesso.")
        audit_logger.log(
            AuditEventType.COG_LOADED,
            severity=AuditSeverity.INFO,
            details={"component": "all_cogs", "status": "success"}
        )
    except Exception as e:
        log.exception(f"Falha ao carregar cogs: {e}")
        audit_logger.log(
            AuditEventType.COG_FAILED,
            severity=AuditSeverity.CRITICAL,
            details={"component": "cogs_loading", "error": str(e)}
        )

    # =========================================================
    # START
    # =========================================================
    
    token = TOKEN.strip()
    
    # Validação de segurança do token
    if not validate_discord_token(token):
        log.error(f"❌ TOKEN INVÁLIDO! (Len: {len(token) if token else 0})")
        log.error("Por favor, verifique o arquivo .env e adicione um token válido do Discord.")
        audit_logger.log(
            AuditEventType.TOKEN_VALIDATION_FAILED,
            severity=AuditSeverity.CRITICAL,
            details={"token_length": len(token) if token else 0}
        )
        return
    
    log.info(f"🔑 Token carregado e validado. (Len: {len(token)})")
    await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("🛑 Bot encerrado pelo usuário.")
        audit_logger.log(
            AuditEventType.BOT_STOPPED,
            severity=AuditSeverity.INFO,
            details={"reason": "keyboard_interrupt"}
        )
    except Exception as e:
        log.exception(f"🔥 Erro fatal: {e}")
        audit_logger.log(
            AuditEventType.ERROR_OCCURRED,
            severity=AuditSeverity.CRITICAL,
            details={"error": "fatal_error", "message": str(e), "error_type": type(e).__name__}
        )