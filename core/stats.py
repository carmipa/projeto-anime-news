from datetime import datetime, timedelta

class BotStats:
    def __init__(self):
        self.start_time = datetime.now()
        self.scans_completed = 0
        self.news_posted = 0
        self.cache_hits_total = 0
        self.last_scan_time = None
        self.errors_count = 0

    def format_uptime(self):
        delta = datetime.now() - self.start_time
        # Simplified formatting
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"

stats = BotStats()
