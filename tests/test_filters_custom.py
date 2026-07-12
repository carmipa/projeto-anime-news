"""
Smoke tests de casos "reais" reportados no canal.

Antes este arquivo tinha código no nível de módulo com print() de caracteres
japoneses, o que quebrava a COLETA do pytest no console cp1252 (Windows).
Convertido para testes de verdade: verificam apenas que match_intel roda sem
estourar e retorna bool para conteúdo variado (sem asserções de valor, já que
os valores esperados vivem em test_filter_logic.py).
"""
import pytest
from core.filters import match_intel

# (título, canal, source do feed)
REPORTED_TITLES = [
    ("Trailer de “O Grande Pecado de Kujo”｜Netflix", "Netflix Japan",
     "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q"),
    ("O elenco de ONE PIECE conhece as risadas de ONE PIECE? | Netflix", "Still Watching Netflix",
     "https://www.youtube.com/feeds/videos.xml?channel_id=UClp1Q_Ui80Wf69A6YI67S3w"),
    ("Um Samurai Champloo de ação ao vivo?! + NOVAS reações ao trailer do anime Sekiro", "Crunchyroll",
     "https://www.youtube.com/feeds/videos.xml?channel_id=UC7wu64jFsV02bbu6UHUd7JA"),
    ("RuneScape: Dragonwilds – Trailer oficial do teaser mundial de Dowdun Reach", "GameTrailers",
     "some_gametrailers_source"),
    ("David Dastmalchian se tornando o Sr. 3 da Baroque Works na 2ª temporada de ONE PIECE", "Still Watching Netflix",
     "https://www.youtube.com/feeds/videos.xml?channel_id=UClp1Q_Ui80Wf69A6YI67S3w"),
    ("Pragmata - Trailer oficial de visão geral de 90 segundos", "IGN",
     "https://www.youtube.com/feeds/videos.xml?user=IGNentertainment"),
]


@pytest.mark.parametrize("title, channel, source", REPORTED_TITLES)
def test_match_intel_todos_returns_bool(title, channel, source):
    config = {"123": {"filters": ["todos"]}}
    result = match_intel("123", title, "resumo de anime one piece", config, source)
    assert isinstance(result, bool)


@pytest.mark.parametrize("title, channel, source", REPORTED_TITLES)
def test_match_intel_games_returns_bool(title, channel, source):
    config = {"123": {"filters": ["games"]}}
    result = match_intel("123", title, "game of the year anime", config, source)
    assert isinstance(result, bool)
