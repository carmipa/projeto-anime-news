"""
Admin cog - Administrative commands (/forcecheck).
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging  # Necessário para logging.ERROR

from utils.logger import log, log_with_context
from utils.security import scan_rate_limiter, config_rate_limiter, log_security_event
from utils.audit import audit_logger, AuditEventType, AuditSeverity
from utils.exceptions import RateLimitError, SecurityError

# log = logging.getLogger("AnimeBootNews")


class AdminCog(commands.Cog):
    """Cog com comandos administrativos."""
    
    def __init__(self, bot, run_scan_once_func):
        self.bot = bot
        self.run_scan_once = run_scan_once_func
    
    @app_commands.command(name="forcecheck", description="Força varredura imediata de feeds.")
    @app_commands.checks.has_permissions(administrator=True)
    async def forcecheck(self, interaction: discord.Interaction):
        """Força uma varredura imediata sem abrir o dashboard."""
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        
        try:
            # Rate limiting
            allowed, retry_after = await scan_rate_limiter.is_allowed(f"{guild_id}:{user_id}")
            if not allowed:
                log_security_event(
                    "RATE_LIMIT_EXCEEDED",
                    user_id=user_id,
                    guild_id=guild_id,
                    details={"command": "forcecheck", "retry_after": retry_after},
                    severity="WARNING"
                )
                audit_logger.log(
                    AuditEventType.RATE_LIMIT_EXCEEDED,
                    severity=AuditSeverity.WARNING,
                    user_id=user_id,
                    guild_id=guild_id,
                    details={"command": "forcecheck"}
                )
                await interaction.response.send_message(
                    f"⏳ Rate limit excedido. Tente novamente em {int(retry_after)}s.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            # Audit log
            audit_logger.log(
                AuditEventType.SCAN_STARTED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                guild_id=guild_id,
                details={"trigger": "forcecheck"}
            )
            
            await self.run_scan_once(trigger="forcecheck")
            
            audit_logger.log(
                AuditEventType.SCAN_COMPLETED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                guild_id=guild_id,
                details={"trigger": "forcecheck"}
            )
            
            await interaction.followup.send("✅ Varredura forçada concluída!", ephemeral=True)
        
        except RateLimitError as e:
            log_with_context(
                log,
                logging.ERROR,
                f"Rate limit em /forcecheck: {e}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="RATE_LIMIT_ERROR"
            )
            try:
                await interaction.followup.send("⏳ Muitas requisições. Aguarde um momento.", ephemeral=True)
            except (discord.NotFound, discord.HTTPException) as e:
                log.debug(f"⚠️ [ADMIN] Erro ao enviar mensagem de rate limit: {e}")
            except Exception as e:
                log.warning(f"⚠️ [ADMIN] Erro inesperado ao enviar mensagem: {e}")
        
        except Exception as e:
            log_with_context(
                log,
                logging.ERROR,
                f"Erro em /forcecheck: {e}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="COMMAND_ERROR",
                exc_info=e
            )
            audit_logger.log(
                AuditEventType.ERROR_OCCURRED,
                severity=AuditSeverity.ERROR,
                user_id=user_id,
                guild_id=guild_id,
                details={"command": "forcecheck", "error": str(e)}
            )
            try:
                await interaction.followup.send("❌ Falha ao executar varredura.", ephemeral=True)
            except (discord.NotFound, discord.HTTPException) as e:
                log.debug(f"⚠️ [ADMIN] Erro ao enviar mensagem de erro: {e}")
            except Exception as e:
                log.warning(f"⚠️ [ADMIN] Erro inesperado ao enviar mensagem de erro: {e}")
    
    @forcecheck.error
    async def forcecheck_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Trata erros do comando /forcecheck."""
        user_id = interaction.user.id if interaction.user else None
        guild_id = interaction.guild_id
        
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Você precisa ter **Administrador** para usar este comando."
            
            # Audit log
            audit_logger.log(
                AuditEventType.PERMISSION_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                guild_id=guild_id,
                details={"command": "forcecheck"}
            )
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except discord.NotFound:
                pass
            return
        
        log_with_context(
            log,
            logging.ERROR,
            f"Erro no comando /forcecheck: {error}",
            user_id=user_id,
            guild_id=guild_id,
            event_type="COMMAND_ERROR",
            exc_info=error
        )

    @app_commands.command(name="set_canal", description="Define este canal atual para receber as notícias.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_canal(self, interaction: discord.Interaction):
        """
        Define o canal atual como destino das notícias para este servidor.
        """
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id
        
        try:
            # Rate limiting
            allowed, retry_after = await config_rate_limiter.is_allowed(f"{guild_id}:{user_id}")
            if not allowed:
                audit_logger.log(
                    AuditEventType.RATE_LIMIT_EXCEEDED,
                    severity=AuditSeverity.WARNING,
                    user_id=user_id,
                    guild_id=guild_id,
                    details={"command": "set_canal"}
                )
                await interaction.response.send_message(
                    f"⏳ Rate limit excedido. Tente novamente em {int(retry_after)}s.",
                    ephemeral=True
                )
                return
            
            # Validação
            from utils.security import validate_channel_id, validate_guild_id
            from utils.storage import p, load_json_safe, save_json_safe
            
            guild_id_str = validate_guild_id(str(guild_id))
            validated_channel_id = validate_channel_id(channel_id)
            
            # Load config
            cfg = load_json_safe(p("config.json"), {})
            
            # Ensure structure
            if guild_id_str not in cfg:
                cfg[guild_id_str] = {}
            
            old_channel = cfg[guild_id_str].get("channel_id")
            
            # Update Channel ID
            cfg[guild_id_str]["channel_id"] = validated_channel_id
            
            # Ensure default filters if empty
            if "filters" not in cfg[guild_id_str]:
                cfg[guild_id_str]["filters"] = []
            
            save_json_safe(p("config.json"), cfg)
            
            # Audit log
            audit_logger.log(
                AuditEventType.CHANNEL_CHANGED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                guild_id=guild_id,
                details={
                    "old_channel": old_channel,
                    "new_channel": validated_channel_id,
                    "channel_name": interaction.channel.name
                }
            )
            
            log_with_context(
                log,
                logging.INFO,
                f"Canal de notícias definido: {validated_channel_id}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="CONFIG_CHANGED"
            )
            
            await interaction.response.send_message(
                f"✅ Canal {interaction.channel.mention} configurado com sucesso para receber notícias!",
                ephemeral=True
            )
        
        except Exception as e:
            log_with_context(
                log,
                logging.ERROR,
                f"Erro em /set_canal: {e}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="COMMAND_ERROR",
                exc_info=e
            )
            audit_logger.log(
                AuditEventType.ERROR_OCCURRED,
                severity=AuditSeverity.ERROR,
                user_id=user_id,
                guild_id=guild_id,
                details={"command": "set_canal", "error": str(e)}
            )
            try:
                await interaction.response.send_message(
                    "❌ Erro ao configurar canal. Verifique os logs.",
                    ephemeral=True
                )
            except (discord.NotFound, discord.HTTPException) as e:
                log.debug(f"⚠️ [ADMIN] Erro ao enviar mensagem de erro: {e}")
            except Exception as e:
                log.warning(f"⚠️ [ADMIN] Erro inesperado ao enviar mensagem de erro: {e}")

    @set_canal.error
    async def set_canal_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        user_id = interaction.user.id if interaction.user else None
        guild_id = interaction.guild_id
        
        if isinstance(error, app_commands.MissingPermissions):
            audit_logger.log(
                AuditEventType.PERMISSION_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                guild_id=guild_id,
                details={"command": "set_canal"}
            )
            await interaction.response.send_message(
                "❌ Você precisa de permissão **Gerenciar Canais** para usar este comando.",
                ephemeral=True
            )
        else:
            log_with_context(
                log,
                logging.ERROR,
                f"Erro no comando /set_canal: {error}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="COMMAND_ERROR",
                exc_info=error
            )


async def setup(bot, run_scan_once_func):
    """
    Setup function para carregar o cog.
    
    Args:
        bot: Instância do bot Discord
        run_scan_once_func: Função de scan a ser injetada
    """
    await bot.add_cog(AdminCog(bot, run_scan_once_func))
