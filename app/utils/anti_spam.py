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
        
        # Ensure minimum time between messages (reduced for faster operation)
        if account_id in self.last_message_time:
            elapsed = (datetime.now() - self.last_message_time[account_id]).total_seconds()
            if elapsed < 10:  # Minimum 10 seconds between messages
                await asyncio.sleep(10 - elapsed)
        
        # Add random micro-delay (1-3 seconds)
        await asyncio.sleep(random.uniform(1, 3))
        
        try:
            # Send message - entity can be ID (int), username (str), or entity object
            # Telethon's send_message handles all these types
            result = await client.send_message(entity, message)
            self.last_message_time[account_id] = datetime.now()
            return result
        except ValueError as e:
            # Entity resolution error - re-raise with more context
            error_msg = str(e)
            if "Could not find" in error_msg or "No user has" in error_msg:
                raise Exception(f"Group/Channel not found: {error_msg}")
            raise
        except TypeError as e:
            # Invalid entity type
            raise Exception(f"Invalid entity type for sending: {type(entity)} - {str(e)}")
        except FloodWaitError as e:
            # Store flood wait time
            error_str = str(e)
            if 'A wait of' in error_str:
                try:
                    wait_seconds = int(error_str.split('A wait of ')[1].split(' seconds')[0])
                    self.flood_wait_until[account_id] = datetime.now() + timedelta(seconds=wait_seconds)
                except:
                    # Fallback: wait 60 seconds
                    self.flood_wait_until[account_id] = datetime.now() + timedelta(seconds=60)
            raise
    
    def calculate_next_send_time(self, min_interval: int, max_interval: int) -> int:
        """Calculate next message time in seconds
        Args:
            min_interval: Minimum interval in minutes
            max_interval: Maximum interval in minutes
        Returns:
            Delay in seconds
        """
        # Random interval between min and max (in minutes)
        base_interval_minutes = random.randint(min_interval, max_interval)
        
        # Add random jitter (±20%)
        jitter = random.uniform(0.8, 1.2)
        
        # Convert to seconds
        delay_seconds = int(base_interval_minutes * 60 * jitter)
        
        # Ensure minimum delay of 30 seconds
        return max(30, delay_seconds)
    
    async def batch_delay(self, batch_size: int = 5):
        """Add delay after sending batch of messages"""
        delay = random.randint(30, 90)  # 30-90 seconds between batches
        await asyncio.sleep(delay)

# Global instance
anti_spam = AntiSpam()