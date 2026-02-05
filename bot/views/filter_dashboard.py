"""
FilterDashboard view - Interactive button panel for filter configuration.
"""
import discord
from typing import Dict, Any, List
import logging

from core.filters import FILTER_OPTIONS
from utils.storage import p, load_json_safe, save_json_safe

from utils.logger import log

# log = logging.getLogger("AnimeBot")


class FilterDashboard(discord.ui.View):
    """
    Painel persistente de filtros AnimeBot.
    Botões por categoria + botão de 'Ver filtros' + Reset.
    """
    
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = str(guild_id)
        self._rebuild()
    
    def _cfg(self) -> Dict[str, Any]:
        """Carrega config.json e garante estrutura mínima por guild."""
        cfg = load_json_safe(p("config.json"), {})
        if not isinstance(cfg, dict):
            log.error("config.json inválido. Recriando.")
            cfg = {}
        
        cfg.setdefault(self.guild_id, {"filters": [], "channel_id": None})
        
        if not isinstance(cfg[self.guild_id].get("filters"), list):
            cfg[self.guild_id]["filters"] = []
        
        return cfg
    
    def _save(self, cfg: Dict[str, Any]) -> None:
        save_json_safe(p("config.json"), cfg)
    
    def _filters(self) -> List[str]:
        cfg = self._cfg()
        return list(cfg[self.guild_id].get("filters", []))
    
    def _set_filters(self, new_filters: List[str]) -> None:
        cfg = self._cfg()
        cfg[self.guild_id]["filters"] = list(dict.fromkeys(new_filters))
        self._save(cfg)
    
    def _is_admin(self, interaction: discord.Interaction) -> bool:
        """Somente admin altera filtros."""
        try:
            return bool(interaction.user.guild_permissions.administrator)
        except Exception:
            return False
    
    def _rebuild(self) -> None:
        """Reconstrói botões conforme filtros ativos."""
        self.clear_items()
        active = set(self._filters())
        
        for key, (label, emoji) in FILTER_OPTIONS.items():
            is_active = key in active
            style = discord.ButtonStyle.success if is_active else discord.ButtonStyle.secondary
            
            btn = discord.ui.Button(
                label=label,
                emoji=emoji,
                style=style,
                custom_id=f"anime:filter:{self.guild_id}:{key}"
            )
            btn.callback = self._toggle_callback
            self.add_item(btn)
        
        show_btn = discord.ui.Button(
            label="Ver filtros",
            emoji="📌",
            style=discord.ButtonStyle.primary,
            custom_id=f"anime:show:{self.guild_id}"
        )
        show_btn.callback = self._show_callback
        self.add_item(show_btn)
        
        reset_btn = discord.ui.Button(
            label="Reset",
            emoji="🔄",
            style=discord.ButtonStyle.danger,
            custom_id=f"anime:reset:{self.guild_id}"
        )
        reset_btn.callback = self._reset_callback
        self.add_item(reset_btn)
    
    async def _toggle_callback(self, interaction: discord.Interaction):
        """Liga/desliga um filtro específico."""
        if not self._is_admin(interaction):
            await interaction.response.send_message(
                "❌ Apenas administradores podem alterar filtros.",
                ephemeral=True
            )
            return
        
        # Extrai categoria do custom_id: "anime:filter:123456:gunpla"
        parts = interaction.data.get("custom_id", "").split(":")
        if len(parts) < 4:
            await interaction.response.send_message("❌ Erro ao processar.", ephemeral=True)
            return
        
        category = parts[3]
        current = self._filters()
        
        if category in current:
            current.remove(category)
            msg = f"➖ **{category.capitalize()}** removido."
        else:
            current.append(category)
            msg = f"➕ **{category.capitalize()}** adicionado."
        
        self._set_filters(current)
        self._rebuild()
        
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(msg, ephemeral=True)
    
    async def _show_callback(self, interaction: discord.Interaction):
        """Mostra filtros ativos."""
        current = self._filters()
        if not current:
            await interaction.response.send_message(
                "📌 Nenhum filtro ativo. Todas as notícias estão bloqueadas.",
                ephemeral=True
            )
            return
        
        labels = [FILTER_OPTIONS.get(f, (f, ""))[0] for f in current]
        msg = "📌 **Filtros ativos:**\n" + "\n".join(f"• {lbl}" for lbl in labels)
        await interaction.response.send_message(msg, ephemeral=True)
    
    async def _reset_callback(self, interaction: discord.Interaction):
        """Reseta todos os filtros."""
        if not self._is_admin(interaction):
            await interaction.response.send_message(
                "❌ Apenas administradores podem resetar filtros.",
                ephemeral=True
            )
            return
        
        self._set_filters([])
        self._rebuild()
        
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🔄 Filtros resetados.", ephemeral=True)
