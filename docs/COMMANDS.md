# 🧰 Comandos do AnimeBootNews

Este documento lista todos os comandos disponíveis no bot, suas funções e as permissões necessárias para uso.

## 📋 Comandos de Usuário

*(Disponíveis para todos os membros)*

### `/help`

Mostra a lista interativa de comandos disponíveis e links úteis.

### `/dashboard`

Abre o painel de controle pessoal onde você pode ver o status do bot e links rápidos para configuração.

### `/status`

Exibe estatísticas em tempo real do bot, incluindo:

- Tempo de atividade (Uptime)
- Total de notícias postadas
- Notícias bloqueadas (filtros)
- Memória e latência

### `/ping`

Verifica a latência da conexão entre o bot e o Discord. Útil para testar se o bot está respondendo.

### `/about`

Exibe informações sobre o projeto, versão, desenvolvedor e links do repositório.

### `/feeds`

Lista todos os feeds RSS e Canais do YouTube que estão sendo monitorados atualmente pelo bot.

---

## 🛡️ Comandos de Administrador

*(Requer permissão de Administrador ou Gerenciar Servidor)*

### `/setlang [idioma]`

Define o idioma em que o bot vai postar notícias e responder comandos neste servidor.

- **Opções:** `pt_BR`, `en_US`, `es_ES`, `it_IT`
- **Exemplo:** `/setlang pt_BR`

### `/set_canal`

Define o canal de texto **atual** onde o comando foi digitado como o canal oficial para receber as notícias.

- **Uso:** Vá até o canal desejado e digite `/set_canal`

### `/forcecheck`

Força uma varredura imediata de todas as fontes de notícias.

- *Nota: Use com moderação para evitar rate-limit das APIs.*

### `/audit`

Exibe um resumo dos **eventos de auditoria de segurança** recentes para este servidor:

- Mudanças de configuração (canal, filtros, idioma)
- Eventos de rate limit
- Erros relevantes de scanner / Discord

> Requer permissão de **Administrador**.

### `/audit_stats`

Mostra **estatísticas agregadas de segurança e auditoria** dos últimos dias:

- Total de eventos
- Quantidade de erros, avisos e eventos críticos
- Tipos de evento mais frequentes

> Requer permissão de **Administrador**.

---

## ⚡ Comandos Especiais (Dono do Bot)

*(Apenas para o dono da aplicação)*

### `/reload`

Recarrega todas as extensões (cogs) do bot sem precisar reiniciar o processo. Útil após atualizações de código.

### `/logs [linhas]`

Mostra as últimas linhas do log do sistema diretamente no chat.

- **Exemplo:** `/logs 20`

### `/clear_history`

Limpa o banco de dados local de notícias já postadas (`history.json`).

- *Cuidado: Isso fará com que notícias antigas sejam repostadas na próxima varredura.*
