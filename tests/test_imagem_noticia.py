"""
Guardas da resolucao de imagem da noticia (feed -> OpenGraph -> embed).

CADA guarda nasce calibrada: um caso DOENTE que ela tem de reprovar e um caso
LEGITIMO QUE CARREGA O MESMO SINAL, que ela tem de aceitar (A1). Caso legitimo
distante prova que a guarda enxerga, nao que discrimina.

O defeito que originou tudo (medido em 2026-09-18 sobre os feeds reais):
animeanime.jp e animecorner.me nao publicam media:thumbnail, media:content,
enclosure nem <img> no summary, e as duas tem og:image por artigo. Sem o
fallback, toda noticia dessas fontes saia no Discord sem imagem.
"""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scanner import (  # noqa: E402
    _extract_feed_image_url,
    _img_candidata,
    _resolve_image_url,
)
from utils.opengraph import _extrair_imagem, imagem_publicavel  # noqa: E402


def _entry(**kw):
    return SimpleNamespace(**kw)


class _RespostaFalsa:
    def __init__(self, status=200, corpo=b"", headers=None, charset="utf-8"):
        self.status = status
        self.headers = headers or {}
        self.charset = charset
        self.content = SimpleNamespace(read=self._read)
        self._corpo = corpo

    async def _read(self, _n=None):
        return self._corpo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _SessaoFalsa:
    """Registra CADA url pedida: e assim que se prova que o GET nao aconteceu."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidas = []

    def get(self, url, **kw):
        self.pedidas.append(url)
        if not self.respostas:
            return _RespostaFalsa(status=404)
        return self.respostas.pop(0)


HTML_COM_OG = b'<html><head><meta property="og:image" content="https://cdn.exemplo.com/capa.jpg"></head></html>'


class TestPrecedenciaDoFeed(unittest.TestCase):
    """INV: o feed tem precedencia; o OpenGraph so entra quando o feed nao trouxe nada."""

    def test_doente_feed_vazio_usa_opengraph(self):
        # Este e o caso do animeanime.jp / animecorner.me medido em producao.
        sessao = _SessaoFalsa([_RespostaFalsa(corpo=HTML_COM_OG)])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://animecorner.me/materia/", "", sessao, None
        ))
        self.assertEqual(url, "https://cdn.exemplo.com/capa.jpg")
        self.assertEqual(len(sessao.pedidas), 1, "devia ter buscado a pagina do artigo")

    def test_legitimo_feed_com_imagem_nao_gasta_requisicao(self):
        # MESMO SINAL do caso acima (noticia textual, mesma funcao, mesmo caminho):
        # a unica diferenca e o feed trazer imagem. O OG nao pode ser chamado.
        sessao = _SessaoFalsa([_RespostaFalsa(corpo=HTML_COM_OG)])
        url = asyncio.run(_resolve_image_url(
            _entry(media_thumbnail=[{"url": "https://feed.exemplo.com/do-feed.jpg"}]),
            "https://animecorner.me/materia/", "", sessao, None
        ))
        self.assertEqual(url, "https://feed.exemplo.com/do-feed.jpg")
        self.assertEqual(sessao.pedidas, [], "feed tinha imagem: nao podia buscar a pagina")

    def test_youtube_nao_busca_pagina(self):
        sessao = _SessaoFalsa([])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "", sessao, None
        ))
        self.assertEqual(url, "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg")
        self.assertEqual(sessao.pedidas, [])


class TestFalhaNuncaImpedePublicacao(unittest.TestCase):
    """INV-IMG-1: nenhuma falha na resolucao pode impedir a publicacao."""

    def test_doente_rede_explode_dentro_do_fetch(self):
        # Exercita o try/except de utils.opengraph._baixar_html -- NAO o de
        # _resolve_image_url, que fica blindado por ele. Os dois ramos precisam
        # de teste proprio: teste que nao exercita o ramo que nomeia e enfeite.
        class SessaoQueExplode:
            def get(self, *a, **kw):
                raise RuntimeError("rede caiu no meio")

        url = asyncio.run(_resolve_image_url(
            _entry(), "https://exemplo.com/a", "", SessaoQueExplode(), None
        ))
        self.assertEqual(url, "", "falha de rede tem de virar ausencia de imagem, nao excecao")

    def test_doente_resolvedor_de_og_levanta_e_noticia_segue(self):
        # Ramo de _resolve_image_url: se o proprio fetch_og_image levantar (bug
        # no executor, import quebrado, contrato mudado), a noticia AINDA sai.
        # Defesa em profundidade: a camada de baixo ja protege, e esta guarda
        # existe para o dia em que ela parar de proteger.
        import core.scanner as sc

        async def explode(*a, **kw):
            raise RuntimeError("contrato do resolvedor quebrou")

        original = sc.fetch_og_image
        sc.fetch_og_image = explode
        try:
            url = asyncio.run(_resolve_image_url(
                _entry(), "https://exemplo.com/a", "", _SessaoFalsa([]), None
            ))
        finally:
            sc.fetch_og_image = original
        self.assertEqual(url, "", "excecao do resolvedor nao pode subir para o envio")

    def test_legitimo_mesma_rota_sem_falha_entrega_imagem(self):
        sessao = _SessaoFalsa([_RespostaFalsa(corpo=HTML_COM_OG)])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://exemplo.com/a", "", sessao, None
        ))
        self.assertEqual(url, "https://cdn.exemplo.com/capa.jpg")


class TestImagemPublicavel(unittest.TestCase):
    """
    INV: URL de imagem invalida faz o Discord recusar o EMBED INTEIRO (50035),
    a noticia falha em TODAS as guilds, nao entra no dedup, e o ciclo seguinte
    tenta de novo -- para sempre. Medido no bot irmao em 2026-08-30.
    """

    def test_doente_relativa_e_recusada(self):
        self.assertIsNone(imagem_publicavel("/wp-content/capa.jpg"))

    def test_doente_host_interno_e_recusado(self):
        self.assertIsNone(imagem_publicavel("http://169.254.169.254/latest/meta-data/"))

    def test_legitimo_com_mesmo_sinal_passa(self):
        # Mesmo sinal do primeiro doente: caminho /wp-content/, mesma extensao.
        # So difere no que importa -- ser absoluta e de host publico.
        url = "https://static.animecorner.me/wp-content/capa.jpg"
        self.assertEqual(imagem_publicavel(url), url)

    def test_vazio_e_none_nao_levantam(self):
        self.assertIsNone(imagem_publicavel(""))
        self.assertIsNone(imagem_publicavel(None))


class TestImgDescartavel(unittest.TestCase):
    """
    INV: token descartavel casa como TOKEN, nunca como substring. Casar
    substring foi o mecanismo exato da classe 3.5 (canal errado assinado).
    """

    def test_doente_pixel_de_rastreio_descartado(self):
        self.assertEqual(_img_candidata('<img src="https://t.co/pixel.gif" width="1" height="1">'), "")

    def test_legitimo_com_o_mesmo_sinal_aceito(self):
        # "comiconline" CONTEM "icon". Se a guarda casar substring, reprova
        # imagem legitima -- e guarda que reprova o correto e pior que guarda
        # nenhuma.
        tag = '<img src="https://cdn.exemplo.com/comiconline-capa.jpg" width="1200" height="675">'
        self.assertEqual(_img_candidata(tag), "https://cdn.exemplo.com/comiconline-capa.jpg")

    def test_doente_data_uri_descartado(self):
        self.assertEqual(_img_candidata('<img src="data:image/gif;base64,R0lGOD">'), "")

    def test_lazy_load_usa_data_src(self):
        tag = '<img src="data:image/gif;base64,R0lGOD" data-src="https://cdn.exemplo.com/real.jpg">'
        self.assertEqual(_img_candidata(tag), "https://cdn.exemplo.com/real.jpg")

    def test_primeira_img_enfeite_nao_cega_a_segunda(self):
        # A regex antiga pegava a PRIMEIRA <img> e parava. Aqui a primeira e
        # icone de compartilhar; a imagem da noticia e a segunda.
        summary = (
            '<p><img src="https://t.co/share-button.png" width="16" height="16"></p>'
            '<p><img src="https://cdn.exemplo.com/materia-capa.jpg"></p>'
        )
        achada = _extract_feed_image_url(_entry(), "https://exemplo.com/a", summary)
        self.assertEqual(achada, "https://cdn.exemplo.com/materia-capa.jpg")


class TestOrdemDoFeedNaoRegrediu(unittest.TestCase):
    """Regressao: a ordem de preferencia dentro do feed e contrato antigo."""

    def test_media_thumbnail_ganha_de_enclosure(self):
        e = _entry(
            media_thumbnail=[{"url": "https://a.exemplo.com/thumb.jpg"}],
            links=[{"href": "https://b.exemplo.com/enc.jpg", "rel": "enclosure", "type": "image/jpeg"}],
        )
        self.assertEqual(_extract_feed_image_url(e, "https://x.com/a", ""), "https://a.exemplo.com/thumb.jpg")

    def test_enclosure_ganha_de_img_no_summary(self):
        e = _entry(links=[{"href": "https://b.exemplo.com/enc.jpg", "rel": "enclosure", "type": "image/jpeg"}])
        summary = '<img src="https://c.exemplo.com/summary.jpg">'
        self.assertEqual(_extract_feed_image_url(e, "https://x.com/a", summary), "https://b.exemplo.com/enc.jpg")

    def test_feed_sem_nada_devolve_vazio(self):
        self.assertEqual(_extract_feed_image_url(_entry(), "https://x.com/a", ""), "")


class TestRedirecionamentoValidado(unittest.TestCase):
    """
    INV-IMG-2: nenhuma URL fora de http(s) publico e buscada, INCLUSIVE depois
    de redirecionamento. O link vem de feed externo e o destino de um 302 nao
    passaria por validate_url nenhuma -- e o caminho classico de SSRF.
    """

    def test_doente_302_para_host_interno_nao_e_seguido(self):
        sessao = _SessaoFalsa([
            _RespostaFalsa(status=302, headers={"Location": "http://169.254.169.254/latest/meta-data/"}),
            _RespostaFalsa(corpo=HTML_COM_OG),  # so seria alcancada se o salto fosse seguido
        ])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://exemplo.com/a", "", sessao, None
        ))
        self.assertEqual(url, "")
        self.assertEqual(len(sessao.pedidas), 1, "o endereco interno NAO podia ter sido pedido")
        self.assertNotIn("169.254.169.254", " ".join(sessao.pedidas))

    def test_legitimo_302_com_o_mesmo_sinal_e_seguido(self):
        # MESMO sinal (302 com Location) -- muda so o destino, que e publico.
        sessao = _SessaoFalsa([
            _RespostaFalsa(status=302, headers={"Location": "https://exemplo.com/artigo-final"}),
            _RespostaFalsa(corpo=HTML_COM_OG),
        ])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://exemplo.com/a", "", sessao, None
        ))
        self.assertEqual(url, "https://cdn.exemplo.com/capa.jpg")
        self.assertEqual(len(sessao.pedidas), 2)

    def test_cadeia_de_dois_saltos_e_abandonada(self):
        sessao = _SessaoFalsa([
            _RespostaFalsa(status=302, headers={"Location": "https://exemplo.com/1"}),
            _RespostaFalsa(status=302, headers={"Location": "https://exemplo.com/2"}),
            _RespostaFalsa(corpo=HTML_COM_OG),
        ])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://exemplo.com/a", "", sessao, None
        ))
        self.assertEqual(url, "")
        self.assertEqual(len(sessao.pedidas), 2, "teto de 1 salto")

    def test_status_nao_200_nao_vira_imagem(self):
        sessao = _SessaoFalsa([_RespostaFalsa(status=403)])
        url = asyncio.run(_resolve_image_url(
            _entry(), "https://exemplo.com/a", "", sessao, None
        ))
        self.assertEqual(url, "")


class TestExtracaoDeMetaTag(unittest.TestCase):
    """INV: ordem og:image > twitter:image > itemprop > link rel=image_src."""

    def test_og_ganha_de_twitter(self):
        html = ('<meta name="twitter:image" content="https://x/tw.jpg">'
                '<meta property="og:image" content="https://x/og.jpg">')
        self.assertEqual(_extrair_imagem(html), "https://x/og.jpg")

    def test_content_vazio_nao_conta_como_encontrado(self):
        # Doente: og:image existe mas vazio. Se contar, o embed recebe "" e a
        # noticia pode ser recusada pela API.
        html = ('<meta property="og:image" content="">'
                '<meta name="twitter:image" content="https://x/tw.jpg">')
        self.assertEqual(_extrair_imagem(html), "https://x/tw.jpg")

    def test_pagina_sem_tag_nenhuma(self):
        self.assertIsNone(_extrair_imagem("<html><head><title>x</title></head></html>"))


if __name__ == "__main__":
    unittest.main()
