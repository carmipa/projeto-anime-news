"""
Guardas calibradas do veredito de saúde da varredura (telemetria de ausência, §3.6).

Disciplina (regra 23 / §6 do manutencao-de-bots): cada regra do veredito nasce com um
PAR — o cenário que TEM de alarmar e o gêmeo saudável que TEM de ficar calado. Guarda
que nunca foi vista reprovando não prova nada quando aprova. Aqui estão os dois
controles no mesmo arquivo: o positivo (o instrumento sabe dizer ANOMALIA/ATENÇÃO) e o
negativo (sabe dizer OK), para um zero legítimo nunca ser confundido com o instrumento
cego.
"""
import pytest
from core.stats import (
    avaliar_varredura,
    VEREDITO_OK,
    VEREDITO_ATENCAO,
    VEREDITO_ANOMALIA,
)


def _av(**kw):
    """avaliar_varredura com um cenário saudável por baixo; sobrescreve o que o teste quer."""
    base = dict(
        fontes_totais=50, feeds_falhos=0, feeds_vazios=0, itens_sem_data=0,
        itens_examinados=10, enviadas=5, semeados=0, cache_hits=3,
        ciclos_sem_envio=0,
    )
    base.update(kw)
    return avaliar_varredura(**base)


# --- Invariante transversal: veredito != OK sempre tem motivo; OK também tem ---

def test_todo_veredito_tem_motivo():
    for cenario in [
        _av(),                                   # OK saudável
        _av(fontes_totais=0),                    # ANOMALIA
        _av(feeds_falhos=30),                    # ANOMALIA por proporção
        _av(feeds_falhos=13),                    # ATENÇÃO por proporção
        _av(itens_sem_data=8, itens_examinados=10),  # ANOMALIA itens sem data
        _av(enviadas=0, ciclos_sem_envio=30),    # ANOMALIA ciclos
    ]:
        assert cenario["motivos"], f"veredito sem motivo é rótulo, não diagnóstico: {cenario}"


# --- Regra: catálogo vazio ---

def test_catalogo_vazio_alarma():
    # Controle POSITIVO: o instrumento sabe dizer ANOMALIA.
    r = _av(fontes_totais=0)
    assert r["veredito"] == VEREDITO_ANOMALIA
    assert any("catálogo vazio" in m for m in r["motivos"])


def test_catalogo_cheio_saudavel_fica_calado():
    # Gêmeo saudável: catálogo cheio, tudo entregando → OK (controle NEGATIVO).
    r = _av(fontes_totais=50, feeds_falhos=0, feeds_vazios=0, enviadas=8)
    assert r["veredito"] == VEREDITO_OK


# --- Regra: contadores inválidos falham FECHADO (nunca OK por omissão) ---

@pytest.mark.parametrize("ruim", [
    dict(fontes_totais=-1),
    dict(feeds_falhos="abc"),
    dict(enviadas=None),
    dict(feeds_vazios=-5),
])
def test_contador_invalido_e_anomalia(ruim):
    r = _av(**ruim)
    assert r["veredito"] == VEREDITO_ANOMALIA
    assert any("inválid" in m for m in r["motivos"])


def test_contadores_validos_nao_sao_anomalia_por_isso():
    # Gêmeo: os mesmos campos, válidos → não dispara a regra de invalidez.
    r = _av(fontes_totais=50, feeds_falhos=0, enviadas=5, feeds_vazios=0)
    assert r["veredito"] != VEREDITO_ANOMALIA


# --- Regra: proporção de fontes mudas (falhos + vazios) ---

def test_metade_das_fontes_mudas_alarma_anomalia():
    r = _av(fontes_totais=50, feeds_falhos=20, feeds_vazios=5)  # 25/50 = 0.5
    assert r["veredito"] == VEREDITO_ANOMALIA


def test_um_quarto_das_fontes_mudas_alarma_atencao():
    r = _av(fontes_totais=50, feeds_falhos=13, feeds_vazios=0)  # 13/50 = 0.26
    assert r["veredito"] == VEREDITO_ATENCAO


def test_uma_fonte_muda_em_cinquenta_e_ruido_fica_calado():
    # Gêmeo saudável: 1 em 50 é ruído, não anomalia. É a calibração do "não basta
    # um contador: a proporção decide".
    r = _av(fontes_totais=50, feeds_falhos=1, feeds_vazios=0, enviadas=5)
    assert r["veredito"] == VEREDITO_OK


