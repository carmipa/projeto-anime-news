"""
Storage utilities - JSON load/save functions.
"""
import os
import json
import logging
from typing import Any

log = logging.getLogger("AnimeBotIntel")

# Diretório dos arquivos de ESTADO de runtime. Vazio = diretório atual (comportamento
# local). Em Docker deve apontar para um volume de DIRETÓRIO (DATA_DIR=/app/data): é o
# que permite a escrita atômica (os.replace), IMPOSSÍVEL sobre bind mount de arquivo
# único — onde o rename sobre o mount point dá EBUSY e cai no fallback não-atômico.
DATA_DIR = os.getenv("DATA_DIR", "").strip()

# Só estes arquivos (estado de runtime, escritos pelo bot) vão para DATA_DIR. Os
# estáticos vindos da imagem — sources.json (catálogo), translations/, templates —
# continuam relativos ao diretório do app.
_ARQUIVOS_DE_ESTADO = {"config.json", "history.json", "state.json", "audit.json", "audit.jsonl"}


def p(filename: str) -> str:
    """
    PROPÓSITO DE NEGÓCIO: resolver o caminho absoluto de um arquivo do bot,
    roteando os arquivos de ESTADO de runtime para DATA_DIR quando definido.

    INVARIANTES DO DOMÍNIO:
    - Só um nome NU (sem separador) que esteja na lista de estado é roteado para
      DATA_DIR; qualquer coisa com caminho ('translations/x.json') ou fora da lista
      ('sources.json') resolve relativo ao app, como sempre.
    - DATA_DIR vazio ⇒ comportamento idêntico ao anterior (cwd), para não mexer no
      uso local nem nos testes.

    COMPORTAMENTO EM CASO DE FALHA: nunca levanta; devolve sempre um caminho absoluto.
    """
    base = os.path.basename(filename)
    if DATA_DIR and filename == base and base in _ARQUIVOS_DE_ESTADO:
        return os.path.abspath(os.path.join(DATA_DIR, base))
    return os.path.abspath(filename)


def load_json_safe(filepath: str, default: Any) -> Any:
    """
    Carrega JSON sem derrubar o bot se faltar / vazio / corrompido.
    
    Args:
        filepath: Caminho do arquivo JSON
        default: Valor padrão se falhar
    
    Returns:
        Dados do JSON ou valor padrão
    """
    try:
        if not os.path.exists(filepath):
            log.warning(f"Arquivo '{filepath}' não existe. Usando padrão.")
            return default
        if os.path.getsize(filepath) == 0:
            log.warning(f"Arquivo '{filepath}' está vazio. Usando padrão.")
            return default
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Falha ao carregar '{filepath}': {e}. Usando padrão.")
        return default


def _write_json_direct(filepath: str, data: Any) -> None:
    """Escrita direta (não-atômica) no arquivo alvo."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_json_safe(filepath: str, data: Any) -> None:
    """
    Salva JSON de forma atômica (tmp + os.replace); em erro, loga e segue.

    Escreve num arquivo temporário no mesmo diretório e faz os.replace
    (rename atômico), evitando corromper o arquivo se o processo cair no
    meio da escrita.

    Fallback: quando o rename atômico não é possível — ex.: o alvo é um bind
    mount de arquivo único no Docker (./config.json:/app/config.json), que gera
    EXDEV/EBUSY ao renomear sobre o mount point — faz escrita direta no arquivo.

    Args:
        filepath: Caminho do arquivo JSON
        data: Dados a salvar
    """
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, filepath)
        except OSError as e:
            # Rename atômico indisponível (bind mount de arquivo único etc.)
            log.warning(f"Escrita atômica indisponível para '{filepath}' ({e}); usando escrita direta.")
            _write_json_direct(filepath, data)
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    except Exception as e:
        log.error(f"Falha ao salvar '{filepath}': {e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
