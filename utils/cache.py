"""
Cache utilities - HTTP caching with ETag and Last-Modified support.
"""
from typing import Dict, Any
from .storage import load_json_safe, save_json_safe, p


def load_http_state() -> Dict[str, Dict[str, str]]:
    """
    Carrega state.json com ETags e Last-Modified por URL.
    
    Returns:
        Dict com formato: {"https://feed.com": {"etag": "abc123", "last_modified": "..."}}
    """
    return load_json_safe(p("state.json"), {})


def save_http_state(state: Dict[str, Dict[str, str]]) -> None:
    """
    Salva cache de ETags e Last-Modified.
    
    Args:
        state: Dicionário de estados HTTP por URL
    """
    save_json_safe(p("state.json"), state)


def get_cache_headers(url: str, state: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    """
    Retorna headers de cache para uma URL se disponíveis.
    
    Args:
        url: URL do feed
        state: Estado HTTP carregado
    
    Returns:
        Headers If-None-Match e/ou If-Modified-Since se disponíveis
    """
    headers = {}
    url_state = state.get(url, {})
    
    if "etag" in url_state and url_state["etag"]:
        headers["If-None-Match"] = url_state["etag"]
    
    if "last_modified" in url_state and url_state["last_modified"]:
        headers["If-Modified-Since"] = url_state["last_modified"]
    
    return headers


def update_cache_state(url: str, response_headers: Any, state: Dict[str, Dict[str, str]]) -> None:
    """
    Atualiza state com ETags e Last-Modified da resposta HTTP.
    
    Args:
        url: URL do feed
        response_headers: Headers da resposta HTTP
        state: Estado HTTP a atualizar (modificado in-place)
    """
    if url not in state:
        state[url] = {}
    
    # Salva ETag se presente (case-insensitive)
    if "ETag" in response_headers:
        state[url]["etag"] = response_headers["ETag"]
    elif "etag" in response_headers:
        state[url]["etag"] = response_headers["etag"]
    
    # Salva Last-Modified se presente (case-insensitive)
    if "Last-Modified" in response_headers:
        state[url]["last_modified"] = response_headers["Last-Modified"]
    elif "last-modified" in response_headers:
        state[url]["last_modified"] = response_headers["last-modified"]

    # Atualiza timestamp de acesso
    from datetime import datetime
    state[url]["last_accessed"] = datetime.now().isoformat()


def cleanup_state(state: Dict[str, Dict[str, str]], days: int = 7) -> int:
    """
    Remove entradas do state não acessadas há X dias.
    
    Args:
        state: O dicionário de estado (modificado in-place).
        days: Número de dias para corte.
        
    Returns:
        Número de entradas removidas.
    """
    from datetime import datetime, timedelta
    from .logger import log
    
    cutoff = datetime.now() - timedelta(days=days)
    to_remove = []
    updated_count = 0
    
    for url, data in state.items():
        # Preserva metadados (começam com _)
        if url.startswith("_"):
            continue
            
        # Se não tiver data (legado), marca agora para não deletar imediatamente
        if "last_accessed" not in data:
            data["last_accessed"] = datetime.now().isoformat()
            updated_count += 1
            continue
            
        try:
            last_access = datetime.fromisoformat(data["last_accessed"])
            if last_access < cutoff:
                to_remove.append(url)
                log.debug(f"🧹 [CLEANUP] Marcando para remoção: {url[:60]}... (último acesso: {last_access.isoformat()})")
        except (ValueError, TypeError) as e:
            # Data inválida, reseta para agora
            log.warning(f"⚠️ [CLEANUP] Data inválida em {url[:60]}...: {e}. Resetando timestamp.")
            data["last_accessed"] = datetime.now().isoformat()
            updated_count += 1

    # Remove entradas antigas
    for url in to_remove:
        del state[url]
    
    if len(to_remove) > 0 or updated_count > 0:
        log.info(f"🧹 [CLEANUP] Removidas {len(to_remove)} entradas antigas (>={days} dias). {updated_count} timestamps atualizados.")
        
    return len(to_remove)
