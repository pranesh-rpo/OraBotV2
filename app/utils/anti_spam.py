import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict
from telethon.errors import FloodWaitError

class AntiSpam:
    def __init__(self):
        self.last_message_time: Dict[int, datetime] = {}
        self.flood_wait_until: Dict[int, datetime] = {}
    
    def get_random_delay(self, min_minutes: int = 5, max_minutes: int = 15) -> int:
        """Get random delay in seconds"""
        return random.randint(min_minutes * 60, max_minutes * 60)
    
    async def safe_send(self, client, entity, message: str, account_id: int):
        """Send message with anti-spam protection"""
        # Check if in flood wait
        if account_id in self.flood_wait_until:
            if datetime.now() < self.flood_wait_until[account_id]:
                wait_time = (self.flood_wait_until[account_id] - datetime.now()).seconds
                raise FloodWaitError(f"Still in flood wait for {wait_time}s")
            else:
                del self.flood_wait_until[account_id]
        
        # Ensure minimum time between messages
        if account_id in self.last_message_time:
            elapsed = (datetime.now() - self.last_message_time[account_id]).seconds
            if elapsed < 60:  # Minimum 1 minute between messages
                await asyncio.sleep(60 - elapsed)
        
        # Add random micro-delay (1-5 seconds)
        await asyncio.sleep(random.uniform(1, 5))
        
        try:
            await client.send_message(entity, message)
            self.last_message_time[account_id] = datetime.now()
            return True
        except FloodWaitError as e:
            # Store flood wait time
            wait_seconds = int(str(e).split('A wait of ')[1].split(' seconds')[0])
            self.flood_wait_until[account_id] = datetime.now() + timedelta(seconds=wait_seconds)
            raise
    
    def calculate_next_send_time(self, min_interval: int, max_interval: int) -> int:
        """Calculate next message time ensuring ~5 messages per hour"""
        # Random interval between min and max
        base_interval = random.randint(min_interval, max_interval)
        
        # Add random jitter (±20%)
        jitter = random.uniform(0.8, 1.2)
        
        return int(base_interval * 60 * jitter)
    
    async def batch_delay(self, batch_size: int = 5):
        """Add delay after sending batch of messages"""
        delay = random.randint(30, 90)  # 30-90 seconds between batches
        await asyncio.sleep(delay)

# Global instance
anti_spam = AntiSpam()