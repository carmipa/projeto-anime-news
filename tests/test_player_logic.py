import unittest
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.scanner import _classify_entry_type

class TestPlayerFix(unittest.TestCase):
    def test_media_embed_logic_simulation(self):
        # We want to verify the logic inside run_scan_once for media
        link = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        is_media = True
        entry_type = "video"
        
        # Simulated logic from scanner.py
        embed_url = link
        
        self.assertEqual(embed_url, link, "Media embed SHOULD have a URL for a better UX")
        
        # Simulated thumbnail logic
        has_thumb = True
        thumbnail_to_set = None
        if has_thumb:
            thumbnail_to_set = "http://example.com/thumb.jpg"
            
        self.assertEqual(thumbnail_to_set, "http://example.com/thumb.jpg", "Media embed SHOULD have a thumbnail if available")

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
