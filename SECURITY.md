# 🔒 Política de Segurança e GRC - AnimeBootNews Bot

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Controles de Segurança](#controles-de-segurança)
3. [Governança](#governança)
4. [Gerenciamento de Riscos](#gerenciamento-de-riscos)
5. [Compliance](#compliance)
6. [Logs e Auditoria](#logs-e-auditoria)
7. [Resposta a Incidentes](#resposta-a-incidentes)

---

## 🎯 Visão Geral

Este documento descreve as políticas de segurança, governança, riscos e compliance (GRC) implementadas no **AnimeBootNews Bot**.

### Objetivos de Segurança

- ✅ Proteger dados de configuração e histórico
- ✅ Prevenir abuso de comandos e APIs
- ✅ Garantir rastreabilidade de ações administrativas
- ✅ Validar todas as entradas de usuário
- ✅ Monitorar e alertar sobre eventos de segurança

---

## 🛡️ Controles de Segurança

### 1. Validação de Entrada

#### Implementado

- **Validação de Guild ID**: Verifica formato numérico e comprimento
- **Validação de Channel ID**: Verifica formato de snowflake Discord
- **Validação de URLs**: Bloqueia URLs locais (prevenção SSRF)
- **Validação de Idioma**: Apenas idiomas suportados permitidos
- **Sanitização de Strings**: Remove HTML e caracteres de controle

#### Exemplo de Uso

```python
from utils.security import validate_guild_id, validate_url, sanitize_string

# Validação
guild_id = validate_guild_id(user_input)
url = validate_url(feed_url)
clean_text = sanitize_string(user_text, max_length=2000)
```

### 2. Rate Limiting

#### Implementado

- **Comandos**: 10 comandos/minuto por usuário
- **Scans**: 3 scans/5 minutos por usuário
- **Configuração**: 5 mudanças/minuto por usuário

#### Configuração

```python
from utils.security import command_rate_limiter, scan_rate_limiter

allowed, retry_after = await command_rate_limiter.is_allowed(user_id)
if not allowed:
    # Rate limit excedido
    pass
```

### 3. Validação de Token

- Formato Discord validado (3 partes separadas por `.`)
- Comprimento mínimo verificado
- Validação na inicialização do bot

### 4. Prevenção SSRF

- URLs locais bloqueadas (`localhost`, `127.0.0.1`, etc.)
- **Endurecido:** literais IPv4/IPv6 privados, loopback, link-local e multicast são rejeitados em `validate_url` (feeds não podem apontar para rede interna por IP direto).
- URLs com **usuário/senha embutidos** (`https://user:pass@...`) são rejeitadas (reduz vazamento acidental em logs).
- Apenas esquemas `http` e `https` permitidos.
- **Nota:** hostnames públicos que resolvem para IP interno (DNS) não são bloqueados sem resolver DNS — mantenha `sources.json` sob controle de confiança.

### 4.1 Dashboard web (`aiohttp`)

- Por padrão o servidor escuta em **`127.0.0.1`** (não expõe estatísticas na LAN inteira). Variáveis: `WEB_HOST`, `WEB_PORT`, `WEB_ENABLED` no `.env`.
- Em Docker/rede isolada, se precisar `WEB_HOST=0.0.0.0`, restrinja com firewall ou rede privada.
- Opcional: `WEB_API_SECRET` — se definido, **`/api/stats`** exige `Authorization: Bearer <segredo>`.

### 4.2 Componentes Discord (dashboard de filtros)

- Botões do painel verificam se a **guild da interação** corresponde ao painel, reduzindo abuso de `custom_id` entre servidores.
- Validação de hostname antes de requisições

### 5. Sanitização de Arquivos

- Validação de nomes de arquivo
- Prevenção de path traversal (`..`, `/`, `\`)
- Bloqueio de caracteres especiais

---

## 📊 Governança

### Estrutura de Dados

#### Arquivos de Configuração

- `config.json`: Configuração por guild (validado)
- `sources.json`: Feeds monitorados (validado)
- `history.json`: Histórico de notícias (protegido)
- `state.json`: Estado HTTP cache (protegido)
- `audit.json`: Logs de auditoria (somente leitura para bot)

#### Permissões de Arquivo

```bash
chmod 600 .env              # Secrets (somente owner)
chmod 644 config.json       # Configuração (leitura)
chmod 644 audit.json        # Auditoria (leitura)
```

### Controle de Acesso

#### Níveis de Permissão

1. **Usuário**: Comandos públicos (`/help`, `/status`, `/ping`)
2. **Administrador**: Comandos administrativos (`/dashboard`, `/forcecheck`, `/set_canal`)
3. **Dono do Bot**: Comandos especiais (futuro: `/reload`, `/logs`)

#### Verificação de Permissões

```python
from utils.security import check_discord_permissions

has_perms = check_discord_permissions(
    member,
    required_permissions={"manage_channels", "administrator"}
)
```

---

## ⚠️ Gerenciamento de Riscos

### Riscos Identificados

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Rate Limit Discord API | Média | Alto | Rate limiting interno, retry com backoff |
| Feed malicioso | Baixa | Médio | Validação de URL, sanitização |
| Configuração corrompida | Baixa | Alto | Validação de schema, backups |
| Token vazado | Baixa | Crítico | Validação de token, rotação recomendada |
| Abuso de comandos | Média | Médio | Rate limiting, auditoria |

### Matriz de Severidade

- **CRITICAL**: Token inválido, falha crítica do sistema
- **ERROR**: Erro em operação importante, scan falhou
- **WARNING**: Rate limit, permissão negada, validação falhou
- **INFO**: Operação normal, scan completado, config alterada

---

## ✅ Compliance

### LGPD / GDPR

#### Dados Coletados

- **Guild ID**: Identificador do servidor Discord
- **Channel ID**: Identificador do canal configurado
- **User ID**: Identificador do usuário (apenas em logs de auditoria)

#### Retenção de Dados

- **Histórico**: Últimas 1000 notícias (FIFO)
- **Auditoria**: Últimos 10.000 eventos
- **Cache HTTP**: Limpeza automática após 7 dias

#### Direitos do Usuário

- **Acesso**: Comando `/audit` para visualizar eventos relacionados
- **Exclusão**: Remover guild de `config.json` remove todos os dados
- **Portabilidade**: Exportar `config.json` e `audit.json`

### Logs de Compliance

Todos os eventos críticos são registrados em `audit.json`:

- Mudanças de configuração
- Acessos administrativos
- Erros de segurança
- Operações de dados

---

## 📝 Logs e Auditoria

### Sistema de Auditoria

#### Eventos Auditados

- `RATE_LIMIT_EXCEEDED`: Rate limit excedido
- `PERMISSION_DENIED`: Permissão negada
- `CONFIG_CHANGED`: Configuração alterada
- `CHANNEL_CHANGED`: Canal alterado
- `SCAN_STARTED`: Varredura iniciada
- `SCAN_COMPLETED`: Varredura completada
- `SCAN_FAILED`: Varredura falhou
- `ERROR_OCCURRED`: Erro ocorrido
- `BOT_STARTED`: Bot iniciado
- `BOT_STOPPED`: Bot parado

#### Formato de Log

```json
{
  "timestamp": "2026-02-13T10:30:45.123456",
  "event_type": "CONFIG_CHANGED",
  "severity": "INFO",
  "user_id": 123456789,
  "guild_id": 987654321,
  "details": {
    "old_channel": 111111,
    "new_channel": 222222
  },
  "metadata": {}
}
```

### Consulta de Auditoria

```python
from utils.audit import audit_logger, AuditEventType, AuditSeverity

# Consultar eventos
events = audit_logger.query(
    event_type=AuditEventType.CONFIG_CHANGED,
    guild_id=123456789,
    since=datetime.now() - timedelta(days=7),
    limit=100
)

# Estatísticas
stats = audit_logger.get_stats(days=7)
```

### Logs Estruturados

O sistema suporta logs em formato JSON estruturado:

```python
from utils.logger import log_with_context

log_with_context(
    log,
    logging.INFO,
    "Operação realizada",
    user_id=123456,
    guild_id=789012,
    event_type="OPERATION",
    details={"action": "config_update"}
)
```

---

## 🚨 Resposta a Incidentes

### Procedimento de Resposta

1. **Detecção**: Logs de auditoria e monitoramento
2. **Análise**: Consultar `audit.json` para contexto
3. **Contenção**: Desabilitar guild afetada se necessário
4. **Eradicação**: Corrigir vulnerabilidade
5. **Recuperação**: Restaurar configuração válida
6. **Lições Aprendidas**: Documentar incidente

### Comandos de Emergência

```bash
# Parar bot
docker-compose stop

# Ver logs recentes
docker-compose logs --tail=100 | grep ERROR

# Consultar auditoria
python -c "from utils.audit import audit_logger; print(audit_logger.get_stats(days=1))"

# Backup de emergência
tar -czf backup-emergency-$(date +%Y%m%d-%H%M%S).tar.gz config.json audit.json
```

### Contatos de Segurança

- **Issues**: [GitHub Issues](https://github.com/carmipa/anime-news-bot/issues)
- **Email**: (configurar conforme necessário)

---

## 🔄 Atualizações de Segurança

### Checklist de Atualização

- [ ] Revisar logs de auditoria
- [ ] Verificar vulnerabilidades conhecidas
- [ ] Atualizar dependências (`pip list --outdated`)
- [ ] Testar validações de entrada
- [ ] Verificar backups
- [ ] Atualizar documentação

### Dependências de Segurança

- `discord.py`: Atualizar regularmente
- `aiohttp`: Verificar CVE
- `feedparser`: Manter atualizado
- `certifi`: Atualizar certificados SSL

---

## 📚 Referências

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Discord.py Security](https://discordpy.readthedocs.io/en/stable/security.html)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security.html)

---

**Última atualização**: 2026-02-13  
**Versão**: 1.0  
**Responsável**: Equipe de Desenvolvimento