def test_logo_abaixo_do_limiar_de_atencao_fica_calado():
    # 12/50 = 0.24, logo abaixo de 0.25 → não alarma (calibração da borda).
    r = _av(fontes_totais=50, feeds_falhos=12, feeds_vazios=0, enviadas=5)
    assert r["veredito"] == VEREDITO_OK


# --- Regra: itens novos descartados por falta de data (proporção calibrada) ---

def test_maioria_dos_itens_sem_data_alarma_anomalia():
    # 8 de 10 itens novos sem data → extração de data possivelmente quebrada.
    r = _av(itens_sem_data=8, itens_examinados=10)
    assert r["veredito"] == VEREDITO_ANOMALIA
    assert any("falta de" in m for m in r["motivos"])


def test_um_quarto_dos_itens_sem_data_alarma_atencao():
    r = _av(itens_sem_data=3, itens_examinados=10)  # 0.3
    assert r["veredito"] == VEREDITO_ATENCAO


def test_poucos_itens_sem_data_fica_calado():
    # Gêmeo saudável: 1 em 10 é ruído (0.1, abaixo de 0.25) — não alarma. É a
    # calibração que evita o alarme falso que fazia isto ser risco residual.
    r = _av(itens_sem_data=1, itens_examinados=10)
    assert r["veredito"] == VEREDITO_OK


def test_itens_sem_data_sem_denominador_fica_calado():
    # Sem itens examinados (nenhum item novo), a regra não dispara — não há
    # proporção a calcular, e um cache-hit total é legítimo.
    r = _av(itens_sem_data=0, itens_examinados=0)
    assert r["veredito"] == VEREDITO_OK


# --- Regra: ciclos seguidos sem publicar (distingue "dia sem notícia" de "bot mudo") ---

def test_um_ciclo_sem_publicar_e_legitimo():
    # Zero legítimo dito com todas as letras: 0 enviadas, fontes responderam, 1º ciclo.
    r = _av(enviadas=0, semeados=0, ciclos_sem_envio=0)
    assert r["veredito"] == VEREDITO_OK
    assert any("sem novidade" in m for m in r["motivos"])


def test_seis_ciclos_sem_publicar_alarma_atencao():
    r = _av(enviadas=0, semeados=0, ciclos_sem_envio=6)
    assert r["veredito"] == VEREDITO_ATENCAO


def test_vinte_e_quatro_ciclos_sem_publicar_alarma_anomalia():
    r = _av(enviadas=0, semeados=0, ciclos_sem_envio=24)
    assert r["veredito"] == VEREDITO_ANOMALIA


# --- Regra anime-news-específica (lente boa-fé): semeadura NÃO é ciclo sem envio ---

def test_semeadura_com_zero_enviadas_e_ok_mesmo_com_historico_alto():
    # Uma varredura que só semeou fontes novas envia 0 de propósito. Se copiássemos
    # o critério do bot irmão sem esta adaptação, seria ANOMALIA falsa. O gêmeo
    # saudável aqui é a própria semeadura: com semeados>0, mesmo ciclos_sem_envio
    # alto, o veredito é OK (o envio começa no próximo ciclo).
    r = _av(enviadas=0, semeados=8, ciclos_sem_envio=30)
    assert r["veredito"] == VEREDITO_OK
    assert any("semeada" in m for m in r["motivos"])


# --- Escalada: o pior sinal manda (veredito só sobe, nunca desce) ---

def test_pior_sinal_manda():
    # ATENÇÃO (itens sem data 0.3) + ANOMALIA (fontes mudas 0.6) → ANOMALIA.
    r = _av(fontes_totais=50, feeds_falhos=30, itens_sem_data=3, itens_examinados=10)
    assert r["veredito"] == VEREDITO_ANOMALIA


# --- Integração: o furo operacional (catálogo vazio no caminho real do scanner) ---

def test_scanner_catalogo_vazio_persiste_anomalia(monkeypatch, tmp_path):
    """
    Cobre a revisão de falha operacional: a varredura tem early-return quando não há
    fontes, ANTES do cálculo do veredito. Sem o conserto, a ANOMALIA mais importante
    (catálogo vazio) sairia em silêncio. Prova que ela é registada em memória E
    persistida em state.json pelo caminho REAL do scanner.
    """
    import asyncio
    import json
    import core.scanner as sc

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sc, "load_sources", lambda: [])
    sc.stats.ultimo_veredito = None

    asyncio.run(sc.run_scan_once(bot=None, trigger="test"))

    assert sc.stats.ultimo_veredito is not None
    assert sc.stats.ultimo_veredito["veredito"] == VEREDITO_ANOMALIA
    meta = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["_meta"]
    assert meta["ultimo_veredito"]["veredito"] == VEREDITO_ANOMALIA
