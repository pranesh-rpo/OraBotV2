import aiohttp
from datetime import datetime
from config import Config
from typing import Optional, List

class ExternalLogger:
    def __init__(self):
        self.token = Config.LOGGER_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
    
    def _build_log_message(
        self,
        user_id: int,
        account_phone: str,
        message: str,
        log_type: str = "info"
    ) -> str:
        """Build formatted log message text"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        emoji = {
            "info": "ℹ️",
            "success": "✅",
            "error": "❌",
            "warning": "⚠️",
            "broadcast": "📢"
        }.get(log_type, "📝")
        
        return f"""
{emoji} <b>{log_type.upper()}</b>

👤 User: <code>{user_id}</code>
📱 Account: <code>{account_phone}</code>
📝 Message: {message}
🕐 Time: {timestamp}
"""
    
    async def _send_to_targets(self, targets: List[int], text: str):
        """Low-level helper to send a message to multiple chat IDs"""
        if not self.token:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                # Deduplicate targets
                unique_targets = set(int(t) for t in targets if t)
                for chat_id in unique_targets:
                    await session.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": text,
                            "parse_mode": "HTML"
                        }
                    )
        except Exception as e:
            print(f"Failed to send log: {e}")
    
    async def send_log(
        self,
        user_id: int,
        account_phone: str,
        message: str,
        log_type: str = "info",
        send_to_user: bool = True,
        extra_receivers: Optional[List[int]] = None,
    ):
        """
        Send log to external logger bot.
        
        - Always sends to all ADMIN_IDS
        - Optionally also sends directly to the user who owns the account
        - Can include any extra receiver chat_ids if needed
        """
        log_message = self._build_log_message(user_id, account_phone, message, log_type)
        
        targets: List[int] = []
        
        # Admins always receive all logs
        targets.extend(Config.ADMIN_IDS or [])
        
        # Optionally send to the user who owns this account
        if send_to_user and user_id:
            targets.append(user_id)
        
        # Any extra receivers (e.g. support channel, monitoring bots)
        if extra_receivers:
            targets.extend(extra_receivers)
        
        await self._send_to_targets(targets, log_message)

# Global instance
external_logger = ExternalLogger()