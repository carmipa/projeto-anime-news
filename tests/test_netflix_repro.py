
import pytest
from core.filters import match_intel

@pytest.mark.parametrize("title, summary, source, should_pass", [
    # Cases reported by user (Should BLOCK)
    ("Trailer de Peaky Blinders: O Imortal - Netflix", "Descrição genérica", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),
    ("Trailer de 'Namorado Mensal' - Netflix", "Descrição genérica", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),
    ("Trailer da série de documentários Netflix 'DIAMOND TRUTH' - Netflix", "Descrição genérica", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),
    ("Apresentando Ronnie Hawkins, o personagem principal de Ronnie the Hawk - Netflix", "Netflix Japan", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", False),
    
    # Control cases (Should PASS)
    ("Trailer de Gundam Requiem for Vengeance - Netflix", "Anime mecha legal", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", True),
    ("SPY x FAMILY Season 3 Teaser", "Anya volta", "https://www.youtube.com/feeds/videos.xml?channel_id=UC14Yc2Qv92DMuyNRlHvpo2Q", True),
])
def test_netflix_filters(title, summary, source, should_pass):
    # Config mock
    config = {
        "guild1": {
            "filters": ["todos"] # "todos" enables general anime checks
        }
    }
    
    result = match_intel("guild1", title, summary, config, source=source)
    
    if should_pass:
        assert result is True, f"Should have PASSED: {title}"
    else:
        assert result is False, f"Should have BLOCKED: {title}"
