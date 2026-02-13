"""
Audit logging system for GRC (Governance, Risk, Compliance).
Structured logging for security events, configuration changes, and compliance tracking.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from utils.storage import p, load_json_safe, save_json_safe
from utils.logger import log


class AuditEventType(Enum):
    """Tipos de eventos auditáveis."""
    # Segurança
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_INPUT = "INVALID_INPUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TOKEN_VALIDATION_FAILED = "TOKEN_VALIDATION_FAILED"
    SECURITY_CHECK_FAILED = "SECURITY_CHECK_FAILED"
    
    # Configuração
    CONFIG_CHANGED = "CONFIG_CHANGED"
    FILTER_CHANGED = "FILTER_CHANGED"
    CHANNEL_CHANGED = "CHANNEL_CHANGED"
    LANGUAGE_CHANGED = "LANGUAGE_CHANGED"
    
    # Operações
    SCAN_STARTED = "SCAN_STARTED"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SCAN_FAILED = "SCAN_FAILED"
    NEWS_POSTED = "NEWS_POSTED"
    NEWS_BLOCKED = "NEWS_BLOCKED"
    
    # Sistema
    BOT_STARTED = "BOT_STARTED"
    BOT_STOPPED = "BOT_STOPPED"
    COG_LOADED = "COG_LOADED"
    COG_FAILED = "COG_FAILED"
    ERROR_OCCURRED = "ERROR_OCCURRED"
    
    # Compliance
    DATA_ACCESSED = "DATA_ACCESSED"
    DATA_MODIFIED = "DATA_MODIFIED"
    BACKUP_CREATED = "BACKUP_CREATED"


class AuditSeverity(Enum):
    """Níveis de severidade."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AuditLogger:
    """Sistema de auditoria estruturado."""
    
    def __init__(self, audit_file: str = "audit.json"):
        self.audit_file = p(audit_file)
        self.max_entries = 10000  # Mantém últimos 10k eventos
        self._ensure_audit_file()
    
    def _ensure_audit_file(self):
        """Garante que o arquivo de auditoria existe."""
        if not os.path.exists(self.audit_file):
            save_json_safe(self.audit_file, [])
    
    def log(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Registra um evento de auditoria.
        
        Args:
            event_type: Tipo do evento
            severity: Severidade
            user_id: ID do usuário (opcional)
            guild_id: ID da guild (opcional)
            details: Detalhes do evento
            metadata: Metadados adicionais
        """
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "severity": severity.value,
            "user_id": user_id,
            "guild_id": guild_id,
            "details": details or {},
            "metadata": metadata or {}
        }
        
        # Carrega eventos existentes
        events = load_json_safe(self.audit_file, [])
        if not isinstance(events, list):
            events = []
        
        # Adiciona novo evento
        events.append(event)
        
        # Mantém apenas últimos N eventos
        if len(events) > self.max_entries:
            events = events[-self.max_entries:]
        
        # Salva
        save_json_safe(self.audit_file, events)
        
        # Log também no logger padrão
        log_msg = (
            f"[AUDIT] {event_type.value} | "
            f"Severity: {severity.value} | "
            f"User: {user_id} | "
            f"Guild: {guild_id} | "
            f"Details: {details}"
        )
        
        if severity == AuditSeverity.CRITICAL:
            log.critical(log_msg)
        elif severity == AuditSeverity.ERROR:
            log.error(log_msg)
        elif severity == AuditSeverity.WARNING:
            log.warning(log_msg)
        else:
            log.info(log_msg)
    
    def query(
        self,
        event_type: Optional[AuditEventType] = None,
        severity: Optional[AuditSeverity] = None,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Consulta eventos de auditoria.
        
        Args:
            event_type: Filtrar por tipo
            severity: Filtrar por severidade
            guild_id: Filtrar por guild
            user_id: Filtrar por usuário
            since: Filtrar eventos desde esta data
            limit: Limite de resultados
        
        Returns:
            Lista de eventos
        """
        events = load_json_safe(self.audit_file, [])
        if not isinstance(events, list):
            return []
        
        filtered = []
        for event in events:
            # Filtros
            if event_type and event.get("event_type") != event_type.value:
                continue
            if severity and event.get("severity") != severity.value:
                continue
            if guild_id and event.get("guild_id") != guild_id:
                continue
            if user_id and event.get("user_id") != user_id:
                continue
            if since:
                try:
                    event_time = datetime.fromisoformat(event.get("timestamp", ""))
                    if event_time < since:
                        continue
                except (ValueError, TypeError):
                    continue
            
            filtered.append(event)
        
        # Retorna últimos N
        return filtered[-limit:]
    
    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Retorna estatísticas de auditoria.
        
        Args:
            days: Número de dias para analisar
        
        Returns:
            Estatísticas
        """
        since = datetime.utcnow() - timedelta(days=days)
        events = self.query(since=since, limit=10000)
        
        stats = {
            "total_events": len(events),
            "by_type": {},
            "by_severity": {},
            "by_guild": {},
            "errors": 0,
            "warnings": 0,
            "critical": 0
        }
        
        for event in events:
            # Por tipo
            event_type = event.get("event_type", "UNKNOWN")
            stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1
            
            # Por severidade
            severity = event.get("severity", "INFO")
            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            
            if severity == "ERROR":
                stats["errors"] += 1
            elif severity == "WARNING":
                stats["warnings"] += 1
            elif severity == "CRITICAL":
                stats["critical"] += 1
            
            # Por guild
            guild_id = event.get("guild_id")
            if guild_id:
                stats["by_guild"][str(guild_id)] = stats["by_guild"].get(str(guild_id), 0) + 1
        
        return stats


# Instância global
audit_logger = AuditLogger()


# Helpers para facilitar uso
def audit_event(
    event_type: AuditEventType,
    severity: AuditSeverity = AuditSeverity.INFO,
    user_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    **kwargs
):
    """Helper para registrar eventos de auditoria."""
    audit_logger.log(
        event_type=event_type,
        severity=severity,
        user_id=user_id,
        guild_id=guild_id,
        details=details,
        metadata=kwargs
    )
