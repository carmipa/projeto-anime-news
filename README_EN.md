<!-- English documentation for GitHub. Portuguese version: readme.md -->

# 🗞️ AnimeBootNews — Your Anime News Bot

<p align="center">
  <img alt="AnimeBootNews" src="./icon.png" width="260">
</p>

<p align="center">
  <a href="https://discord.com/developers/applications">
    <img src="https://img.shields.io/badge/Discord-Bot-5865F2?logo=discord&logoColor=white&style=flat-square" alt="Discord Bot" />
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white&style=flat-square" alt="Python 3.10+" />
  </a>
  <img src="https://img.shields.io/badge/Status-Active-success?style=flat-square" alt="Status" />
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License MIT" />
  </a>
  <a href="SECURITY.md">
    <img src="https://img.shields.io/badge/Security-Hardened-important?style=flat-square&logo=shield" alt="Security Hardened" />
  </a>
</p>

<p align="center">
  <b>Smart RSS/Atom/YouTube feed monitoring, 100% focused on ANIME.</b><br>
  Filters out Games, Merch, and Clothes • Interactive Dashboard • Real‑time Posting • Multi‑Language
</p>

<p align="center">
  🇧🇷 <a href="readme.md"><b>Versão em Português (PT‑BR)</b></a> • 🇺🇸 English (this file)
</p>

---

## 📋 Index

