"""
Guarda do mesmo defeito que atingiu o bot irmão (projeto-bot-games) em 2026-08-30.

Lá, o canal do Discord recebeu notícias cujo título e resumo eram, os dois:

    Error 500 (Server Error)!!1500.That's an error.There was an error.
    Please try again later.That's all we know.

O `deep_translator` não levanta quando o Google responde com página de erro: devolve o
TEXTO da página como se fosse a tradução. Aqui a validação era `if trad:`, que uma string
de erro satisfaz — o mesmo buraco, com o agravante de o `except Exception as e` descartar
o motivo (o `e` era capturado e nunca usado).

Este bot ainda não tinha sido apanhado publicando lixo. Isto é a correção a chegar ANTES
do incidente, não depois.
"""
import asyncio

import pytest

import utils.translator as tr

PAGINA_DE_ERRO = (
    "Error 500 (Server Error)!!1500.That's an error.There was an error. "
    "Please try again later.That's all we know."
)
ORIGINAL = "New anime announced for the winter season"


@pytest.fixture(autouse=True)
def _estado_limpo():
    tr._reset_degradacoes()
    yield
    tr._reset_degradacoes()


def _tradutor_que_responde(monkeypatch, resposta):
    class _Duplo:
        def __init__(self, *a, **k):
            pass

        def translate(self, texto):
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

    monkeypatch.setattr(tr, "GoogleTranslator", _Duplo)


def test_pagina_de_erro_nao_e_publicada(monkeypatch):
    _tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == ORIGINAL


def test_controle_positivo_traducao_boa_passa(monkeypatch):
    """Sem este par, "devolveu o original" seria indistinguível de "nunca traduz"."""
    _tradutor_que_responde(monkeypatch, "Novo anime anunciado")
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == "Novo anime anunciado"


def test_pagina_de_erro_nao_entra_no_cache(monkeypatch):
    """Cachear o lixo faria o erro repetir-se mesmo depois de o serviço voltar."""
    _tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)
    asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR"))
    assert ("pt", ORIGINAL) not in tr._TRANSLATION_CACHE

    _tradutor_que_responde(monkeypatch, "Novo anime anunciado")
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == "Novo anime anunciado"


def test_excecao_do_servico_devolve_original_e_conta(monkeypatch):
    _tradutor_que_responde(monkeypatch, RuntimeError("connection reset"))
    assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == ORIGINAL
    assert tr.degradacoes_totais() == 1, "o motivo da falha voltou a ser descartado"


def test_resposta_vazia_ou_nao_string_devolve_original(monkeypatch):
    for resposta in (None, "", "   ", b"bytes"):
        tr._reset_degradacoes()
        _tradutor_que_responde(monkeypatch, resposta)
        assert asyncio.run(tr.translate_to_target(ORIGINAL, "pt_BR")) == ORIGINAL


def test_degradacao_e_contavel(monkeypatch):
    _tradutor_que_responde(monkeypatch, PAGINA_DE_ERRO)
    for i in range(4):
        asyncio.run(tr.translate_to_target(f"{ORIGINAL} {i}", "pt_BR"))
    assert tr.degradacoes_totais() == 4


@pytest.mark.parametrize("lixo", [PAGINA_DE_ERRO, "That's all we know.",
                                  "Error 502 (Server Error)!!1", "", "  ", None, 123])
def test_detector_recusa_o_que_tem_de_recusar(lixo):
    assert tr._traducao_utilizavel(lixo) is False


@pytest.mark.parametrize("bom", [
    "Novo anime anunciado para a temporada de inverno",
    "New anime announced for the winter season",
    "Servidor do jogo caiu após o episódio",     # fala de erro, e é notícia legítima
    "Patch corrige erro 500 no site oficial",    # idem, com o número no meio
])
def test_detector_aceita_o_que_tem_de_aceitar(bom):
    """
    CONTROLE NEGATIVO. Um detector que recusa tudo passaria em todos os testes acima e
    faria o bot nunca traduzir. A assinatura procurada é o texto da página do Google, não
    a palavra "erro".
    """
    assert tr._traducao_utilizavel(bom) is True
