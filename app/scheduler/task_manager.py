import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import aiosqlite

from app.database.operations import DatabaseOperations
from app.client.broadcast_worker import broadcast_worker


class ScheduleTaskManager:
    def __init__(self):
        self.db = DatabaseOperations()
        self.task = None
        self.ist = timezone(timedelta(hours=5, minutes=30))

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

    async def _fetch_accounts_with_schedules(self) -> List[Dict]:
        async with aiosqlite.connect(self.db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT a.id AS account_id, a.user_id, a.is_broadcasting,
                       s.start_time, s.end_time, s.min_interval, s.max_interval
                FROM accounts a
                JOIN schedules s ON s.account_id = a.id
                WHERE a.is_active = 1 AND s.is_active = 1
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

    async def _run_loop(self):
        try:
            while True:
                try:
                    accounts = await self._fetch_accounts_with_schedules()
                    now = datetime.now(tz=self.ist)
                    for acc in accounts:
                        account_id = acc["account_id"]
                        within = self._is_within_schedule(acc["start_time"], acc["end_time"], now)
                        is_running = bool(acc["is_broadcasting"])

                        if within and not is_running:
                            msg = await self.db.get_account_message(account_id)
                            if not msg:
                                await self.db.add_log(account_id, "broadcast", "No message set for auto-start", "error")
                                continue
                            ok, info = await broadcast_worker.start_broadcast(account_id)
                            status = "success" if ok else "error"
                            await self.db.add_log(account_id, "broadcast", f"Auto-start: {info}", status)

                        if not within and is_running:
                            ok, info = await broadcast_worker.stop_broadcast(account_id)
                            status = "success" if ok else "error"
                            await self.db.add_log(account_id, "broadcast", f"Auto-stop: {info}", status)
                except Exception as e:
                    pass
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            return


schedule_task_manager = ScheduleTaskManager()