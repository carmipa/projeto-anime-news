"""
Audit cog - Comandos para visualizar logs de auditoria e estatísticas de segurança.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging

from utils.audit import audit_logger, AuditEventType, AuditSeverity
from utils.logger import log, log_with_context
from utils.security import check_discord_permissions


class AuditCog(commands.Cog):
    """Cog com comandos de auditoria."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="audit", description="Visualiza logs de auditoria e eventos de segurança.")
    @app_commands.describe(
        days="Número de dias para consultar (padrão: 7)",
        event_type="Tipo de evento específico",
        severity="Severidade mínima"
    )
    @app_commands.choices(
        event_type=[
            app_commands.Choice(name="Config Changed", value="CONFIG_CHANGED"),
            app_commands.Choice(name="Scan Started", value="SCAN_STARTED"),
            app_commands.Choice(name="Scan Completed", value="SCAN_COMPLETED"),
            app_commands.Choice(name="Rate Limit", value="RATE_LIMIT_EXCEEDED"),
            app_commands.Choice(name="Permission Denied", value="PERMISSION_DENIED"),
            app_commands.Choice(name="Error Occurred", value="ERROR_OCCURRED"),
        ],
        severity=[
            app_commands.Choice(name="Info", value="INFO"),
            app_commands.Choice(name="Warning", value="WARNING"),
            app_commands.Choice(name="Error", value="ERROR"),
            app_commands.Choice(name="Critical", value="CRITICAL"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def audit(
        self,
        interaction: discord.Interaction,
        days: Optional[int] = 7,
        event_type: Optional[str] = None,
        severity: Optional[str] = None
    ):
        """Visualiza eventos de auditoria."""
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        
        try:
            # Limita dias (máximo 30)
            days = min(max(days, 1), 30)
            
            # Consulta eventos
            since = datetime.now(timezone.utc) - timedelta(days=days)
            
            event_type_enum = None
            if event_type:
                try:
                    event_type_enum = AuditEventType[event_type]
                except KeyError:
                    await interaction.response.send_message(
                        f"❌ Tipo de evento inválido: {event_type}",
                        ephemeral=True
                    )
                    return
            
            severity_enum = None
            if severity:
                try:
                    severity_enum = AuditSeverity[severity]
                except KeyError:
                    await interaction.response.send_message(
                        f"❌ Severidade inválida: {severity}",
                        ephemeral=True
                    )
                    return
            
            events = audit_logger.query(
                event_type=event_type_enum,
                severity=severity_enum,
                guild_id=guild_id,
                since=since,
                limit=50
            )
            
            if not events:
                await interaction.response.send_message(
                    f"📋 Nenhum evento encontrado nos últimos {days} dias.",
                    ephemeral=True
                )
                return
            
            # Cria embed com resumo
            embed = discord.Embed(
                title="📊 Logs de Auditoria",
                description=f"Últimos {days} dias | {len(events)} eventos",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Agrupa por tipo
            by_type = {}
            for event in events:
                etype = event.get("event_type", "UNKNOWN")
                by_type[etype] = by_type.get(etype, 0) + 1
            
            # Mostra top 5 tipos
            sorted_types = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:5]
            type_list = "\n".join(f"• {k}: {v}" for k, v in sorted_types)
            embed.add_field(name="Por Tipo", value=type_list or "N/A", inline=False)
            
            # Últimos 5 eventos
            recent_events = events[-5:]
            recent_list = []
            for event in reversed(recent_events):
                timestamp = event.get("timestamp", "")[:10]  # Apenas data
                etype = event.get("event_type", "UNKNOWN")
                severity = event.get("severity", "INFO")
                recent_list.append(f"`{timestamp}` **{etype}** ({severity})")
            
            embed.add_field(
                name="Eventos Recentes",
                value="\n".join(recent_list) or "N/A",
                inline=False
            )
            
            embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Audit log da consulta
            audit_logger.log(
                AuditEventType.DATA_ACCESSED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                guild_id=guild_id,
                details={"query": {"days": days, "event_type": event_type, "severity": severity}}
            )
        
        except Exception as e:
            log_with_context(
                log,
                logging.ERROR,
                f"Erro em /audit: {e}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="COMMAND_ERROR",
                exc_info=e
            )
            try:
                await interaction.response.send_message(
                    "❌ Erro ao consultar auditoria. Verifique os logs.",
                    ephemeral=True
                )
            except (discord.NotFound, discord.HTTPException) as e:
                log.debug(f"⚠️ [AUDIT] Erro ao enviar mensagem de erro: {e}")
            except Exception as e:
                log.warning(f"⚠️ [AUDIT] Erro inesperado ao enviar mensagem de erro: {e}")
    
    @app_commands.command(name="audit_stats", description="Estatísticas de segurança e auditoria.")
    @app_commands.describe(days="Número de dias para analisar (padrão: 7)")
    @app_commands.checks.has_permissions(administrator=True)
    async def audit_stats(self, interaction: discord.Interaction, days: Optional[int] = 7):
        """Mostra estatísticas de auditoria."""
        user_id = interaction.user.id
        guild_id = interaction.guild_id
        
        try:
            days = min(max(days, 1), 30)
            stats = audit_logger.get_stats(days=days)
            
            embed = discord.Embed(
                title="📈 Estatísticas de Segurança",
                description=f"Análise dos últimos {days} dias",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Total de Eventos",
                value=f"{stats['total_events']}",
                inline=True
            )
            
            embed.add_field(
                name="Erros",
                value=f"{stats['errors']}",
                inline=True
            )
            
            embed.add_field(
                name="Avisos",
                value=f"{stats['warnings']}",
                inline=True
            )
            
            embed.add_field(
                name="Críticos",
                value=f"{stats['critical']}",
                inline=True
            )
            
            # Top 3 tipos de evento
            sorted_types = sorted(
                stats['by_type'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:3]
            
            if sorted_types:
                top_events = "\n".join(f"• {k}: {v}" for k, v in sorted_types)
                embed.add_field(name="Eventos Mais Comuns", value=top_events, inline=False)
            
            embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Audit log
            audit_logger.log(
                AuditEventType.DATA_ACCESSED,
                severity=AuditSeverity.INFO,
                user_id=user_id,
                guild_id=guild_id,
                details={"query": "stats", "days": days}
            )
        
        except Exception as e:
            log_with_context(
                log,
                logging.ERROR,
                f"Erro em /audit_stats: {e}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="COMMAND_ERROR",
                exc_info=e
            )
            try:
                await interaction.response.send_message(
                    "❌ Erro ao gerar estatísticas. Verifique os logs.",
                    ephemeral=True
                )
            except (discord.NotFound, discord.HTTPException) as e:
                log.debug(f"⚠️ [AUDIT] Erro ao enviar mensagem de erro: {e}")
            except Exception as e:
                log.warning(f"⚠️ [AUDIT] Erro inesperado ao enviar mensagem de erro: {e}")
    
    @audit.error
    @audit_stats.error
    async def audit_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Trata erros dos comandos de auditoria."""
        user_id = interaction.user.id if interaction.user else None
        guild_id = interaction.guild_id
        
        if isinstance(error, app_commands.MissingPermissions):
            audit_logger.log(
                AuditEventType.PERMISSION_DENIED,
                severity=AuditSeverity.WARNING,
                user_id=user_id,
                guild_id=guild_id,
                details={"command": "audit"}
            )
            await interaction.response.send_message(
                "❌ Você precisa ter permissão de **Administrador** para usar este comando.",
                ephemeral=True
            )
        else:
            log_with_context(
                log,
                logging.ERROR,
                f"Erro em comando de auditoria: {error}",
                user_id=user_id,
                guild_id=guild_id,
                event_type="COMMAND_ERROR",
                exc_info=error
            )


async def setup(bot):
    """Setup function para carregar o cog."""
    await bot.add_cog(AuditCog(bot))
