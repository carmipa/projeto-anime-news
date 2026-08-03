
import logging
import colorlog
import sys
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class StructuredFormatter(logging.Formatter):
    """Formatter para logs estruturados (JSON) para fácil parsing."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Formata log como JSON estruturado."""
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Adiciona campos extras se existirem
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "guild_id"):
            log_data["guild_id"] = record.guild_id
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type
        if hasattr(record, "details"):
            log_data["details"] = record.details
        
        # Adiciona exception info se existir
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)

def setup_logger(name: str = "AnimeBootNews", structured: bool = False) -> logging.Logger:
    """
    Configura e retorna um logger com suporte a cores (GRC style).
    
    Args:
        name: Nome do logger
        structured: Se True, usa formato JSON estruturado
    """
    # Cria o logger base
    logger = logging.getLogger(name)
    
    # Nível padrão pode ser alterado via env var
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Evita duplicação de handlers se chamar setup_logger múltiplas vezes
    if logger.handlers:
        return logger

    # Handler de Console (Stream)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    if structured:
        # Formatação estruturada (JSON)
        formatter = StructuredFormatter()
    else:
        # Formatação com Cores
        formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            reset=True,
            log_colors={
                'DEBUG':    'white',
                'INFO':     'green',
                'WARNING':  'yellow',
                'ERROR':    'red',
                'CRITICAL': 'red,bg_white',
            },
            secondary_log_colors={},
            style='%'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    user_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    event_type: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    exc_info: Optional[Exception] = None
):
    """
    Log com contexto estruturado.
    
    Args:
        logger: Logger instance
        level: Nível de log (logging.INFO, etc)
        message: Mensagem
        user_id: ID do usuário
        guild_id: ID da guild
        event_type: Tipo do evento
        details: Detalhes adicionais
        exc_info: Exception info
    """
    extra = {}
    if user_id:
        extra["user_id"] = user_id
    if guild_id:
        extra["guild_id"] = guild_id
    if event_type:
        extra["event_type"] = event_type
    if details:
        extra["details"] = details
    
    logger.log(level, message, extra=extra, exc_info=exc_info)

# Instância padrão para importação direta
log = setup_logger()
