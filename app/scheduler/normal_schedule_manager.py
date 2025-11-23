import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import aiosqlite

from app.database.operations import DatabaseOperations
from app.client.broadcast_worker import broadcast_worker
from app.bot.menus import account_info_message
from app.bot.keyboards import account_dashboard_keyboard


class NormalScheduleTaskManager:
    """Task manager for normal schedules (time-based windows)"""
    def __init__(self, bot=None):
        self.db = DatabaseOperations()
        self.task = None
        self.ist = timezone(timedelta(hours=5, minutes=30))
        self.bot = bot

    async def start(self):
        if self.task and not self.task.done():
            return
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def _fetch_accounts_with_normal_schedules(self) -> List[Dict]:
        async with aiosqlite.connect(self.db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT a.id AS account_id, a.user_id, a.is_broadcasting, a.manual_override,
                       s.start_time, s.end_time, s.min_interval, s.max_interval
                FROM accounts a
                JOIN schedules s ON s.account_id = a.id
                WHERE a.is_active = 1 AND s.is_active = 1 AND s.schedule_type = 'normal'
                """
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    def _is_within_schedule(self, start_time_str: str, end_time_str: str, current_time: datetime) -> bool:
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        current = current_time.time()
        if start_time > end_time:
            return current >= start_time or current <= end_time
        return start_time <= current <= end_time

    async def _notify_user(self, user_id: int, account_id: int, message: str):
        """Send notification to user about schedule changes"""
        if not self.bot:
            return  # No bot instance available
        
        try:
            account = await self.db.get_account(account_id)
            if not account:
                return
            
            # Send notification as a new message instead of editing
            await self.bot.send_message(
                user_id,
                message,
                reply_markup=account_dashboard_keyboard(account_id, False),  # False because we just stopped it
                parse_mode="HTML"
            )
        except Exception as e:
            # If notification fails, at least log it
            await self.db.add_log(account_id, "notification", f"Failed to send notification: {str(e)}", "error")

    async def _run_loop(self):
        try:
            while True:
                try:
                    accounts = await self._fetch_accounts_with_normal_schedules()
                    now = datetime.now(tz=self.ist)
                    for acc in accounts:
                        account_id = acc["account_id"]
                        within = self._is_within_schedule(acc["start_time"], acc["end_time"], now)
                        is_running = bool(acc["is_broadcasting"])
                        manual_override = bool(acc.get("manual_override", 0))

                        if within and not is_running and not manual_override:
                            # Only auto-start if not manually overridden
                            msg = await self.db.get_account_message(account_id)
                            if not msg:
                                await self.db.add_log(account_id, "broadcast", "No message set for normal schedule auto-start", "error")
                                continue
                            ok, info = await broadcast_worker.start_broadcast(account_id)
                            status = "success" if ok else "error"
                            await self.db.add_log(account_id, "broadcast", f"Normal schedule auto-start: {info}", status)

                        if not within and is_running and not manual_override:
                            # Only auto-stop if not manually overridden
                            ok, info = await broadcast_worker.stop_broadcast(account_id)
                            status = "success" if ok else "error"
                            await self.db.add_log(account_id, "broadcast", f"Normal schedule auto-stop: {info}", status)
                            
                            # Notify user about auto-stop
                            await self._notify_user(
                                acc["user_id"],
                                account_id,
                                f"⏰ <b>Schedule Auto-Stop</b>\n\n"
                                f"Broadcast automatically stopped as schedule window ended.\n"
                                f"Time: {now.strftime('%H:%M')} IST\n\n"
                                f"Your account is now inactive. Start manually or wait for next schedule window."
                            )
                except Exception as e:
                    pass
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            return


normal_schedule_task_manager = NormalScheduleTaskManager()
