import pytest
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.filters import match_intel

# Dummy config
CONFIG = {
    "417746665219424277": {
        "filters": ["anime", "news", "games", "filmes"],
        "channel_id": 1426541539978510490,
        "language": "pt_BR"
    }
}

GUILD_ID = "417746665219424277"

@pytest.mark.parametrize("title, summary, source, expected", [
    # Reported Failures - Sports
    ("“Clássico Mundial de Beisebol 2026” | Canção de torcida", "World Baseball Classic", "https://youtube.com/feeds/videos.xml?user=netflixjp", False),
    ("#3 Samurai Japan Manager Pressão para se tornar o melhor do mundo", "Tatsunori Hara x Kazunari Ninomiya", "https://youtube.com/feeds/videos.xml?user=netflixjp", False),
    
    # Reported Failures - Reality/Documentary
    ("Tour 'Green Room' de Boys🚩 | O namorado 2 | Netflix Japão", "The Boyfriend 2", "https://youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),
    ("Haruki Mochizuki se torna Ai! GRWM & Set Tour｜This is I", "Netflix Japan", "https://youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),
    
    # Reported Failures - Sato Company (Untrusted now)
    ("“Kokuho – O Preço da Perfeição” está dando o que falar.", "Sato Company movie", "https://youtube.com/feeds/videos.xml?channel_id=UC0-5Baz14QkUcJ6fAYAkbAQ", False),
    ("Dollhouse | Trailer Oficial (Legendado)", "Sato Company film", "https://youtube.com/feeds/videos.xml?channel_id=UC0-5Baz14QkUcJ6fAYAkbAQ", False),
    
    # Reported Failures - Tokusatsu (Should be blocked if no anime terms)
    ("Trailer KAMEN RIDER ZEZTZ | EP 22", "TokuSato Official", "https://youtube.com/feeds/videos.xml?channel_id=UCivtAzCENYI1jb6Clxydvdw", False),
    
    # Reported Failures - Music/Idols
    ("[TWICE 2025] One in a Mill10n | Trailer Oficial", "Twice K-pop", "https://youtube.com/feeds/videos.xml?channel_id=UC0-5Baz14QkUcJ6fAYAkbAQ", False),
    ("Os membros que serão os últimos do filme especial são... | projeto timelesz -REAL-", "Netflix Japan", "https://youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),

    # Valid Anime Content (Should still pass)
    ("New Anime 'Gundam' Trailer Released", "Sunrise studio", "https://youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", True),
    ("Crunchyroll adds new Manga titles", "Spring season", "https://rss.feed/test", True),
])
def test_filter_reported_cases(title, summary, source, expected):
    result = match_intel(GUILD_ID, title, summary, CONFIG, source=source)
    assert result == expected, f"Failed for: {title} (Source: {source})"

def test_case_sensitivity_fix():
    # Test that Netflix (Mixed Case) is caught by the hint "user=netflix"
    title = "Random Netflix Movie"
    source = "https://www.youtube.com/feeds/videos.xml?USER=NETFLIX"
    # Should be untrusted and block due to lack of anime terms
    assert match_intel(GUILD_ID, title, "Summary", CONFIG, source=source) is False

@pytest.mark.parametrize("title, summary, expected", [
    ("野球のニュース", "Baseball news", False),
    ("サッカー大会", "Soccer tournament", False),
])
def test_japanese_sports_terms(title, summary, expected):
    assert match_intel(GUILD_ID, title, summary, CONFIG, source="trusted") == expected
