"""
Admin cog - Administrative commands (/forcecheck).
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging

from utils.logger import log

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
        try:
            await interaction.response.defer(ephemeral=True)
            await self.run_scan_once(trigger="forcecheck")
            await interaction.followup.send("✅ Varredura forçada concluída!", ephemeral=True)
        except Exception as e:
            log.error(f"Erro em /forcecheck: {e}")
            try:
                await interaction.followup.send("❌ Falha ao executar varredura.", ephemeral=True)
            except:
                pass
    
    @forcecheck.error
    async def forcecheck_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Trata erros do comando /forcecheck."""
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Você precisa ter **Administrador** para usar este comando."
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except discord.NotFound:
                pass
            return
        
        log.exception("Erro no comando /forcecheck", exc_info=error)

    @app_commands.command(name="set_canal", description="Define este canal atual para receber as notícias.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_canal(self, interaction: discord.Interaction):
        """
        Define o canal atual como destino das notícias para este servidor.
        """
        guild_id = str(interaction.guild_id)
        channel_id = interaction.channel_id
        
        # Load config
        from utils.storage import p, load_json_safe, save_json_safe
        cfg = load_json_safe(p("config.json"), {})
        
        # Ensure structure
        if guild_id not in cfg:
            cfg[guild_id] = {}
            
        # Update Channel ID
        cfg[guild_id]["channel_id"] = channel_id
        
        # Ensure default filters if empty
        if "filters" not in cfg[guild_id]:
            cfg[guild_id]["filters"] = []
            
        save_json_safe(p("config.json"), cfg)
        
        log.info(f"Canal de notícias definido para guild {guild_id}: {channel_id} ({interaction.channel.name})")
        
        await interaction.response.send_message(
            f"✅ Canal {interaction.channel.mention} configurado com sucesso para receber notícias!",
            ephemeral=True
        )

    @set_canal.error
    async def set_canal_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Você precisa de permissão **Gerenciar Canais** para usar este comando.",
                ephemeral=True
            )
        else:
            log.exception("Erro no comando /set_canal", exc_info=error)


async def setup(bot, run_scan_once_func):
    """
    Setup function para carregar o cog.
    
    Args:
        bot: Instância do bot Discord
        run_scan_once_func: Função de scan a ser injetada
    """
    await bot.add_cog(AdminCog(bot, run_scan_once_func))
