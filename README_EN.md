# 🗞️ AnimeBootNews — Your Anime News Bot

<p align="center">
  <img alt="AnimeBootNews" src="./icon.png" width="300">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Discord-Bot-5865F2?logo=discord&logoColor=white" alt="Discord Bot" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Status-Active-success" alt="Status" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License MIT" />
</p>

<p align="center">
  <b>Smart RSS/Atom/YouTube feed monitoring exclusively focused on ANIME.</b><br>
  Filters out Games, Merch, and Clothes • Simple Dashboard • Fast Posting
</p>

---

## 📋 Index

- [✨ Features](#-features)
- [🧱 Architecture](#-architecture)
- [🚀 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [🧰 Commands](COMMANDS.md)
- [🎛️ Dashboard](#️-dashboard)
- [🧠 Filter System](#-filter-system)
- [🖥️ Deploy](#️-deploy)
- [📜 License](#-license)

---

## ✨ Features

| Feature | Description |
|---------|-----------|
| 📡 **Periodic Scanner** | Scans RSS/Atom/YouTube feeds every 30 minutes (configurable) |
| 🛡️ **Anti-Merch Filter** | **Natively blocks** games, toys, clothes, and figures. Total focus on ANIME. |
| 🎯 **Simple Categories** | Anime (Trailers/Eps), News (Announcements), and Music (OSTs/Openings). |
| 🎛️ **Persistent Dashboard** | Interactive dashboard with buttons that work even after a restart |
| 🔄 **Deduplication** | Never repeats news (history in `history.json`) |
| 🌐 **Multi-Guild** | Independent configuration per Discord server |
| 🎞️ **Native Player** | YouTube/Twitch videos play directly in chat (no browser needed) |
| 🌍 **Multi-Language** | Supports EN, PT, ES, IT (auto-detect + `/setlang`) |

---

## 🧠 Filter System

The key feature of **AnimeBootNews** is **Active Exclusion**.

### 🚫 What is AUTOMATICALLY BLOCKED?

Any news containing terms like:

- `gameplay`, `videogame`, `ps5`, `xbox`, `nintendo`
- `gunpla`, `figure`, `statue`, `toy`, `model kit`
- `t-shirt`, `apparel`, `clothing`, `fashion`

> **Goal:** If a new game or shirt comes out, the bot **IGNORES** it. We only want ANIME news.

### ✅ What is APPROVED?

If it passes the block above, we check if the category is active in the server (e.g., `Anime` or `Music`).

---

## 📜 License

MIT License.
