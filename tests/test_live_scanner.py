
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import scanner
# Mock discord module before importing scanner if necessary, but we already imported it.
# We will mock the bot instance passed to run_scan_once.

async def mock_channel_send(*args, **kwargs):
    content = kwargs.get('content', '')
    embed = kwargs.get('embed')
    view = kwargs.get('view')
    
    print("\n[MOCK SEND] ------------------------------------------------")
    if content:
        print(f"CONTENT: {content}")
    if embed:
        print(f"EMBED TITLE: {embed.title}")
        print(f"EMBED DESC:  {embed.description}")
        print(f"EMBED URL:   {embed.url}")
        if embed.author:
             print(f"EMBED AUTHOR: {embed.author.name}")
        if embed.footer:
             print(f"EMBED FOOTER: {embed.footer.text}")
    print("------------------------------------------------------------\n")

async def run_live_test():
    print("🚀 Starting LIVE scanner integration test...")
    print("This will fetch REAL data from sources.json but MOCK the Discord sending.")
    
    # 1. Mock Bot
    mock_bot = MagicMock()
    mock_bot.user.avatar.url = "http://mock.url/avatar.png"
    
    # 2. Mock Channel
    mock_channel = AsyncMock()
    mock_channel.send = mock_channel_send
    
    # 3. Mock get_channel to return our mock channel
    # We need to know what channel IDs are in config.json. 
    # If config is empty, we might need to mock load_json_safe to return a dummy config.
    mock_bot.get_channel.return_value = mock_channel
    
    # Mocking storage to ensure we have a valid config for testing if the real one is empty
    # But let's try to run with real logic first. 
    # If run_scan_once reads config.json, we hope it has something.
    # If not, we will monkeypatch scanner.load_json_safe.
    
    original_load = scanner.load_json_safe
    
    def mocked_load_json(path, default):
        if "config.json" in path:
            # Return a dummy config with a dummy guild and channel
            print(f"📦 [TEST] Injecting mock configuration for {path}")
            return {
                "123456789": {
                    "channel_id": 999999,
                    "language": "pt_BR", # Force PT-BR to check translations
                    "filters": ["todos"] # Allow everything that isn't blacklisted
                }
            }
        return original_load(path, default)
    
    # Apply monkeypatch
    scanner.load_json_safe = mocked_load_json
    
    # Run the scan
    try:
        await scanner.run_scan_once(mock_bot, trigger="TEST_LIVE")
        print("\n✅ Live test execution completed without errors.")
    except Exception as e:
        print(f"\n❌ Live test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_live_test())
