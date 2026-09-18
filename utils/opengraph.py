"""
Resolução da imagem de destaque de uma notícia a partir da PÁGINA do artigo.

Existe porque o feed RSS de várias fontes deste catálogo não traz imagem
nenhuma. Medido em 2026-09-18 sobre os feeds reais: animeanime.jp e
animecorner.me não trazem media:thumbnail, media:content, enclosure nem <img>
no summary — e as duas publicam og:image específico POR ARTIGO. Sem este
módulo, toda notícia dessas fontes sai no Discord sem imagem.

Portado do bot irmão gundam-news-discord por DUPLICAÇÃO CONSCIENTE
(regra-arquitetura-desacoplamento §2 e §9: não criar shared/ funcional entre
os bots). Não é cópia: o contrato de validate_url diverge entre os dois bots —
lá devolve tupla (is_valid, msg), aqui LEVANTA ValidationError — e o pacing e
o proxy de saída deste bot não existem no outro.
"""
import asyncio
import random
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from settings import (
    CLOUDFLARE_PROXY_URL,
    CLOUDFLARE_PROXY_SECRET,
    FEED_JITTER_MIN,
    FEED_JITTER_MAX,
)
from utils.logger import log
from utils.security import validate_url

# Crawler social: muitas publicações só renderizam as meta tags de OpenGraph
# para quem se identifica como tal. User-Agent de navegador comum recebe, em
# alguns sites, a página do consentimento de cookies, que não tem og:image.
_OG_USER_AGENT = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
)

# Teto por artigo. A imagem é ENFEITE: a notícia sai sem ela. Esperar mais que
# isto por um enfeite atrasaria a publicação de notícia que já está pronta.
_OG_TIMEOUT_S = 8

# Só o <head> interessa, e ele vem primeiro. Ler o artigo inteiro gastaria
# banda e memória por nada; páginas de notícia passam de 1 MB com folga.
_MAX_BYTES = 262144

# Um único salto, validado. Zero redirecionamento quebraria http->https
# legítimo; seguir à vontade reabriria o SSRF que validate_url fecha, porque
# o destino do salto NÃO passa por validate_url nenhuma.
_MAX_REDIRECTS = 1
_STATUS_REDIRECT = (301, 302, 303, 307, 308)


async def fetch_og_image(
    url: str,
    session: aiohttp.ClientSession,
    ssl_ctx=None,
) -> Optional[str]:
    """
    Busca a imagem de destaque na página do artigo (OpenGraph e equivalentes).

    PROPÓSITO DE NEGÓCIO:
        Dá ao card do Discord a imagem que identifica o anime da notícia,
        quando a fonte não a publica no feed. É o passo que faltava para as
        fontes que só expõem a imagem no HTML do artigo.

    INVARIANTES DO DOMÍNIO:
        - INV-IMG-1: NENHUMA falha aqui pode impedir a publicação da notícia.
          Esta função não levanta: devolve None e quem chama segue sem imagem.
        - INV-IMG-2: nenhuma URL fora de http(s) para host público é buscada,
          INCLUSIVE depois de redirecionamento. O link vem de feed externo, e
          o destino de um 302 não passaria por validate_url nenhuma.
        - A URL devolvida é sempre absoluta: og:image relativo é resolvido
          contra a página, porque o Discord recusa URL relativa.
        - O parse do HTML NÃO corre no event loop (é CPU-bound e atrasaria o
          heartbeat do gateway; classe 3.8 do manutencao-de-bots).

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve None em todos os desfechos ruins, cada um com motivo logado
        (classe 3.9: motivo de rejeição nunca é descartado): URL reprovada na
        validação, host inalcançável, timeout, status diferente de 200,
        redirecionamento para destino não validado, HTML sem tag servível.
        Nunca levanta e nunca devolve string vazia.
    """
    if not url:
        return None

    try:
        alvo = validate_url(url)
    except Exception as e:
        log.debug(f"[OG] URL reprovada na validacao, sem imagem: {url} - {e}")
        return None

    # Mesmo pacing do fetch de feeds. O GET do artigo sai do MESMO IP de
    # datacenter que já tomou bloqueio do Google e da Siliconera, e é um
    # pedido a mais por notícia — sem espalhar, este módulo reabriria o
    # risco que o commit 6001365 fechou.
    if FEED_JITTER_MAX > 0:
        await asyncio.sleep(random.uniform(FEED_JITTER_MIN, FEED_JITTER_MAX))

    html = await _baixar_html(alvo, session, ssl_ctx)
    if not html:
        return None

    # BeautifulSoup é CPU-bound: fora do event loop, sempre.
    loop = asyncio.get_running_loop()
    bruta = await loop.run_in_executor(None, _extrair_imagem, html)
    if not bruta:
        log.debug(f"[OG] Pagina sem tag de imagem servivel: {alvo}")
        return None

    absoluta = urljoin(alvo, bruta.strip())
    if not absoluta.startswith(("http://", "https://")):
        log.debug(f"[OG] Imagem descartada por esquema nao http(s): {bruta[:80]}")
        return None
    return absoluta


