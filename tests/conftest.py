"""
Configuração do pytest para a pasta tests/.

`test_filters_fix.py` e `verify_filters_manual.py` estavam aqui excluídos por
serem scripts manuais. Consequência: ficaram 7/9 e 10/10 sem ninguém ver, e
foi um deles que denunciou dois bugs reais de produção (a lista de termos
estritos não conhecia "Demon Slayer"; a blacklist não tinha nenhum termo de
merch, apesar do readme prometer). Ambos são agora testes normais —
`verify_filters_manual.py` virou `test_filtros_spec.py`.

O que continua fora da coleta são só os dois scripts que fazem **rede real**:
não são testes (não afirmam nada), são ferramentas de diagnóstico manual.
Rodam com `python tests/<nome>.py` a partir da raiz do projeto.
"""
collect_ignore = [
    "test_live_scanner.py",  # varredura real contra sources.json, com envio ao Discord mockado
    "test_discovery.py",     # descoberta de feeds; faz requests HTTP reais
]

import pytest


@pytest.fixture(autouse=True)
def _sem_jitter_de_fetch(monkeypatch):
    """
    Zera o jitter de fetch (0.5-2.5s por fonte) em TODOS os testes. Sem isto, cada
    teste que roda run_scan_once dorme por fonte e a suíte arrasta. O jitter real
    (evasão de rate-limit por IP) vive em produção via settings; aqui não interessa.
    """
    try:
        import core.scanner as sc
        monkeypatch.setattr(sc, "FEED_JITTER_MIN", 0.0, raising=False)
        monkeypatch.setattr(sc, "FEED_JITTER_MAX", 0.0, raising=False)
    except Exception:
        pass
