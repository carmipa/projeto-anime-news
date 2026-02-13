"""
Custom exceptions for better error handling and logging.
"""
from typing import Optional, Dict, Any


class AnimeBotException(Exception):
    """Base exception para todas as exceções do bot."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = self.__class__.__name__


class ConfigurationError(AnimeBotException):
    """Erro de configuração (arquivos JSON inválidos, valores faltando, etc)."""
    pass


class ValidationError(AnimeBotException):
    """Erro de validação de entrada."""
    pass


class SecurityError(AnimeBotException):
    """Erro de segurança (permissões, rate limit, etc)."""
    pass


class NetworkError(AnimeBotException):
    """Erro de rede (timeout, conexão, etc)."""
    pass


class FeedParseError(AnimeBotException):
    """Erro ao fazer parse de feed RSS/Atom."""
    pass


class TranslationError(AnimeBotException):
    """Erro na tradução de texto."""
    pass


class DiscordAPIError(AnimeBotException):
    """Erro na API do Discord."""
    pass


class RateLimitError(SecurityError):
    """Erro de rate limit."""
    
    def __init__(self, message: str, retry_after: Optional[float] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class PermissionError(SecurityError):
    """Erro de permissão."""
    pass
