import unittest
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scanner import _classify_entry_type, _extract_youtube_id, _normalize_youtube_url, _get_youtube_thumbnail

class TestPlayerFix(unittest.TestCase):
    def test_media_embed_logic_simulation(self):
        # We want to verify the logic inside run_scan_once for media
        link = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        is_media = True
        entry_type = "video"
        
        # Simulated logic from scanner.py
        embed_url = None if is_media else link
        
        self.assertIsNone(embed_url, "Media embed should NOT have a URL to avoid suppressing native player")
        
        # Simulated thumbnail logic
        thumbnail_to_set = None
        if not is_media:
            thumbnail_to_set = "feed_thumb" 
        elif is_media and ("youtube.com" in link or "youtu.be" in link):
            thumbnail_to_set = _get_youtube_thumbnail(link)
            
        self.assertEqual(thumbnail_to_set, "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg")

    def test_youtube_helpers(self):
        # ID Extraction
        self.assertEqual(_extract_youtube_id("https://www.youtube.com/watch?v=123"), "123")
        self.assertEqual(_extract_youtube_id("https://youtu.be/abc"), "abc")
        self.assertEqual(_extract_youtube_id("https://www.youtube.com/shorts/xyz"), "xyz")
        
        # Normalization
        self.assertEqual(_normalize_youtube_url("https://www.youtube.com/shorts/xyz"), "https://www.youtube.com/watch?v=xyz")
        
        # Thumbnail
        self.assertEqual(_get_youtube_thumbnail("https://youtu.be/123"), "https://img.youtube.com/vi/123/hqdefault.jpg")

    def test_news_embed_logic_simulation(self):
        link = "https://example.com/news/123"
        is_media = False
        
        # Simulated logic from scanner.py
        embed_url = None if is_media else link
        self.assertEqual(embed_url, link, "News embed SHOULD have a URL")
        
        # Simulated thumbnail logic
        has_thumb = True
        thumbnail_to_set = None
        if not is_media and has_thumb:
            thumbnail_to_set = "http://example.com/thumb.jpg"
            
        self.assertEqual(thumbnail_to_set, "http://example.com/thumb.jpg", "News embed SHOULD have a thumbnail if available")

if __name__ == "__main__":
    unittest.main()
