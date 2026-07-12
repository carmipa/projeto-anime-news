"""
Configuração do pytest para a pasta tests/.

Alguns arquivos aqui são SCRIPTS manuais (rodam via `python tests/xxx.py`),
não testes automatizados: não têm funções `test_` e executam código no nível de
módulo. Em especial, test_filters_fix.py troca sys.stdout no import (Windows),
o que corrompe a captura do pytest ("I/O operation on closed file"). Excluímos
esses arquivos da coleta para manter a suíte limpa. Eles seguem executáveis à mão.
"""
collect_ignore = [
    "test_filters_fix.py",
    "test_live_scanner.py",
    "verify_filters_manual.py",
    "test_discovery.py",  # script de descoberta de feeds (faz requests de rede reais)
]
