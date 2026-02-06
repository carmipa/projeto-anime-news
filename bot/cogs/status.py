"""
Status cog - /status command to show bot statistics.
"""
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta

from core.stats import stats
from settings import LOOP_MINUTES


class StatusCog(commands.Cog):
    """Cog com comando de status do bot."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="status", description="Mostra estatísticas do bot AnimeBootNews.")
    async def status(self, interaction: discord.Interaction):
        """Exibe estatísticas e status atual do bot."""
        # Calcula próxima varredura
        next_scan = datetime.now() + timedelta(minutes=LOOP_MINUTES)
        next_scan_ts = int(next_scan.timestamp())
        
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
            value=f"<t:{next_scan_ts}:R>",
            inline=True
        )
        
        embed.set_footer(text=f"Bot v2.1 | Intervalo: {LOOP_MINUTES} min")
        
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Setup function para carregar o cog."""
    await bot.add_cog(StatusCog(bot))
