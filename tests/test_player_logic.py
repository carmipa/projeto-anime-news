"""
Helpers de midia (YouTube) e resolucao de imagem pela PRODUCAO.

Por que este ficheiro foi reescrito em 2026-09-18: duas das tres funcoes de
teste diziam `# Simulated logic from scanner.py` e reimplementavam a decisao
DENTRO do proprio teste. Elas passavam sem nunca tocar no scanner -- apagar a
logica de producao nao as deixaria vermelhas. E o defeito exato que a
regra-medicao-perguntar-a-producao §1 nomeia: criterio que o codigo de
producao ja implementa deve ser CONSULTADO, nunca copiado.

O que se perdeu ao remover a simulacao, declarado em vez de fingido: a decisao
`embed_url = None if is_media else link` e inline dentro de run_scan_once e nao
ha funcao para consultar. Extrai-la seria refatoracao fora do escopo desta
correcao, entao ela fica como NAO COBERTA -- estado 2, que nao e aprovacao --
e nao como teste verde que nao mede nada.
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scanner import (  # noqa: E402
    _classify_entry_type,
    _extract_youtube_id,
    _get_youtube_thumbnail,
    _normalize_youtube_url,
    _resolve_image_url,
)


class _SessaoQueAcusa:
    """Qualquer GET aqui e falha do teste: prova que a rede NAO foi tocada."""

    def __init__(self):
        self.pedidas = []

    def get(self, url, **kw):
        self.pedidas.append(url)
        raise AssertionError(f"nao devia ter buscado nada, buscou: {url}")


class TestHelpersYouTube(unittest.TestCase):
    def test_extracao_de_id(self):
        self.assertEqual(_extract_youtube_id("https://www.youtube.com/watch?v=123"), "123")
        self.assertEqual(_extract_youtube_id("https://youtu.be/abc"), "abc")
        self.assertEqual(_extract_youtube_id("https://www.youtube.com/shorts/xyz"), "xyz")

    def test_normalizacao_de_shorts(self):
        self.assertEqual(
            _normalize_youtube_url("https://www.youtube.com/shorts/xyz"),
            "https://www.youtube.com/watch?v=xyz",
        )

    def test_thumbnail_pelo_id(self):
        self.assertEqual(
            _get_youtube_thumbnail("https://youtu.be/123"),
            "https://img.youtube.com/vi/123/hqdefault.jpg",
        )


class TestResolucaoDeImagemNaProducao(unittest.TestCase):
    """
    Chama _resolve_image_url de verdade -- e o que a simulacao antiga nao fazia.
    Apagar a linha do fallback de YouTube no scanner deixa isto vermelho.
    """

    def test_video_do_youtube_usa_a_thumb_do_id_sem_rede(self):
        sessao = _SessaoQueAcusa()
        url = asyncio.run(_resolve_image_url(
            SimpleNamespace(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "", sessao, None
        ))
        self.assertEqual(url, "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg")
        self.assertEqual(sessao.pedidas, [], "YouTube resolve pelo id: nao pode gastar requisicao")

    def test_noticia_textual_com_imagem_no_feed_tambem_dispensa_rede(self):
        sessao = _SessaoQueAcusa()
        url = asyncio.run(_resolve_image_url(
            SimpleNamespace(media_thumbnail=[{"url": "https://cdn.exemplo.com/capa.jpg"}]),
            "https://exemplo.com/noticia/123", "", sessao, None
        ))
        self.assertEqual(url, "https://cdn.exemplo.com/capa.jpg")
        self.assertEqual(sessao.pedidas, [])


# TestClassificacaoDeEntrada foi RETIRADO antes de entrar: o gabarito que eu
# escrevi ("Trailer oficial" -> "video") reprovou contra a producao, que
# classifica como "launch". Sem requisito escrito que fundamente qual dos dois
# e o certo, o esperado nasceria da propria implementacao sob avaliacao -- e a
# regra 25/A3 chama isso de gabarito inventado, que vale menos que nenhum.
# Classificacao de tipo de entrada tambem esta fora do escopo desta correcao
# (imagem da noticia). Fica declarado como NAO VERIFICADO, nao como coberto.

if __name__ == "__main__":
    unittest.main()
