"""
Stats module - contadores da varredura e VEREDITO DE SAÚDE por ciclo.

PROPÓSITO DE NEGÓCIO:
    Um painel que só mede SUCESSO é indistinguível de um painel que não mede nada:
    `feeds_falhos=0` tanto significa "nenhuma fonte falhou" quanto "o contador nunca
    foi alimentado". Este módulo mede também a AUSÊNCIA — fontes que pararam de
    entregar, ciclos sem publicar, itens novos descartados por falta de data — e
    fecha cada varredura com um veredito explícito e o motivo dele. Sem isto, uma
    varredura em que metade das fontes morreu tem a mesma aparência de um dia
    tranquilo sem notícia.

INVARIANTES DO DOMÍNIO:
    - Todo veredito diferente de OK vem com pelo menos um MOTIVO textual; veredito
      sem motivo é rótulo, não diagnóstico.
    - O zero legítimo é dito com todas as letras: "0 publicadas, e as fontes que
      responderam não tinham novidade" é um motivo registado, nunca silêncio.
    - Nenhum contador vira veredito sozinho: a PROPORÇÃO decide. 1 falha em 50 é
      ruído; 25 em 50 é anomalia.
    - `fontes_totais == 0` é ANOMALIA, nunca OK — catálogo vazio é a falha que este
      instrumento existe para apanhar.
    - Semeadura NÃO é ciclo sem envio: uma varredura que só marcou o acervo de fontes
      novas como visto (sem publicar) envia 0 de propósito, e isso é OK.

COMPORTAMENTO EM CASO DE FALHA:
    `avaliar_varredura` NÃO levanta. Entradas negativas ou de tipo inesperado são
    normalizadas para -1 e o pior caso devolve ANOMALIA com o motivo "contadores
    inválidos" — visível, nunca um OK por omissão (fail-closed).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

# Vereditos possíveis de uma varredura. Três estados, nunca dois — "não verificou"
# (contadores inválidos) não é aprovação, é ANOMALIA.
VEREDITO_OK = "OK"
VEREDITO_ATENCAO = "ATENCAO"
VEREDITO_ANOMALIA = "ANOMALIA"


class BotStats:
    def __init__(self):
        self.start_time = datetime.now()
        self.scans_completed = 0
        self.news_posted = 0
        self.cache_hits_total = 0
        self.last_scan_time = None
        self.errors_count = 0
        # Último veredito de saúde da varredura (dict de avaliar_varredura), para o
        # comando de status ler sem reprocessar. Sobrevive em memória; a cópia
        # persistida vive em state.json["_meta"]["ultimo_veredito"].
        self.ultimo_veredito: Optional[Dict[str, Any]] = None

    def format_uptime(self):
        delta = datetime.now() - self.start_time
        # Simplified formatting
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"


def avaliar_varredura(
    fontes_totais: int,
    feeds_falhos: int,
    feeds_vazios: int,
    itens_sem_data: int,
    itens_examinados: int,
    enviadas: int,
    semeados: int,
    cache_hits: int,
    ciclos_sem_envio: int,
) -> Dict[str, Any]:
    """
    Fecha uma varredura com veredito e MOTIVO, medindo ausência e não só sucesso.

    PROPÓSITO DE NEGÓCIO: ver o cabeçalho do módulo — é o painel de saúde do bot.

    INVARIANTES DO DOMÍNIO: ver o cabeçalho do módulo. Em especial: proporção decide,
    catálogo vazio é ANOMALIA, semeadura não é ciclo sem envio, zero legítimo é dito.

    COMPORTAMENTO EM CASO DE FALHA: não levanta; contador inválido → ANOMALIA
    "contadores inválidos" (fail-closed). `itens_sem_data` é gatilho por PROPORÇÃO
    sobre `itens_examinados` (itens novos que chegaram ao check de data), não por
    limiar cru: só alarma quando a maioria dos itens novos cai sem data.
    """
    def _n(v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            return -1
        return v if v >= 0 else -1

    metricas = {
        "fontes_totais": _n(fontes_totais),
        "feeds_falhos": _n(feeds_falhos),
        "feeds_vazios": _n(feeds_vazios),
        "itens_sem_data": _n(itens_sem_data),
        "enviadas": _n(enviadas),
        "semeados": _n(semeados),
        "cache_hits": _n(cache_hits),
        "itens_examinados": _n(itens_examinados),
        "ciclos_sem_envio": _n(ciclos_sem_envio),
    }
    if any(v < 0 for v in metricas.values()):
        return {
            "veredito": VEREDITO_ANOMALIA,
            "motivos": ["contadores inválidos — a medição não é confiável"],
            "metricas": metricas,
            "quando": datetime.now().isoformat(timespec="seconds"),
        }

    motivos: List[str] = []
    veredito = VEREDITO_OK

    def _sobe(novo: str) -> None:
        nonlocal veredito
        ordem = {VEREDITO_OK: 0, VEREDITO_ATENCAO: 1, VEREDITO_ANOMALIA: 2}
        if ordem[novo] > ordem[veredito]:
            veredito = novo

    total = metricas["fontes_totais"]
    falhos = metricas["feeds_falhos"]
    vazios = metricas["feeds_vazios"]

    if total == 0:
        motivos.append("catálogo vazio: nenhuma fonte foi carregada")
        _sobe(VEREDITO_ANOMALIA)
    else:
        # Fontes que não entregaram nada, por falha ou por responder 200 sem itens.
        mudas = falhos + vazios
        proporcao = mudas / total
        if proporcao >= 0.5:
            motivos.append(
                f"{mudas} de {total} fontes não entregaram nada "
                f"({falhos} falharam, {vazios} responderam vazias)"
            )
            _sobe(VEREDITO_ANOMALIA)
        elif proporcao >= 0.25:
            motivos.append(
                f"{mudas} de {total} fontes não entregaram nada "
                f"({falhos} falharam, {vazios} responderam vazias)"
            )
            _sobe(VEREDITO_ATENCAO)

    # Itens novos descartados por falta de data. Proporção sobre os itens novos
    # examinados (não limiar cru): se a maioria cai sem data, a extração de data
    # quebrou para aquele lote (a fonte mudou o formato do feed).
    examinados = metricas["itens_examinados"]
    sem_data = metricas["itens_sem_data"]
    if examinados > 0:
        prop_sem_data = sem_data / examinados
        if prop_sem_data >= 0.5:
            motivos.append(
                f"{sem_data} de {examinados} itens novos descartados por falta de "
                "data (extração de data possivelmente quebrada)"
            )
            _sobe(VEREDITO_ANOMALIA)
        elif prop_sem_data >= 0.25:
            motivos.append(
                f"{sem_data} de {examinados} itens novos descartados por falta de data"
            )
            _sobe(VEREDITO_ATENCAO)

    if metricas["enviadas"] == 0:
        if metricas["semeados"] > 0:
            # Semeadura de fonte nova: envio zero é esperado, e vira publicação
            # normal no próximo ciclo. NÃO é ausência de entrega.
            motivos.append(
                f"0 publicadas: {metricas['semeados']} fonte(s) nova(s) semeada(s); "
                "publicação começa no próximo ciclo"
            )
        elif ciclos_sem_envio >= 24:
            motivos.append(
                f"{ciclos_sem_envio} ciclos seguidos sem publicar nada"
            )
            _sobe(VEREDITO_ANOMALIA)
        elif ciclos_sem_envio >= 6:
            motivos.append(
                f"{ciclos_sem_envio} ciclos seguidos sem publicar nada"
            )
            _sobe(VEREDITO_ATENCAO)
        else:
            # O zero legítimo, dito com todas as letras.
            motivos.append(
                "0 publicadas neste ciclo — sem novidade nas fontes que responderam"
            )

    if veredito == VEREDITO_OK and not motivos:
        motivos.append(
            f"{metricas['enviadas']} publicadas, "
            f"{total - falhos - vazios} de {total} fontes entregaram"
        )

    return {
        "veredito": veredito,
        "motivos": motivos,
        "metricas": metricas,
        "quando": datetime.now().isoformat(timespec="seconds"),
    }


stats = BotStats()