async def _baixar_html(
    alvo: str,
    session: aiohttp.ClientSession,
    ssl_ctx,
) -> Optional[str]:
    """
    Baixa o HTML do artigo, seguindo no máximo um redirecionamento validado.

    PROPÓSITO DE NEGÓCIO:
        Entregar o HTML do artigo para a extração da imagem, sem que o link
        vindo de um feed externo vire um pedido a endereço interno.

    INVARIANTES DO DOMÍNIO:
        - Todo endereço efetivamente buscado passou por validate_url antes,
          incluindo o destino do redirecionamento (INV-IMG-2).
        - No máximo _MAX_REDIRECTS saltos; o segundo 302 é abandonado.
        - Lê no máximo _MAX_BYTES; o <head> vem antes disso.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve None com o motivo em log de debug. Nunca levanta.
    """
    visitados = 0
    while True:
        try:
            via_proxy = bool(CLOUDFLARE_PROXY_URL and _quer_proxy(alvo))
            headers = {
                "User-Agent": _OG_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            if via_proxy and CLOUDFLARE_PROXY_SECRET:
                headers["X-Proxy-Secret"] = CLOUDFLARE_PROXY_SECRET
            pedido = f"{CLOUDFLARE_PROXY_URL}{alvo}" if via_proxy else alvo

            async with session.get(
                pedido,
                headers=headers,
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=_OG_TIMEOUT_S),
                allow_redirects=False,
            ) as resp:
                if resp.status in _STATUS_REDIRECT:
                    destino = resp.headers.get("Location", "")
                    if visitados >= _MAX_REDIRECTS or not destino:
                        log.debug(f"[OG] Redirecionamento nao seguido ({resp.status}): {alvo}")
                        return None
                    candidato = urljoin(alvo, destino)
                    try:
                        alvo = validate_url(candidato)
                    except Exception as e:
                        log.debug(f"[OG] Destino de redirecionamento reprovado: {candidato[:120]} - {e}")
                        return None
                    visitados += 1
                    continue

                if resp.status != 200:
                    log.debug(f"[OG] HTTP {resp.status} ao buscar artigo: {alvo}")
                    return None

                bruto = await resp.content.read(_MAX_BYTES)
                return bruto.decode(resp.charset or "utf-8", errors="replace")

        except asyncio.TimeoutError:
            log.debug(f"[OG] Timeout de {_OG_TIMEOUT_S}s no artigo: {alvo}")
            return None
        except Exception as e:
            log.debug(f"[OG] Falha ao buscar artigo {alvo}: {type(e).__name__}: {e}")
            return None


