# =========================================================
# AnimeBootNews Bot v1.0
# main.py (Modularized)
# =========================================================

import logging
import asyncio
import discord
import os
from logging.handlers import RotatingFileHandler
from discord.ext import commands

from settings import TOKEN, COMMAND_PREFIX
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
from web.server import start_web_server  # Novo web server
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
        
        # Iniciar Web Server
        await start_web_server(port=8080)
        
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