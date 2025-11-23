import asyncio
import aiosqlite
import random
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError,
    ChatAdminRequiredError
)
from app.database.operations import DatabaseOperations
from app.client.session_manager import session_manager
from app.utils.anti_spam import anti_spam
from app.utils.logger import external_logger
from config import Config

class BroadcastWorker:
    def __init__(self):
        self.db = DatabaseOperations()
        self.running_tasks = {}
        self.ist = timezone(timedelta(hours=5, minutes=30))
    
    async def sync_broadcast_status(self):
        """Sync broadcast status on startup - clean up stale statuses"""
        try:
            accounts = await self.db.get_all_broadcasting_accounts()
            for account in accounts:
                account_id = account['id']
                # Reset stale broadcast status
                await self.db.update_account_broadcast_status(account_id, False)
                await self.db.add_log(
                    account_id,
                    "broadcast",
                    "Cleaned up stale broadcast status on startup",
                    "info"
                )
        except Exception as e:
            # Log error but don't fail startup
            print(f"Error syncing broadcast status: {e}")
    
    async def start_broadcast(self, account_id: int):
        """Start broadcasting for an account"""
        # Check if already running in memory
        if account_id in self.running_tasks:
            return False, "Broadcast already running"
        
        # Check database status and clean up if needed
        account = await self.db.get_account(account_id)
        if not account:
            return False, "Account not found"
        
        # If database shows broadcasting but no task is running, reset the status
        if account['is_broadcasting']:
            await self.db.update_account_broadcast_status(account_id, False)
            await self.db.add_log(
                account_id,
                "broadcast",
                "Cleaned up stale broadcast status",
                "info"
            )
        
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
        
        # Log start with details
        await self.db.add_log(
            account_id,
            "broadcast",
            f"Starting broadcast for {len(groups)} groups. Message length: {len(message)} chars",
            "info"
        )
        
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
        # Check if running in memory
        task_running = account_id in self.running_tasks
        
        if task_running:
            # Cancel task
            task = self.running_tasks.pop(account_id)
            task.cancel()
        else:
            # If no task but database shows broadcasting, just update database
            account = await self.db.get_account(account_id)
            if not account:
                return False, "Account not found"
            
            if not account['is_broadcasting']:
                return False, "Broadcast not running"
        
        # Always update database status and clear manual override for natural stops
        await self.db.update_account_broadcast_status(account_id, False)
        await self.db.set_manual_override(account_id, False)  # Clear manual override for natural stops
        
        account = await self.db.get_account(account_id)
        await external_logger.send_log(
            account['user_id'],
            account['phone_number'],
            "Broadcast stopped",
            "info"
        )
        
        return True, "Broadcast stopped"
    
    async def refresh_groups(self, account_id: int):
        """Refresh groups list from Telegram and update running broadcast"""
        try:
            account = await self.db.get_account(account_id)
            if not account:
                return False, "Account not found"
            
            # Get client (from active clients or load new)
            client = session_manager.get_client(account_id)
            if not client:
                # Try to load client
                try:
                    client = await session_manager.load_client(
                        account['session_string'],
                        account_id
                    )
                except Exception as e:
                    return False, f"Failed to load client: {str(e)}"
            
            # Ensure client is connected
            if not client.is_connected():
                try:
                    await client.connect()
                    if not await client.is_user_authorized():
                        return False, "Session expired"
                except Exception as e:
                    return False, f"Failed to connect: {str(e)}"
            
            # Fetch fresh groups
            fetched_groups = await session_manager.get_dialogs(client)
            
            if not fetched_groups:
                return False, "No groups found"
            
            # Save groups to database
            await self.db.save_groups(account_id, fetched_groups)
            
            # If broadcast is running, the loop will pick up the new groups on next sync
            # We don't need to manually update the running task's groups list
            # as it will be refreshed in the next sync cycle
            
            return True, f"Refreshed {len(fetched_groups)} groups"
        except Exception as e:
            return False, f"Error refreshing groups: {str(e)}"
    
    def _calculate_delay_for_5_per_hour(self) -> int:
        """Calculate random delay to achieve ~5 messages per hour"""
        # 5 messages per hour = 1 message every 12 minutes on average
        # Randomize between 8-16 minutes to keep it natural
        # This ensures we get approximately 5 messages per hour
        base_minutes = random.uniform(8, 16)
        return int(base_minutes * 60)  # Convert to seconds
    
    def _is_within_schedule(self, schedule: Optional[dict], current_time: datetime) -> bool:
        """Check if current time is within schedule"""
        if not schedule:
            return True
        
        start_time = datetime.strptime(schedule['start_time'], "%H:%M").time()
        end_time = datetime.strptime(schedule['end_time'], "%H:%M").time()
        current = current_time.time()
        
        # Handle schedule that spans midnight (e.g., 22:00 - 06:00)
        if start_time > end_time:
            # Schedule spans midnight
            return current >= start_time or current <= end_time
        else:
            # Normal schedule within same day
            return start_time <= current <= end_time
    
    async def _broadcast_loop(self, account_id: int, account: dict,
                             client, initial_message: str, groups: list):
        """Main broadcast loop - sends to all groups, then waits with smart timing"""
        message = initial_message
        schedule = None
        manual_interval = None
        try:
            # Get schedule, manual interval, and latest message
            schedule = await self.db.get_schedule(account_id)
            manual_interval = await self.db.get_manual_interval(account_id)
            message = await self.db.get_account_message(account_id) or message

            # Log broadcast start
            mode_text = ""
            if manual_interval:
                mode_text = f"Manual interval: {manual_interval} minutes"
            elif schedule:
                mode_text = f"Schedule: {schedule['start_time']} - {schedule['end_time']} (5 msg/hr)"
            else:
                mode_text = "Default mode: 5 messages/hour with random timing"
            
            await self.db.add_log(
                account_id,
                "broadcast",
                f"Broadcast loop started with {len(groups)} groups. Mode: {mode_text}",
                "info"
            )
            
            while True:
                # Refresh schedule, manual interval, and message each cycle
                schedule = await self.db.get_schedule(account_id)
                manual_interval = await self.db.get_manual_interval(account_id)
                latest_message = await self.db.get_account_message(account_id)
                if latest_message:
                    message = latest_message
                elif not message:
                    await self.db.add_log(
                        account_id,
                        "error",
                        "No message configured. Stopping broadcast.",
                        "error"
                    )
                    break

                # Check if within schedule time (only if schedule is set)
                current_time = datetime.now(tz=self.ist)
                if schedule and not self._is_within_schedule(schedule, current_time):
                    # Outside schedule, wait and check again
                    start_time = schedule['start_time']
                    end_time = schedule['end_time']
                    await self.db.add_log(
                        account_id,
                        "broadcast",
                        f"⏸️ Outside schedule ({start_time} - {end_time} IST), waiting...",
                        "info"
                    )
                    # Wait 1 minute and check again
                    await asyncio.sleep(60)
                    continue
                
                # Check if client is still connected
                if not client.is_connected():
                    await self.db.add_log(
                        account_id,
                        "error",
                        "Client disconnected, attempting to reconnect",
                        "error"
                    )
                    try:
                        await client.connect()
                        if not await client.is_user_authorized():
                            raise Exception("Session expired")
                    except Exception as e:
                        await self.db.add_log(
                            account_id,
                            "error",
                            f"Failed to reconnect: {str(e)}",
                            "error"
                        )
                        break  # Exit loop if can't reconnect
                
                # Safety check: ensure we have groups
                if not groups:
                    await self.db.add_log(
                        account_id,
                        "error",
                        "No groups available, stopping broadcast",
                        "error"
                    )
                    break
                
                # Refresh groups before each cycle
                try:
                    fetched_groups = await session_manager.get_dialogs(client)
                    await self.db.save_groups(account_id, fetched_groups)
                    new_groups = await self.db.get_account_groups(account_id)
                    if new_groups:
                        groups = new_groups
                except Exception as e:
                    await self.db.add_log(
                        account_id,
                        "error",
                        f"Failed to refresh groups: {str(e)}",
                        "error"
                    )
                
                # Log cycle start
                await self.db.add_log(
                    account_id,
                    "broadcast",
                    f"🚀 Starting broadcast cycle to {len(groups)} groups",
                    "info"
                )
                
                # Send to ALL groups sequentially (no delay between groups)
                successful_sends = 0
                failed_sends = 0
                
                for group_index, group in enumerate(groups):
                    # Try to send message
                    try:
                        # Get group_id (Telethon stores groups with negative IDs)
                        group_id = group['group_id']
                        group_title = group.get('group_title', 'Unknown')
                        
                        # Log attempt (less verbose for batch sending)
                        if group_index == 0 or (group_index + 1) % 5 == 0:
                            await self.db.add_log(
                                account_id,
                                "broadcast",
                                f"Sending to group {group_index + 1}/{len(groups)}: {group_title}",
                                "info"
                            )
                        
                        # Resolve entity from ID (more reliable than using raw ID)
                        entity = None
                        try:
                            # Try to get entity from ID
                            entity = await client.get_entity(group_id)
                        except Exception as entity_error:
                            error_str = str(entity_error)
                            # Try alternative: search in dialogs
                            try:
                                async for dialog in client.iter_dialogs():
                                    if dialog.id == group_id:
                                        entity = dialog.entity
                                        break
                            except:
                                pass
                            
                            # If still no entity, try using ID directly (ensure negative for groups)
                            if entity is None:
                                if group_id > 0:
                                    group_id = -abs(group_id)
                                entity = group_id
                                await self.db.add_log(
                                    account_id,
                                    "broadcast",
                                    f"Using ID directly (could not resolve entity): {error_str[:100]}",
                                    "warning"
                                )
                        
                        # Send message using resolved entity
                        await anti_spam.safe_send(
                            client,
                            entity,
                            message,
                            account_id
                        )
                        
                        await self.db.update_group_last_message(account_id, group['group_id'])
                        successful_sends += 1
                        
                        # Only log every 5th success to reduce log spam
                        if successful_sends % 5 == 0 or group_index == len(groups) - 1:
                            await self.db.add_log(
                                account_id,
                                "broadcast",
                                f"✅ Sent to {successful_sends} groups so far...",
                                "success"
                            )
                    
                    except FloodWaitError as e:
                        wait_time = getattr(e, "seconds", None)
                        if wait_time is None:
                            try:
                                wait_time = int(str(e).split('A wait of ')[1].split(' seconds')[0])
                            except Exception:
                                wait_time = Config.MIN_INTERVAL * 60
                        await self.db.add_log(
                            account_id,
                            "error",
                            f"FloodWait: {wait_time}s for {group_title}. Skipping this group.",
                            "warning"
                        )
                        failed_sends += 1
                        await asyncio.sleep(wait_time)
                        # Skip this group and continue to next
                        continue
                
                    except (ChatWriteForbiddenError, UserBannedInChannelError, ChatAdminRequiredError) as e:
                        # Mark group as inactive if we can't send
                        error_type = type(e).__name__
                        error_reason = "Banned/No permission"
                        if isinstance(e, ChatAdminRequiredError):
                            error_reason = "Admin privileges required"
                        elif isinstance(e, ChatWriteForbiddenError):
                            error_reason = "Write forbidden"
                        elif isinstance(e, UserBannedInChannelError):
                            error_reason = "User banned"
                        
                        try:
                            async with aiosqlite.connect(self.db.db_path) as db_conn:
                                await db_conn.execute(
                                    "UPDATE groups SET is_active = 0 WHERE account_id = ? AND group_id = ?",
                                    (account_id, group['group_id'])
                                )
                                await db_conn.commit()
                        except:
                            pass
                        
                        failed_sends += 1
                        # Continue to next group
                        continue
                    
                    except Exception as e:
                        error_msg = str(e)
                        error_type = type(e).__name__
                        
                        # Check for specific common errors
                        if "InputPeerInvalid" in error_msg or "CHAT_ID_INVALID" in error_msg:
                            # Mark group as inactive
                            try:
                                async with aiosqlite.connect(self.db.db_path) as db_conn:
                                    await db_conn.execute(
                                        "UPDATE groups SET is_active = 0 WHERE account_id = ? AND group_id = ?",
                                        (account_id, group['group_id'])
                                    )
                                    await db_conn.commit()
                            except:
                                pass
                        elif ("CHAT_WRITE_FORBIDDEN" in error_msg or "can't write" in error_msg.lower() or 
                              "ChatAdminRequiredError" in error_msg or "admin privileges" in error_msg.lower()):
                            # Mark as inactive
                            try:
                                async with aiosqlite.connect(self.db.db_path) as db_conn:
                                    await db_conn.execute(
                                        "UPDATE groups SET is_active = 0 WHERE account_id = ? AND group_id = ?",
                                        (account_id, group['group_id'])
                                    )
                                    await db_conn.commit()
                            except:
                                pass
                        
                        failed_sends += 1
                        # Continue to next group
                        continue
                
                # After sending to all groups, log summary and wait for interval
                await self.db.add_log(
                    account_id,
                    "broadcast",
                    f"✅ Cycle complete: {successful_sends} successful, {failed_sends} failed out of {len(groups)} groups",
                    "success"
                )
                
                # Calculate delay for next cycle
                # Priority: Manual interval > Schedule interval > Default (5 msg/hr)
                if manual_interval:
                    # Use manual interval (already validated to be >= 7 minutes)
                    delay = manual_interval * 60  # Convert minutes to seconds
                    delay_text = f"Manual interval: {manual_interval} minutes"
                elif schedule:
                    # Use schedule's interval settings if available, otherwise default to 5 msg/hr
                    min_interval = schedule.get('min_interval', Config.MIN_INTERVAL)
                    max_interval = schedule.get('max_interval', Config.MAX_INTERVAL)
                    delay = anti_spam.calculate_next_send_time(min_interval, max_interval)
                    delay_text = f"Schedule interval: {min_interval}-{max_interval} minutes"
                else:
                    # Default: 5 messages per hour with random timing
                    delay = self._calculate_delay_for_5_per_hour()
                    delay_text = "Default: ~5 messages/hour (random timing)"
                
                await self.db.add_log(
                    account_id,
                    "broadcast",
                    f"⏳ Waiting {delay}s ({delay/60:.1f} min) before next cycle ({delay_text})",
                    "info"
                )
                
                # Wait for the calculated delay, but check schedule periodically if set
                if schedule:
                    # If schedule is set, check every minute to respect schedule boundaries
                    waited = 0
                    while waited < delay:
                        sleep_time = min(60, delay - waited)  # Check every minute
                        await asyncio.sleep(sleep_time)
                        waited += sleep_time
                        
                        # Check if we're still within schedule
                        current_time = datetime.now(tz=self.ist)
                        if not self._is_within_schedule(schedule, current_time):
                            await self.db.add_log(
                                account_id,
                                "broadcast",
                                f"⏸️ Schedule end time reached, pausing broadcast",
                                "info"
                            )
                            # Wait until schedule starts again
                            while not self._is_within_schedule(schedule, datetime.now(tz=self.ist)):
                                await asyncio.sleep(60)
                            await self.db.add_log(
                                account_id,
                                "broadcast",
                                f"▶️ Schedule start time reached, resuming broadcast",
                                "info"
                            )
                            break  # Break out of wait loop to start new cycle
                else:
                    # No schedule, just wait the full delay
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
        finally:
            await self.db.update_account_broadcast_status(account_id, False)
            await self.db.set_manual_override(account_id, False)  # Clear manual override for natural completion
            self.running_tasks.pop(account_id, None)

# Global instance
broadcast_worker = BroadcastWorker()