import json
from core.filters import match_intel

titles = [
    ("Trailer de “O Grande Pecado de Kujo”｜Netflix", "Netflix Japan", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q"),
    ("O elenco de ONE PIECE conhece as risadas de ONE PIECE? | Netflix", "Still Watching Netflix", "https://www.youtube.com/feeds/videos.xml?channel_id=UClp1Q_Ui80Wf69A6YI67S3w"),
    ("Um Samurai Champloo de ação ao vivo?! + NOVAS reações ao trailer do anime Sekiro", "Crunchyroll", "https://www.youtube.com/feeds/videos.xml?channel_id=UC7wu64jFsV02bbu6UHUd7JA"),
    ("RuneScape: Dragonwilds – Trailer oficial do teaser mundial de Dowdun Reach", "GameTrailers", "some_gametrailers_source"),
    ("David Dastmalchian se tornando o Sr. 3 da Baroque Works na 2ª temporada de ONE PIECE", "Still Watching Netflix", "https://www.youtube.com/feeds/videos.xml?channel_id=UClp1Q_Ui80Wf69A6YI67S3w"),
    ("Pragmata - Trailer oficial de visão geral de 90 segundos", "IGN", "https://www.youtube.com/feeds/videos.xml?user=IGNentertainment"),
]

config = {
    "123": {"filters": ["todos"]}
}

for title, channel, source in titles:
    res = match_intel("123", title, "algum resumo de anime aqui (finge que o summary tem anime ou one piece)", config, source)
    print(f"Title: {title} | Result (todos): {res}")

config_games = {
    "123": {"filters": ["games"]}
}
for title, channel, source in titles:
    res = match_intel("123", title, "game of the year anime", config_games, source)
    print(f"Title (games): {title} | Result (games): {res}")