def _quer_proxy(url: str) -> bool:
    """
    Diz se o GET do artigo deve sair pelo proxy de saída.

    PROPÓSITO DE NEGÓCIO:
        Reusar a decisão que o catálogo já toma para a FONTE, agora para o
        domínio do artigo — é o mesmo IP tomando o mesmo bloqueio.

    INVARIANTES DO DOMÍNIO:
        - Consulta o critério da produção (core.sources), nunca o reimplementa
          (regra-medicao-perguntar-a-producao §1).
        - Import local de propósito: utils/ não depende de core/ no topo, para
          não criar ciclo de importação.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve False (busca direta) se o catálogo não puder ser consultado.
    """
    try:
        from core.sources import source_wants_proxy
        return source_wants_proxy(url)
    except Exception:
        return False


def _extrair_imagem(html: str) -> Optional[str]:
    """
    Extrai a URL da imagem de destaque do HTML. SÍNCRONA de propósito.

    PROPÓSITO DE NEGÓCIO:
        Achar, entre as meta tags da página, a imagem que a própria publicação
        declara como representativa do artigo.

    INVARIANTES DO DOMÍNIO:
        - É CPU-bound e NÃO corre no event loop; quem chama usa executor.
        - Ordem de preferência fixa: OpenGraph > Twitter Card > itemprop >
          link rel=image_src. A primeira que existir ganha, porque og:image é
          a que a publicação mantém para os agregadores.
        - Não devolve string vazia: content presente mas vazio é ignorado.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve None quando nenhuma tag serve. HTML malformado é tolerado pelo
        parser; qualquer exceção propaga para o chamador, que já a converte em
        None — imagem ausente nunca impede o envio.
    """
    sopa = BeautifulSoup(html, "html.parser")

    og = (
        sopa.find("meta", attrs={"property": "og:image"})
        or sopa.find("meta", attrs={"name": "og:image"})
        or sopa.find("meta", attrs={"property": "og:image:secure_url"})
    )
    if og and (og.get("content") or "").strip():
        return og["content"]

    tw = (
        sopa.find("meta", attrs={"name": "twitter:image"})
        or sopa.find("meta", attrs={"property": "twitter:image"})
    )
    if tw and (tw.get("content") or "").strip():
        return tw["content"]

    ip = sopa.find("meta", attrs={"itemprop": "image"})
    if ip and (ip.get("content") or "").strip():
        return ip["content"]

    ls = sopa.find("link", rel="image_src")
    if ls and (ls.get("href") or "").strip():
        return ls["href"]

    return None


def imagem_publicavel(url: str) -> Optional[str]:
    """
    Decide se uma URL de imagem pode ir para o embed do Discord.

    PROPÓSITO DE NEGÓCIO:
        Impedir que uma imagem ruim APAGUE a notícia. O Discord recusa o embed
        inteiro com 400 (error code 50035) quando a URL de imagem é inválida;
        a notícia falha em todas as guilds, não entra no dedup, e o ciclo
        seguinte tenta de novo — para sempre. Foi medido no bot irmão em
        2026-08-30 (guild 417746665219424277, o mesmo item de hora em hora
        durante dias) pela mesma causa: embed recusado que nunca é marcado
        como entregue.

    INVARIANTES DO DOMÍNIO:
        - Só devolve URL absoluta http(s) para host público (reusa validate_url,
          o mesmo critério anti-SSRF do resto do bot).
        - Nunca levanta: é chamada no caminho de publicação.
        - Devolve None em vez de string vazia, para o chamador ter um teste só.

    COMPORTAMENTO EM CASO DE FALHA:
        Devolve None; a notícia sai SEM imagem, que é o desfecho seguro.
        Notícia sem imagem é lida; notícia recusada pela API não existe.
    """
    if not url or not isinstance(url, str):
        return None
    limpa = url.strip()
    if not limpa.startswith(("http://", "https://")):
        return None
    try:
        validate_url(limpa)
    except Exception as e:
        log.debug(f"[IMG] URL de imagem descartada: {limpa[:120]} - {e}")
        return None
    if not urlparse(limpa).netloc:
        return None
    return limpa
