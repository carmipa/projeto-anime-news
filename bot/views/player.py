"""
Player view - Contains buttons for media playback.
"""
import discord

class WatchView(discord.ui.View):
    """
    View com botão de 'Assistir' (Link Button).
    Usada para acompanhar posts de vídeo.
    """
    def __init__(self, url: str):
        super().__init__(timeout=None)
        
        self.add_item(discord.ui.Button(
            label="Assistir Agora / Watch Now",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="▶️"
        ))
