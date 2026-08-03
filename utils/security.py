"""
Security utilities - Input validation, sanitization, rate limiting, and security checks.
"""
import re
import ipaddress
import time
from typing import Dict, Optional, Set, Tuple
from collections import defaultdict
from urllib.parse import urlparse, urljoin
import asyncio
from datetime import datetime, timedelta, timezone

from utils.logger import log


# =========================================================
# RATE LIMITING
# =========================================================

class RateLimiter:
    """Rate limiter por usuário/guild para prevenir abuso."""
    
    def __init__(self, max_calls: int = 5, period: float = 60.0):
        """
        Args:
            max_calls: Número máximo de chamadas permitidas
            period: Período em segundos
        """
        self.max_calls = max_calls
        self.period = period
        self.calls: Dict[str, list] = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def is_allowed(self, identifier: str) -> Tuple[bool, Optional[float]]:
        """
        Verifica se uma ação é permitida.
        
        Args:
            identifier: ID único (user_id, guild_id, etc)
        
        Returns:
            (allowed, retry_after)
        """
        async with self.lock:
            now = time.time()
            # Remove chamadas antigas
            self.calls[identifier] = [
                call_time for call_time in self.calls[identifier]
                if now - call_time < self.period
            ]
            
            if len(self.calls[identifier]) >= self.max_calls:
                oldest_call = min(self.calls[identifier])
                retry_after = self.period - (now - oldest_call)
                return False, retry_after
            
            self.calls[identifier].append(now)
            return True, None
    
    async def reset(self, identifier: str):
        """Reseta o contador para um identificador."""
        async with self.lock:
            self.calls[identifier] = []


# Rate limiters globais
command_rate_limiter = RateLimiter(max_calls=10, period=60.0)  # 10 comandos/minuto
scan_rate_limiter = RateLimiter(max_calls=3, period=300.0)  # 3 scans/5min
config_rate_limiter = RateLimiter(max_calls=5, period=60.0)  # 5 mudanças/minuto


# =========================================================
# INPUT VALIDATION & SANITIZATION
# =========================================================

class ValidationError(Exception):
    """Exceção para erros de validação."""
    pass


def validate_guild_id(guild_id: str) -> str:
    """Valida e sanitiza um guild ID."""
    if not guild_id:
        raise ValidationError("Guild ID não pode ser vazio")
    
    # Remove caracteres não numéricos
    cleaned = re.sub(r'[^0-9]', '', str(guild_id))
    
    if not cleaned or len(cleaned) < 17 or len(cleaned) > 20:
        raise ValidationError(f"Guild ID inválido: {guild_id}")
    
    return cleaned


def validate_channel_id(channel_id: int) -> int:
    """Valida um channel ID."""
    if not isinstance(channel_id, int):
        try:
            channel_id = int(channel_id)
        except (ValueError, TypeError):
            raise ValidationError(f"Channel ID deve ser numérico: {channel_id}")
    
    if channel_id < 100000000000000000:  # Discord IDs são snowflakes (18-19 dígitos)
        raise ValidationError(f"Channel ID inválido: {channel_id}")
    
    return channel_id


def validate_language(lang: str) -> str:
    """Valida código de idioma (formato exato pt_BR, en_US, etc.)."""
    valid_langs = {'pt_BR', 'en_US', 'es_ES', 'it_IT'}
    if not lang or str(lang) not in valid_langs:
        raise ValidationError(f"Idioma inválido: {lang}. Válidos: {valid_langs}")
    return str(lang)


def _hostname_blocks_ssrf(hostname: str) -> bool:
    """
    False se o host for claramente inseguro para fetch servidor→URL (SSRF).
    Bloqueia literais IP privados, loopback, link-local, metadata cloud comum, etc.
    Hostnames DNS não são resolvidos aqui (risco residual se feed apontar para domínio malicioso).
    """
    if not hostname:
        return False
    host = hostname.strip().lower()
    # IPv6 em URLs pode vir com []
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    blocked_names = {
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "metadata.google.internal", "metadata", "instance-data",
    }
    if host in blocked_names:
        return False

    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
        # AWS / cloud metadata (link-local 169.254.169.254 já coberto por is_link_local)
    except ValueError:
        pass

    return True


