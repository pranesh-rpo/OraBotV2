import asyncio
from datetime import datetime, time
from typing import Optional
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError
from app.database.operations import DatabaseOperations
from app.client.session_manager import session_manager
from app.utils.anti_spam import anti_spam
from app.utils.logger import external_logger
from config import Config

class BroadcastWorker:
    def __init__(self):
        self.db = DatabaseOperations()
        self.running_tasks = {}
    
    async def start_broadcast(self, account_id: int):
        """Start broadcasting for an account"""
        if account_id in self.running_tasks:
            return False, "Broadcast already running"
        
        # Get account details
        account = await self.db.get_account(account_id)
        if not account:
            return False, "Account not found"
        
        # Get message
        message = await self.db.get_account_message(account_id)
        if not message:
            return False, "Please set a message first"
        
        # Load client
        try:
            client = await session_manager.load_client(
                account['session_string'], 
                account_id
            )
        except Exception as e:
            return False, f"Failed to load account: {str(e)}"
        
        # Get groups
        groups = await self.db.get_account_groups(account_id)
        if not groups:
            # Fetch and save groups
            try:
                fetched_groups = await session_manager.get_dialogs(client)
                await self.db.save_groups(account_id, fetched_groups)
                groups = await self.db.get_account_groups(account_id)
            except Exception as e:
                return False, f"Failed to fetch groups: {str(e)}"
        
        if not groups:
            return False, "No groups found"
        
        # Update status
        await self.db.update_account_broadcast_status(account_id, True)
        
        # Start broadcast task
        task = asyncio.create_task(
            self._broadcast_loop(account_id, account, client, message, groups)
        )
        self.running_tasks[account_id] = task
        
        await external_logger.send_log(
            account['user_id'],
            account['phone_number'],
            f"Broadcast started for {len(groups)} groups",
            "success"
        )
        
        return True, f"Broadcast started for {len(groups)} groups"
    
    async def stop_broadcast(self, account_id: int):
        """Stop broadcasting for an account"""
        if account_id not in self.running_tasks:
            return False, "Broadcast not running"
        
        # Cancel task
        self.running_tasks[account_id].cancel()
        del self.running_tasks[account_id]
        
        # Update status
        await self.db.update_account_broadcast_status(account_id, False)
        
        account = await self.db.get_account(account_id)
        await external_logger.send_log(
            account['user_id'],
            account['phone_number'],
            "Broadcast stopped",
            "info"
        )
        
        return True, "Broadcast stopped"
    
    async def _broadcast_loop(self, account_id: int, account: dict, 
                             client, message: str, groups: list):
        """Main broadcast loop"""
        try:
            # Get schedule
            schedule = await self.db.get_schedule(account_id)
            
            group_index = 0
            
            while True:
                # Check if within schedule time
                if schedule:
                    current_time = datetime.now().time()
                    start_time = datetime.strptime(schedule['start_time'], "%H:%M").time()
                    end_time = datetime.strptime(schedule['end_time'], "%H:%M").time()
                    
                    if not (start_time <= current_time <= end_time):
                        # Outside schedule, wait
                        await asyncio.sleep(60)
                        continue
                
                # Get next group
                if group_index >= len(groups):
                    group_index = 0
                    await self.db.add_log(
                        account_id,
                        "broadcast",
                        "Completed one full cycle, restarting",
                        "info"
                    )
                    await anti_spam.batch_delay()
                
                group = groups[group_index]
                
                # Try to send message
                try:
                    await anti_spam.safe_send(
                        client,
                        group['group_id'],
                        message,
                        account_id
                    )
                    
                    await self.db.update_group_last_message(account_id, group['group_id'])
                    await self.db.add_log(
                        account_id,
                        "broadcast",
                        f"Message sent to: {group['group_title']}",
                        "success"
                    )
                    
                    await external_logger.send_log(
                        account['user_id'],
                        account['phone_number'],
                        f"✅ Sent to: {group['group_title']}",
                        "broadcast"
                    )
                    
                except FloodWaitError as e:
                    wait_time = int(str(e).split('A wait of ')[1].split(' seconds')[0])
                    await self.db.add_log(
                        account_id,
                        "error",
                        f"FloodWait: {wait_time}s for {group['group_title']}",
                        "warning"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
                    await self.db.add_log(
                        account_id,
                        "error",
                        f"Cannot send to: {group['group_title']} - Banned/No permission",
                        "error"
                    )
                
                except Exception as e:
                    await self.db.add_log(
                        account_id,
                        "error",
                        f"Error sending to {group['group_title']}: {str(e)}",
                        "error"
                    )
                
                # Move to next group
                group_index += 1
                
                # Calculate next send time
                interval = schedule['min_interval'] if schedule else Config.MIN_INTERVAL
                max_interval = schedule['max_interval'] if schedule else Config.MAX_INTERVAL
                delay = anti_spam.calculate_next_send_time(interval, max_interval)
                
                await asyncio.sleep(delay)
        
        except asyncio.CancelledError:
            await self.db.add_log(
                account_id,
                "broadcast",
                "Broadcast stopped by user",
                "info"
            )
        except Exception as e:
            await self.db.add_log(
                account_id,
                "error",
                f"Broadcast loop error: {str(e)}",
                "error"
            )
            await self.db.update_account_broadcast_status(account_id, False)

# Global instance
broadcast_worker = BroadcastWorker()