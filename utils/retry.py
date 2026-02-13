"""
Retry logic with exponential backoff for network operations and API calls.
"""
import asyncio
import time
from typing import Callable, TypeVar, Optional, List, Type
from functools import wraps

from utils.logger import log
from utils.exceptions import NetworkError, FeedParseError, TranslationError

T = TypeVar('T')


class RetryConfig:
    """Configuração de retry."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retryable_exceptions: Optional[List[Type[Exception]]] = None
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions or [
            NetworkError,
            FeedParseError,
            asyncio.TimeoutError,
            ConnectionError,
            OSError
        ]


async def retry_async(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs
) -> T:
    """
    Executa função assíncrona com retry e backoff exponencial.
    
    Args:
        func: Função assíncrona a executar
        *args: Argumentos posicionais
        config: Configuração de retry
        **kwargs: Argumentos nomeados
    
    Returns:
        Resultado da função
    
    Raises:
        Última exceção se todas as tentativas falharem
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    delay = config.initial_delay
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        
        except Exception as e:
            last_exception = e
            
            # Verifica se é exceção retryable
            if not any(isinstance(e, exc_type) for exc_type in config.retryable_exceptions):
                log.debug(f"Exceção não retryable: {type(e).__name__}")
                raise
            
            # Última tentativa, não espera
            if attempt == config.max_attempts:
                log.error(
                    f"Falha após {config.max_attempts} tentativas: {type(e).__name__}: {e}"
                )
                break
            
            # Log da tentativa
            log.warning(
                f"Tentativa {attempt}/{config.max_attempts} falhou: {type(e).__name__}: {e}. "
                f"Retry em {delay:.2f}s..."
            )
            
            # Espera antes de retry
            await asyncio.sleep(delay)
            
            # Backoff exponencial
            delay = min(delay * config.exponential_base, config.max_delay)
    
    # Se chegou aqui, todas as tentativas falharam
    raise last_exception


def retry_decorator(config: Optional[RetryConfig] = None):
    """
    Decorator para adicionar retry a funções assíncronas.
    
    Usage:
        @retry_decorator(config=RetryConfig(max_attempts=5))
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_async(func, *args, config=config, **kwargs)
        return wrapper
    return decorator


# Configurações pré-definidas
HTTP_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0
)

TRANSLATION_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    initial_delay=2.0,
    max_delay=10.0,
    exponential_base=1.5
)

FEED_PARSE_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    initial_delay=0.5,
    max_delay=5.0,
    exponential_base=2.0
)
