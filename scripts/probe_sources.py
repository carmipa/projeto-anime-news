"""
Sonda de saude de fontes — usa o CAMINHO REAL deste bot, nao um cliente HTTP paralelo.

PROPOSITO DE NEGOCIO: responder, com evidencia colavel, se cada fonte do catalogo ainda
rende noticia. Fonte morta em silencio e a falha mais comum deste tipo de bot: ela responde
200, devolve zero entradas ou conteudo congelado, e ninguem nota porque "0 noticias hoje"
parece um dia calmo. No bot irmao (projeto-bot-games) foram 20 de 64 fontes mortas sem que
o resumo da varredura acusasse uma unica.

INVARIANTES DO DOMINIO:
  1. Sonda pelo `_fetch_and_parse` DESTE scanner — o mesmo validate_url, os mesmos
     `source_headers` (User-Agent por fonte, que varias fontes japonesas exigem) e o mesmo
     feedparser. Sonda com cliente proprio mede outra coisa e aprova o que a producao
     recusa.
  2. `http_state` vazio de proposito: com o cache real, fonte saudavel responderia 304 e a
     sonda nao veria entrada nenhuma — leitura indistinguivel de fonte morta.
  3. O TITULO do feed e sempre impresso ao lado do nome configurado. Canal trocado ou
     handle ocupado por terceiro responde 200 com videos recentes; so o titulo denuncia.
  4. A sonda so vale depois da CALIBRACAO: um controle positivo que TEM de passar e um
     negativo que TEM de reprovar. Instrumento que nunca foi visto dizendo NAO nao prova
     nada quando diz SIM.

COMPORTAMENTO EM CASO DE FALHA: tres estados de saida, nunca dois.
  0 = PASSOU        todas as fontes sondadas estao saudaveis
  1 = REPROVOU      pelo menos uma esta doente
  2 = NAO VERIFICOU calibracao falhou ou nao havia alvo — nao e aprovacao nem reprovacao

Uso:
    .venv\\Scripts\\python.exe scripts\\probe_sources.py --catalogo
    .venv\\Scripts\\python.exe scripts\\probe_sources.py https://exemplo.com/feed
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import aiohttp  # noqa: E402
import certifi  # noqa: E402

from core.scanner import _CACHE_HIT, _extract_entry_datetime, _fetch_and_parse  # noqa: E402
from core.sources import load_sources, source_name  # noqa: E402

IDADE_MAXIMA_DIAS = 180
CONCORRENCIA = 5

# Controles. Positivo: feed estavel e no catalogo. Negativo: channel_id sintaticamente
# valido e inexistente — mesma forma dos IDs corrompidos que o bot irmao carregou por meses.
CONTROLE_POSITIVO = "https://www.animenewsnetwork.com/news/rss.xml"
CONTROLE_NEGATIVO = "https://www.youtube.com/feeds/videos.xml?channel_id=UCzzzzzzzzzzzzzzzzzzzzzz"


def _chave_de_comparacao(texto: str) -> str:
    """
    PROPOSITO DE NEGOCIO: comparar o titulo que o feed declara com o nome configurado no
    catalogo, para apanhar canal trocado — o defeito em que a fonte responde 200 com videos
    recentes mas de OUTRO canal, e so o titulo denuncia.

    INVARIANTES DO DOMINIO: a comparacao ignora o que nao distingue canal — maiusculas,
    espacos (inclusive o ideografico U+3000, comum em titulos japoneses), hifen, travessao e
    parenteses. A primeira versao comparava as strings cruas e produziu TRES falsos
    positivos no catalogo real, todos por pontuacao: `サンライズ SUNRISE` vs
    `サンライズ  SUNRISE` (espaco duplo), `ぽにきゃん Anime` vs `ぽにきゃん-Anime` (hifen) e
    `NEWS (英語版)` vs `NEWS(英語版)` (espaco antes do parentese). Alarme falso gasta a
    atencao de quem le e ensina a ignorar o aviso verdadeiro.

    COMPORTAMENTO EM CASO DE FALHA: entrada que nao for `str` devolve string vazia, e o
    chamador nao emite aviso nenhum — na duvida, calar e melhor que alarme falso.
    """
    if not isinstance(texto, str):
        return ""
    fora = " \t　-–—()[]｜|:：・.,'\"　"
    return "".join(c for c in texto.lower() if c not in fora)


@dataclass
class Resultado:
    url: str
    nome_configurado: str
    titulo_do_feed: str
    entradas: int
    idade_dias: int | None
    saudavel: bool
    motivo: str

    def linha(self) -> str:
        marca = "OK  " if self.saudavel else "FALHA"
        idade = f"{self.idade_dias}d" if self.idade_dias is not None else "-"
        divergencia = ""
        if self.titulo_do_feed and self.nome_configurado:
            a = _chave_de_comparacao(self.titulo_do_feed)
            b = _chave_de_comparacao(self.nome_configurado)
            if a and b and a not in b and b not in a:
                divergencia = "  <-- TITULO DIVERGE DO NOME CONFIGURADO"
        return (
            f"[{marca}] {self.nome_configurado}\n"
            f"        {self.url}\n"
            f"        entradas={self.entradas} recente={idade} "
            f"titulo={self.titulo_do_feed!r}{divergencia}"
            + (f"\n        motivo: {self.motivo}" if not self.saudavel else "")
        )


async def sondar(session, url: str, ssl_ctx) -> Resultado:
    nome = source_name(url) or url
    # Invariante 2: estado HTTP vazio, para nunca receber 304 e confundir cache com morte.
    _, feed = await _fetch_and_parse(session, url, {}, ssl_ctx)

    if feed is _CACHE_HIT:
        return Resultado(url, nome, "", 0, None, False,
                         "304 inesperado com cache vazio — investigar o fetch")
    if feed is None:
        return Resultado(url, nome, "", 0, None, False,
                         "o fetch do proprio bot rejeitou (rede, status != 200, SSRF ou parse)")

    entradas = getattr(feed, "entries", []) or []
    titulo = str(getattr(getattr(feed, "feed", None), "title", "") or "")

    if not entradas:
        return Resultado(url, nome, titulo, 0, None, False,
                         "200 sem entradas (feed descontinuado, bloqueio parcial ou HTML no lugar de XML)")

    agora = datetime.now(timezone.utc)
    idades = []
    for e in entradas:
        dt = _extract_entry_datetime(e)
        if dt is not None:
            idades.append((agora - dt).days)

    if not idades:
        return Resultado(url, nome, titulo, len(entradas), None, False,
                         "nenhuma entrada tem data — o scanner descartaria todas")

    recente = min(idades)
    if recente > IDADE_MAXIMA_DIAS:
        return Resultado(url, nome, titulo, len(entradas), recente, False,
                         f"congelado: item mais recente com {recente} dias (max {IDADE_MAXIMA_DIAS})")

    return Resultado(url, nome, titulo, len(entradas), recente, True, "")


async def _sondar_todas(urls: list[str]) -> list[Resultado]:
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    sem = asyncio.Semaphore(CONCORRENCIA)
    async with aiohttp.ClientSession() as session:
        async def _uma(u: str) -> Resultado:
            async with sem:
                return await sondar(session, u, ssl_ctx)
        return list(await asyncio.gather(*[_uma(u) for u in urls]))


async def calibrar() -> tuple[bool, str]:
    positivo, negativo = await _sondar_todas([CONTROLE_POSITIVO, CONTROLE_NEGATIVO])
    if not positivo.saudavel:
        return False, (
            f"controle POSITIVO reprovou ({CONTROLE_POSITIVO}: {positivo.motivo}). "
            "A sonda, a rede ou o proprio caminho do bot esta quebrado — o veredito sobre "
            "as outras fontes nao vale."
        )
    if negativo.saudavel:
        return False, (
            f"controle NEGATIVO passou ({CONTROLE_NEGATIVO}). A sonda nao sabe dizer NAO; "
            "qualquer 'OK' abaixo seria indistinguivel de cegueira."
        )
    return True, (
        f"controle positivo OK ({positivo.entradas} entradas, mais recente {positivo.idade_dias}d) | "
        f"controle negativo reprovou como esperado ({negativo.motivo})"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Sonda de saude de fontes do AnimeBot")
    ap.add_argument("urls", nargs="*", help="URLs a sondar")
    ap.add_argument("--catalogo", action="store_true", help="sonda tudo o que load_sources() devolve")
    ap.add_argument("--json", help="grava o resultado bruto neste caminho")
    args = ap.parse_args()

    alvos = list(args.urls)
    if args.catalogo:
        alvos.extend(load_sources())
    vistos: set[str] = set()
    alvos = [u for u in alvos if not (u in vistos or vistos.add(u))]

    if not alvos:
        print("NAO VERIFICOU: nenhuma URL alvo. Use --catalogo ou passe URLs.", file=sys.stderr)
        return 2

    calibrada, explicacao = asyncio.run(calibrar())
    print(f"[calibracao] {explicacao}\n")
    if not calibrada:
        print("NAO VERIFICOU: instrumento nao calibrado.", file=sys.stderr)
        return 2

    resultados = asyncio.run(_sondar_todas(alvos))
    for r in resultados:
        print(r.linha())

    doentes = [r for r in resultados if not r.saudavel]
    print(f"\nresumo: {len(resultados) - len(doentes)}/{len(resultados)} saudaveis")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in resultados], f, indent=2, ensure_ascii=False)
        print(f"json: {args.json}")

    return 1 if doentes else 0


if __name__ == "__main__":
    sys.exit(main())
