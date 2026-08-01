#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regressão dos casos que o Paulo reportou tendo visto no canal: conteúdo
live-action, variedades e beisebol do Netflix Japan a entrar num canal de
notícias de anime.

Duas coisas mudaram face à versão anterior deste ficheiro:

1. Rodava como script e trocava `sys.stdout` no import, o que corrompia a
   captura do pytest — por isso estava excluído da coleta e não corria em lado
   nenhum. Agora é um teste normal.
2. Todos os casos apontavam para o channel_id `UC14Yc2Qv92DMuyNRlHvpo2Q` a
   chamar-lhe "Netflix Japan". Esse ID é a **TOHO animation**. O engano não era
   só do teste: estava também no código, e punha um estúdio de anime a ser
   tratado como fonte mista. Os casos passaram a usar o canal verdadeiro.
"""
import pytest

from core.filters import match_intel

CONFIG = {
    "417746665219424277": {
        "filters": ["anime", "news", "games", "filmes"],
        "channel_id": 1426541539978510490,
        "language": "pt_BR",
    }
}
GUILD = "417746665219424277"

NETFLIX_JP = "https://www.youtube.com/feeds/videos.xml?channel_id=UCv2ejD5B1xOYtGB2cf80B8g"
TOHO = "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q"

BLOQUEAR = [
    ('"Se eu pudesse passar uma coisa" | Clássico Mundial de Beisebol 2026 | Netflix Japão',
     "beisebol"),
    ("#3 Samurai Japan Manager Pressão para se tornar o melhor do mundo: Tatsunori Hara x "
     "Kazunari Ninomiya | Clássico Mundial de Beisebol de 2026", "beisebol + manager"),
    ('Bem-vindo ao Lanche "Ai" | Este sou eu | Netflix Japão', "reality 'Este sou eu'"),
    ("Caso com as circunstâncias de Takuya e Ai | Este sou eu | Netflix Japão", "reality"),
    ('"Clássico Mundial de Beisebol 2026" | Canção de torcida do torneio Netflix | '
     'Koshi Inaba "Toque" | Filme Especial', "beisebol + canção de torcida"),
    ("Haruki Mochizuki se torna Ai! GRWM & Set Tour｜This is I｜Netflix Japan", "GRWM + set tour"),
    ("Kim Seon-ho x Go Yoon-jung - Primeiro beijo em frente a uma cachoeira particular | "
     "Você consegue interpretar o amor? | Netflix Japão", "dorama live-action"),
    ('Tour "Green Room" de Boys | O namorado 2 | Netflix Japão', "green room + o namorado"),
]


@pytest.mark.parametrize("titulo,motivo", BLOQUEAR)
def test_conteudo_nao_anime_do_netflix_japan_e_bloqueado(titulo, motivo):
    assert match_intel(GUILD, titulo, "Netflix Japan", CONFIG, source=NETFLIX_JP) is False, motivo


def test_anime_de_estudio_confiavel_passa():
    assert match_intel(
        GUILD, "New Anime Trailer Released", "Sunrise studio announces new series",
        CONFIG, source=TOHO,
    ) is True


def test_anime_de_fonte_rss_desconhecida_passa():
    assert match_intel(
        GUILD, "Crunchyroll adds new Manga titles", "Spring season announcements",
        CONFIG, source="https://rss.feed/test",
    ) is True
