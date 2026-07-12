"""
Storage utilities - JSON load/save functions.
"""
import os
import json
import logging
from typing import Any

log = logging.getLogger("AnimeBotIntel")


def p(filename: str) -> str:
    """
    Retorna o caminho absoluto para um arquivo no diretório raiz do bot.
    
    Args:
        filename: Nome do arquivo (ex: 'config.json')
    
    Returns:
        Caminho absoluto do arquivo
    """
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
