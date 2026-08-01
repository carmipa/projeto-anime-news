"""
Status cog - /status command to show bot statistics.
"""
from datetime import datetime

import discord
from discord.ext import commands
from discord import app_commands

from core.stats import stats
from settings import LOOP_MINUTES


class StatusCog(commands.Cog):
    """Cog com comando de status do bot."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="status", description="Mostra estatísticas do bot AnimeBootNews.")
    async def status(self, interaction: discord.Interaction):
        """
        PROPÓSITO DE NEGÓCIO: dar ao administrador do servidor a saúde real do
        bot num relance — se está a varrer, quando varreu e quando volta.

        INVARIANTES DO DOMÍNIO:
        - "Próxima varredura" tem de vir do agendador de facto. Antes era
          `agora + LOOP_MINUTES` calculado na hora do comando, ou seja, dizia
          sempre "daqui a 12 horas" mesmo que a varredura fosse dali a um
          minuto — informação errada com cara de precisa.

        COMPORTAMENTO EM CASO DE FALHA: sem agendador vivo, mostra "agendador
        parado" em vez de inventar um horário; o comando nunca levanta.
        """
        from core.scanner import loop_task

        next_iteration = getattr(loop_task, "next_iteration", None) if loop_task else None
        if next_iteration:
            next_scan_str = f"<t:{int(next_iteration.timestamp())}:R>"
        else:
            next_scan_str = "⚠️ agendador parado"

        embed = discord.Embed(
            title="🛰️ Status do AnimeBootNews Bot",
            color=discord.Color.from_rgb(255, 0, 32),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="⏰ Uptime",
            value=stats.format_uptime(),
            inline=True
        )
        
        embed.add_field(
            name="📡 Varreduras",
            value=f"{stats.scans_completed}",
            inline=True
        )
        
        embed.add_field(
            name="📰 Notícias Enviadas",
            value=f"{stats.news_posted}",
            inline=True
        )
        
        embed.add_field(
            name="📦 Cache Hits Total",
            value=f"{stats.cache_hits_total}",
            inline=True
        )

        embed.add_field(
            name="⚠️ Fontes com falha",
            value=f"{stats.errors_count}",
            inline=True
        )
        
        if stats.last_scan_time:
            last_scan_str = f"<t:{int(stats.last_scan_time.timestamp())}:R>"
        else:
            # Fallback: Check persisted state
            try:
                from utils.cache import load_http_state
                state = load_http_state()
                if "_meta" in state and "last_scan" in state["_meta"]:
                    dt = datetime.fromisoformat(state["_meta"]["last_scan"])
                    last_scan_str = f"<t:{int(dt.timestamp())}:R>"
                else:
                    last_scan_str = "Nenhuma ainda"
            except Exception:
                last_scan_str = "Nenhuma ainda"
        
        embed.add_field(
            name="🕐 Última Varredura",
            value=last_scan_str,
            inline=True
        )
        
        embed.add_field(
            name="⏳ Próxima Varredura",
            value=next_scan_str,
            inline=True
        )
        
        embed.set_footer(text=f"Bot v2.1 | Intervalo: {LOOP_MINUTES} min")
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Setup function para carregar o cog."""
    await bot.add_cog(StatusCog(bot))
