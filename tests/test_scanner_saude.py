"""
Testes de saúde do scanner e do cadastro de fontes.

Cobrem os três defeitos que a auditoria de 2026-08-01 encontrou e que nenhum
log denunciava: agendador duplicado por reconexão, feed descartado por `bozo`
mesmo trazendo entradas, e fonte cadastrada sem nome confirmado.
"""
import asyncio
import json

import feedparser
import pytest

from core import scanner, sources


# =========================================================
# AGENDADOR
# =========================================================

def test_start_scheduler_e_idempotente():
    """
    O `@tasks.loop` é declarado dentro de start_scheduler, logo cada chamada
    fabricava um Loop novo. Como `on_ready` corre outra vez a cada reconexão do
    gateway, o bot acumulava agendadores — medido: 2 chamadas = 2 loops ativos.
    """
    import discord

    async def cenario():
        bot = discord.Client(intents=discord.Intents.default())
        primeiro = scanner.start_scheduler(bot)
        segundo = scanner.start_scheduler(bot)
        try:
            assert primeiro is segundo, "segunda chamada criou um agendador novo"
            assert primeiro.is_running()
            ativos = [t for t in asyncio.all_tasks() if "intelligence_gathering" in repr(t)]
            assert len(ativos) <= 1, f"{len(ativos)} loops de varredura ativos"
        finally:
            primeiro.cancel()
            scanner.loop_task = None

    asyncio.run(cenario())


# =========================================================
# TOLERÂNCIA A FEED MALFORMADO
# =========================================================

# XML com namespace não declarado: o feedparser liga `bozo` e mesmo assim
# devolve a entrada. É o caso típico que fazia o feed inteiro desaparecer.
FEED_MALFORMADO = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Feed Torto</title>
    <item>
      <title>Nova temporada de anime anunciada</title>
      <link>https://exemplo.test/noticia</link>
      <dc:creator>sem namespace declarado</dc:creator>
    </item>
  </channel>
</rss>"""


def test_feedparser_marca_bozo_mas_devolve_entradas():
    """Premissa do teste seguinte: sem isto, o resto não prova nada."""
    feed = feedparser.parse(FEED_MALFORMADO)
    assert feed.bozo, "o XML de exemplo deixou de ser malformado"
    assert len(feed.entries) == 1


class _RespostaFalsa:
    status = 200
    headers: dict = {}

    async def read(self):
        return FEED_MALFORMADO

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _SessaoFalsa:
    def get(self, *args, **kwargs):
        return _RespostaFalsa()


def test_feed_bozo_com_entradas_e_aproveitado():
    url = "https://exemplo.test/feed"
    _, feed = asyncio.run(scanner._fetch_and_parse(_SessaoFalsa(), url, {}, None))
    assert feed is not None, "feed com entradas válidas foi descartado por bozo"
    assert feed is not scanner._CACHE_HIT
    assert feed.entries[0].title == "Nova temporada de anime anunciada"


# =========================================================
# CADASTRO DE FONTES
# =========================================================

def test_load_sources_respeita_enabled_e_deduplica(tmp_path, monkeypatch):
    dados = {
        "youtube_feeds": {
            "a": [
                {"url": "https://x.test/1", "name": "Um"},
                {"url": "https://x.test/2", "name": "Dois", "enabled": False},
                "https://x.test/3",
            ],
            "b": [{"url": "https://x.test/1", "name": "Um (repetido)"}],
        }
    }
    ficheiro = tmp_path / "sources.json"
    ficheiro.write_text(json.dumps(dados), encoding="utf-8")
    monkeypatch.setattr(sources, "p", lambda _: str(ficheiro))
    sources._CACHE = None

    try:
        urls = sources.load_sources()
        assert urls == ["https://x.test/1", "https://x.test/3"]
        meta = sources.load_source_meta()
        assert meta["https://x.test/1"]["name"] == "Um", "vence a primeira ocorrência"
        assert meta["https://x.test/3"]["enabled"] is True, "string solta é ativa por omissão"
        assert meta["https://x.test/3"]["untrusted"] is False, "string solta é confiável"
    finally:
        sources._CACHE = None


def test_toda_fonte_do_projeto_tem_nome_confirmado():
    """
    GUARDA: nenhum channel_id entra no sources.json sem o nome real do canal ao
    lado. Foi por cadastrar IDs "às cegas" e documentá-los em comentário errado
    que TOHO animation, WIT STUDIO, KADOKAWAanime e Crunchyroll acabaram
    tratados como canais de games. O nome tem de vir do título do próprio feed.
    """
    sources._CACHE = None
    sem_nome = [u for u, m in sources.load_source_meta().items() if not m.get("name")]
    assert not sem_nome, (
        "fontes sem 'name' no sources.json (confirme o nome pelo título do feed):\n"
        + "\n".join(f"  - {u}" for u in sem_nome)
    )


def test_fontes_removidas_nao_voltam_por_engano():
    """As fontes retiradas ficam documentadas com o motivo, não apagadas em silêncio."""
    from utils.storage import p as caminho
    with open(caminho("sources.json"), "r", encoding="utf-8") as f:
        bruto = json.load(f)

    removidas = bruto.get("_removidas", {})
    assert removidas, "o registo do que foi removido (e porquê) desapareceu"

    sources._CACHE = None
    ativas = set(sources.load_source_meta())
    voltaram = ativas & set(removidas)
    assert not voltaram, f"fonte removida por defeito voltou ao cadastro: {voltaram}"
