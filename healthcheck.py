#!/usr/bin/env python3
"""
Healthcheck do container do AnimeBootNews.

PROPÓSITO DE NEGÓCIO: responder se o bot está REALMENTE a funcionar, e não
apenas se o processo não morreu. O healthcheck anterior verificava
`os.path.exists('/app/config.json')` — um ficheiro montado por volume, portanto
sempre presente: reportava "healthy" com o bot travado, desconectado do Discord
ou com o loop de eventos bloqueado.

INVARIANTES DO DOMÍNIO:
- Se o dashboard web está ligado, a prova de vida é uma resposta HTTP do
  próprio processo: só responde quem tem o event loop a correr.
- Se o dashboard está desligado, a prova é a idade da última varredura
  registada em state.json, com folga de 2 ciclos antes de acusar problema.
- Antes da primeira varredura (arranque a frio) o container é considerado são;
  quem cobre esse período é o `start_period` do compose.
- Só usa a biblioteca padrão: o healthcheck não pode depender de nada que
  possa falhar a instalar.

COMPORTAMENTO EM CASO DE FALHA: termina com código 1 (unhealthy) e imprime o
motivo em stdout, que o Docker guarda em `.State.Health.Log`. Qualquer exceção
inesperada também dá 1 — na dúvida sobre a saúde, reporta doente.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta


def _flag(nome: str, padrao: str) -> str:
    return os.getenv(nome, padrao).strip().lower()


def _web_ligado() -> bool:
    return _flag("WEB_ENABLED", "true") in ("1", "true", "yes", "on")


def _inteiro(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, str(padrao)))
    except ValueError:
        return padrao


def verifica_web() -> tuple[bool, str]:
    porta = _inteiro("WEB_PORT", 8080)
    url = f"http://127.0.0.1:{porta}/"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                return True, f"dashboard respondeu 200 em {url}"
            return False, f"dashboard respondeu {resp.status} em {url}"
    except Exception as e:
        return False, f"dashboard não respondeu em {url}: {type(e).__name__}: {e}"


def verifica_ultima_varredura() -> tuple[bool, str]:
    # Mesmo DATA_DIR do bot (utils.storage): o state.json vive no volume de
    # diretório em Docker. Sem DATA_DIR, cai no /app de sempre.
    base = os.getenv("DATA_DIR", "").strip() or "/app"
    caminho = os.path.join(base, "state.json")
    if not os.path.exists(caminho):
        return True, "sem state.json ainda (arranque a frio)"
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            estado = json.load(f)
    except Exception as e:
        return False, f"state.json ilegível: {type(e).__name__}: {e}"

    ultima = (estado.get("_meta") or {}).get("last_scan")
    if not ultima:
        return True, "nenhuma varredura registada ainda (arranque a frio)"

    try:
        quando = datetime.fromisoformat(ultima)
    except ValueError:
        return False, f"last_scan inválido: {ultima!r}"

    limite = timedelta(minutes=_inteiro("LOOP_MINUTES", 720) * 2 + 30)
    idade = datetime.now() - quando
    if idade > limite:
        return False, f"última varredura há {idade} (limite {limite})"
    return True, f"última varredura há {idade}"


def main() -> int:
    if _web_ligado():
        ok, motivo = verifica_web()
    else:
        ok, motivo = verifica_ultima_varredura()
    print(motivo)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # nunca reportar saudável por acidente
        print(f"healthcheck falhou: {type(e).__name__}: {e}")
        sys.exit(1)
