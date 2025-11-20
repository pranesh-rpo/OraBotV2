import aiohttp
from datetime import datetime
from config import Config
from typing import Optional

class ExternalLogger:
    def __init__(self):
        self.token = Config.LOGGER_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
    
    async def send_log(self, user_id: int, account_phone: str, message: str, log_type: str = "info"):
        """Send log to external logger bot"""
        if not self.token:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        emoji = {
            "info": "ℹ️",
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "broadcast": "📢"
        }.get(log_type, "📝")
        
        log_message = f"""
{emoji} <b>{log_type.upper()}</b>

👤 User: <code>{user_id}</code>
📱 Account: <code>{account_phone}</code>
📝 Message: {message}
🕐 Time: {timestamp}
"""
        
        try:
            async with aiohttp.ClientSession() as session:
                # Send to admin users
                for admin_id in Config.ADMIN_IDS:
                    await session.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": admin_id,
                            "text": log_message,
                            "parse_mode": "HTML"
                        }
                    )
        except Exception as e:
            print(f"Failed to send log: {e}")

# Global instance
external_logger = ExternalLogger()