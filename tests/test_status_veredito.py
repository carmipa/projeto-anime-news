"""
Guarda do /status: o veredito de saúde da varredura tem de aparecer no embed.

Sem esta guarda, o veredito ficaria só no log e no audit — invisível para o
administrador do servidor, que é quem precisa de ver "a última varredura foi
ANOMALIA" num relance. Exercita o callback real do comando.
"""
import asyncio
from unittest.mock import MagicMock, AsyncMock

import discord

from bot.cogs.status import StatusCog
from core.stats import stats


def _chamar_status():
    cog = StatusCog(MagicMock())
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    asyncio.run(StatusCog.status.callback(cog, interaction))
    return interaction.response.send_message.call_args.kwargs["embed"]


def _campo_saude(embed):
    for f in embed.fields:
        if "Saúde" in f.name:
            return f
    return None


def test_status_mostra_veredito_anomalia_em_vermelho():
    stats.ultimo_veredito = {
        "veredito": "ANOMALIA",
        "motivos": ["catálogo vazio: nenhuma fonte foi carregada"],
        "metricas": {},
        "quando": "2026-08-30T12:00:00",
    }
    embed = _chamar_status()
    campo = _campo_saude(embed)
    assert campo is not None, "o /status precisa mostrar o veredito da varredura"
    assert "ANOMALIA" in campo.value
    assert "catálogo vazio" in campo.value
    assert embed.color == discord.Color.red()


def test_status_mostra_veredito_ok_em_verde():
    stats.ultimo_veredito = {
        "veredito": "OK",
        "motivos": ["5 publicadas, 50 de 50 fontes entregaram"],
        "metricas": {},
        "quando": "2026-08-30T12:00:00",
    }
    embed = _chamar_status()
    campo = _campo_saude(embed)
    assert campo is not None
    assert "OK" in campo.value
    assert embed.color == discord.Color.green()


def test_status_sem_veredito_nao_quebra(monkeypatch, tmp_path):
    # Antes da 1ª varredura e sem state.json: o comando não pode levantar, e
    # simplesmente não mostra o campo de saúde.
    monkeypatch.chdir(tmp_path)
    stats.ultimo_veredito = None
    embed = _chamar_status()
    assert _campo_saude(embed) is None