def validate_url(url: str, allowed_schemes: Set[str] = None) -> str:
    """
    Valida e sanitiza uma URL.
    
    Args:
        url: URL a validar
        allowed_schemes: Esquemas permitidos (default: http, https)
    
    Returns:
        URL sanitizada
    
    Raises:
        ValidationError: Se URL inválida
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL não pode ser vazia")
    
    url = url.strip()
    
    if allowed_schemes is None:
        allowed_schemes = {'http', 'https'}
    
    try:
        parsed = urlparse(url)
        
        # Valida esquema
        if parsed.scheme not in allowed_schemes:
            raise ValidationError(f"Esquema não permitido: {parsed.scheme}")
        
        # Valida hostname
        if not parsed.netloc:
            raise ValidationError("URL sem hostname válido")
        
        # Prevenção SSRF: host literais perigosos e IPs privados/loopback
        hostname = parsed.hostname
        if not hostname:
            raise ValidationError("URL sem hostname válido")
        if not _hostname_blocks_ssrf(hostname):
            raise ValidationError("Host não permitido (rede privada ou local)")

        # Evita credenciais embutidas na URL (reduz vazamento em logs de terceiros)
        if parsed.username is not None or parsed.password is not None:
            raise ValidationError("URLs com usuário/senha não são permitidas")

        # Valida formato básico
        if len(url) > 2048:  # Limite HTTP
            raise ValidationError("URL muito longa (máximo 2048 caracteres)")
        
        return url
    
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"URL inválida: {e}")


def sanitize_string(text: str, max_length: int = 2000, allow_html: bool = False) -> str:
    """
    Sanitiza string removendo caracteres perigosos.
    
    Args:
        text: Texto a sanitizar
        max_length: Comprimento máximo
        allow_html: Se False, remove tags HTML
    
    Returns:
        String sanitizada
    """
    if not text:
        return ""
    
    if not isinstance(text, str):
        text = str(text)
    
    # Remove caracteres de controle (exceto \n, \r, \t)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    
    # Remove HTML se não permitido
    if not allow_html:
        text = re.sub(r'<[^>]+>', '', text)
        # Escapa entidades HTML básicas
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Limita comprimento
    if len(text) > max_length:
        text = text[:max_length]
        log.warning(f"String truncada para {max_length} caracteres")
    
    return text.strip()


def validate_filters(filters: list) -> list:
    """
    PROPÓSITO DE NEGÓCIO: normalizar a lista de categorias que um servidor
    assina, aceitando nomes antigos em vez de os descartar em silêncio.

    INVARIANTES DO DOMÍNIO:
    - A autoridade sobre o que é categoria válida é o `core.filters`, não uma
      cópia da lista aqui. Duas listas divergem: esta rejeitava "musica"
      enquanto o CAT_MAP tinha o alias e o filtro o aceitava.
    - Nome legado é traduzido (musica → music), nome desconhecido é removido.

    COMPORTAMENTO EM CASO DE FALHA: levanta ValidationError se o argumento não
    for lista; devolve lista vazia se nada sobreviver à normalização.
    """
    if not isinstance(filters, list):
        raise ValidationError("Filtros devem ser uma lista")

    from core.filters import normalize_filters
    return normalize_filters(filters)


# =========================================================
# SECURITY CHECKS
# =========================================================

def is_safe_filename(filename: str) -> bool:
    """Verifica se um nome de arquivo é seguro."""
    if not filename:
        return False
    
    # Bloqueia path traversal
    dangerous = ['..', '/', '\\', '\x00']
    if any(d in filename for d in dangerous):
        return False
    
    # Bloqueia caracteres especiais
    if re.search(r'[<>:"|?*]', filename):
        return False
    
    return True


def check_discord_permissions(member, required_permissions: Set[str]) -> bool:
    """
    Verifica se um membro tem as permissões necessárias.
    
    Args:
        member: discord.Member
        required_permissions: Set de permissões necessárias
    
    Returns:
        True se tem todas as permissões
    """
    if not member:
        return False
    
    # Admin tem todas as permissões
    if member.guild_permissions.administrator:
        return True
    
    # Verifica permissões específicas
    for perm in required_permissions:
        if not getattr(member.guild_permissions, perm, False):
            return False
    
    return True


# =========================================================
# SECURITY AUDIT LOGGING
# =========================================================

def log_security_event(
    event_type: str,
    user_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    details: Optional[Dict] = None,
    severity: str = "INFO"
):
    """
    Registra evento de segurança para auditoria.
    
    Args:
        event_type: Tipo do evento (ex: 'RATE_LIMIT', 'INVALID_INPUT', 'PERMISSION_DENIED')
        user_id: ID do usuário (opcional)
        guild_id: ID da guild (opcional)
        details: Detalhes adicionais
        severity: Severidade (INFO, WARNING, ERROR, CRITICAL)
    """
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "severity": severity,
        "user_id": user_id,
        "guild_id": guild_id,
        "details": details or {}
    }
    
    # Log estruturado para fácil parsing
    log_msg = f"[SECURITY] {event_type} | User: {user_id} | Guild: {guild_id} | {details}"
    
    if severity == "CRITICAL":
        log.critical(log_msg)
    elif severity == "ERROR":
        log.error(log_msg)
    elif severity == "WARNING":
        log.warning(log_msg)
    else:
        log.info(log_msg)
    
    # TODO: Enviar para sistema de auditoria externo (ex: ELK, Splunk)


# =========================================================
# TOKEN VALIDATION
# =========================================================

def validate_discord_token(token: str) -> bool:
    """
    Valida formato básico de token Discord.
    
    Args:
        token: Token a validar
    
    Returns:
        True se formato válido
    """
    if not token or not isinstance(token, str):
        return False
    
    token = token.strip()
    
    # Tokens Discord têm formato específico.
    # Exemplo (forma genérica, NÃO real):
    #   <ID_USUÁRIO>.<TIMESTAMP>.<ASSINATURA_HMAC>
    # Formato: <user_id>.<timestamp>.<hmac>
    
    parts = token.split('.')
    if len(parts) != 3:
        return False
    
    # Verifica que cada parte tem conteúdo
    if not all(part for part in parts):
        return False
    
    # Verifica comprimento mínimo (tokens são longos)
    if len(token) < 50:
        return False
    
    return True