- [✨ Features](#-features)
- [🧱 Architecture](#-architecture)
- [🚀 Installation](#-installation)
- [⚙️ Configuration](#-configuration)
- [🧰 Commands](#-commands)
- [🎛️ Dashboard](#-dashboard)
- [🧠 Filter System](#-filter-system)
- [🌍 Multi‑Language](#-multi-language)
- [🔒 Security & Audit](#-security--audit)
- [🐳 Deploy](#-deploy)
- [📜 License](#-license)

---

## ✨ Features

| Feature | Description |
|---------|------------|
| 📡 **Periodic Scanner** | Scans RSS/Atom/YouTube feeds every **30 minutes** (configurable) |
| 🛡️ **Anti‑Merch Filter** | **Natively blocks** games, toys, clothes, and figures. Pure ANIME signal. |
| 🎯 **Smart Categories** | Anime (Trailers/Eps), News (Announcements), Music (OSTs/Openings) |
| 🎛️ **Persistent Dashboard** | Discord dashboard with buttons that survive restarts |
| 🔄 **Deduplication** | Never repeats news (`history.json` with rolling window) |
| 🌐 **Multi‑Guild** | Fully independent configuration per Discord server |
| 📝 **Structured Logs** | JSON logs + security audit trail in `audit.json` |
| 🛡️ **Security & GRC** | Input validation, rate limiting, token checks, detailed policy in `SECURITY.md` |
| 🎞️ **Native Player** | YouTube/Twitch videos with a built‑in “Watch Now” button |
| 🌍 **Multi‑Language** | `en_US`, `pt_BR`, `es_ES`, `it_IT` (auto‑detect + `/setlang`) |
| 🖥️ **Web Dashboard** | Status & stats at `http://localhost:8080` (aiohttp + Jinja2) |

---

## 🧱 Architecture

### 🧩 High‑Level Diagram (Mermaid)

```mermaid
flowchart LR
    subgraph Inputs[News Sources]
        RSS[RSS / Atom Feeds]
        YT[YouTube Channels]
    end

    subgraph Core[Core Scanner]
        SCAN[APScheduler\nScanner]
        PIPE[Processing\nPipeline]
        FILTER[FIlters & Categorization]
        TRANS[Translation]
    end

    subgraph DiscordSide[Discord Bot]
        DASH[Dashboard & Views]
        COGS[Cogs\n(/status, /feeds,\n/audit, /audit_stats)]
    end

    subgraph Web[Web Dashboard]
        WEB[aiohttp + Jinja2]
        API[REST API /api/*]
    end

    Inputs --> SCAN --> PIPE --> FILTER --> TRANS --> DiscordSide
    DiscordSide --> WEB
    PIPE -->|History / Cache| Storage[(JSON\nconfig/history/state)]
    PIPE -->|Audit Trail| Audit[(audit.json)]
```

### Components

- **Core Scanner**: Async HTTP (`aiohttp`) + `feedparser` + caching (ETag / Last‑Modified)
- **Filter Engine**: Category + blacklist/whitelist logic, tuned for anime‑only content
- **Discord Bot**: Slash commands (`/status`, `/feeds`, `/dashboard`, `/audit`, …)
- **Web Server**: aiohttp + Jinja2 dashboard and JSON endpoints (`/api/status`, `/api/stats`, …)
- **Persistence**: JSON files (`config.json`, `sources.json`, `history.json`, `state.json`, `audit.json`)

---

## 🚀 Installation

> For full step‑by‑step details (PT‑BR), see the main [readme.md](readme.md).

### 1️⃣ Requirements

- Python **3.10+**
- `pip`
- A Discord **Bot Token** (from the [Developer Portal](https://discord.com/developers/applications))

### 2️⃣ Clone & Virtualenv

```bash
git clone https://github.com/carmipa/gundam-news-discord.git
cd anime-news-bot

python -m venv .venv
.\.venv\Scripts\activate   # Windows
# or
source .venv/bin/activate  # macOS / Linux
```

### 3️⃣ Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4️⃣ Environment Variables

```bash
# .env
DISCORD_TOKEN=your_discord_bot_token_here
COMMAND_PREFIX=!
LOOP_MINUTES=30
```

### 5️⃣ Run

```bash
python main.py
```

You should see logs like:

- `✅ Logged in as BotName#1234`
- `📡 Scanner iniciado - próxima varredura em 30 minutos`
- `🌍 Web Dashboard iniciado em http://localhost:8080`

---

## ⚙️ Configuration

### `sources.json` – Feeds

Configure YouTube and RSS/Atom feeds:

```json
{
  "youtube_feeds": {
    "anime_studios": [
      "https://www.youtube.com/feeds/videos.xml?channel_id=UCWOA1ZGywLbqmigxE4Qlvuw"
    ]
  },
  "official_sites": {
    "anime_news": [
      "https://www.animenewsnetwork.com/news/rss.xml",
      "https://myanimelist.net/rss/news.xml"
    ]
  }
}
```

### `config.json` – Per‑Guild Settings

```json
{
  "YOUR_GUILD_ID": {
    "channel_id": 123456789,
    "filters": ["anime", "news", "music"],
    "language": "en_US",
    "enabled": true
  }
}
```

Use Discord’s **Developer Mode** to copy server and channel IDs.

---

## 🧰 Commands

> Full PT‑BR command reference: [COMMANDS.md](COMMANDS.md)

### User Commands

- `/help` – Help & links
- `/status` – Bot statistics (uptime, scans, posts)
- `/feeds` – Shows monitored feeds
- `/ping` – Latency check
- `/about` – About the project

### Admin Commands

- `/dashboard` – Opens the interactive dashboard in the current channel
- `/setlang` – Sets the bot language (per guild): `en_US`, `pt_BR`, `es_ES`, `it_IT`
- `/set_canal` – Sets the current channel as the news target
- `/forcecheck` – Forces an immediate scan of all sources
- `/audit` – Shows recent security audit events
- `/audit_stats` – Shows aggregated security/audit statistics

---

## 🎛️ Dashboard

- Toggle filters (Anime / News / Music / Games / Movies / Gunpla / All)
- See active filters for the current guild
- Reset configuration with a button
- Triggers a **manual scan** when you open it (so you see news immediately)

---

## 🧠 Filter System

The core principle is **Active Exclusion**:

- ❌ Blocks: `gameplay`, `ps5`, `xbox`, `nintendo`, `gunpla`, `figure`, `t-shirt`, …
- ✅ Allows: anime‑related content (episodes, trailers, OSTs, announcements)
- ✅ Uses strict anime keywords to avoid unrelated entertainment/news noise
- ✅ Uses colour‑coded cards in Discord embeds for launches, videos, reposts and normal news

See `core/filters.py` for the full list and customization.

---

## 🌍 Multi‑Language

- Supported: `en_US`, `pt_BR`, `es_ES`, `it_IT`
- Auto‑detects Discord guild locale
- Can be overridden via `/setlang`
- News content is automatically translated using `deep-translator`

---

## 🔒 Security & Audit

AnimeBootNews ships with a hardened security layer:

- Input validation (IDs, URLs, language, strings)
- Rate limiting for commands and scans
- Discord token validation at startup
- Structured audit trail in `audit.json`
- Commands `/audit` and `/audit_stats` for in‑Discord insights

See **[SECURITY.md](SECURITY.md)** for the full GRC policy.

---

## 🐳 Deploy

For a full production guide (Docker + VPS), see **[DEPLOY.md](DEPLOY.md)** (PT‑BR).

- Dockerfile + `docker-compose.yml` included
- Healthcheck, log rotation and persistent volumes
- Ready for 24/7 operation on a small VPS

---

## 📜 License

Released under the **MIT License**. See [`LICENSE`](LICENSE) for details.
