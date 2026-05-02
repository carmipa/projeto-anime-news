import pytest
from core.filters import _contains_any

def test_contains_any_basic_match():
    """Test verification of basic keyword matches."""
    keywords = ["naruto", "sasuke"]
    assert _contains_any("i love naruto", keywords) is True
    assert _contains_any("sasuke is cool", keywords) is True
    assert _contains_any("no ninjas here", keywords) is False

def test_contains_any_word_boundaries():
    """Test that it respects word boundaries (no partial matches)."""
    keywords = ["naruto", "bleach"]
    
    # Should NOT match
    assert _contains_any("drawing a picture", keywords) is False
    assert _contains_any("bleachy place", keywords) is False
    assert _contains_any("narutoing", keywords) is False
    
    # Should MATCH
    assert _contains_any("naruto shippuden", keywords) is True
    assert _contains_any("bleach thousand year", keywords) is True

def test_contains_any_plurals():
    """Test that regular plural check works (optional 's')."""
    # Note: The implementation plan decided to allow optional 's'
    # Implementation should handle: r'\bkeyword(?:s)?\b'
    keywords = ["naruto", "sasuke", "one piece"]
    
    assert _contains_any("look at those narutos", keywords) is True
    assert _contains_any("lots of sasukes", keywords) is True
    assert _contains_any("broken one piece", keywords) is True

def test_contains_any_00_edge_case():
    """Test specific edge case for '00' vs '12:00'."""
    keywords = ["pv"]
    
    # Should NOT match time formats
    assert _contains_any("it is 12:00 now", keywords) is False
    assert _contains_any("03:00 pm", keywords) is False
    
    # Should MATCH standalone pv
    assert _contains_any("new anime pv is great", keywords) is True
    assert _contains_any("official pv", keywords) is True

def test_contains_any_char_edge_case():
    """Test 'char' vs 'charge'."""
    keywords = ["luffy"]
    
    assert _contains_any("luffy is here", keywords) is True
    assert _contains_any("fluffy cat", keywords) is False
    assert _contains_any("luffy's adventure", keywords) is True

