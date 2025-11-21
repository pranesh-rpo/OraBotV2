import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import Config

class DatabaseOperations:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
    
    # USER OPERATIONS
    async def add_user(self, user_id: int, username: str = None, first_name: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name)
            )
            await db.commit()
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def verify_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (user_id,))
            await db.commit()
    
    # ACCOUNT OPERATIONS
    async def add_account(self, user_id: int, phone: str, session_string: str, first_name: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            
            # Check if account with this phone number exists (even if soft-deleted)
            # If it exists, delete it first to avoid unique constraint violation
            async with db.execute(
                "SELECT id FROM accounts WHERE phone_number = ?", (phone,)
            ) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    existing_id = existing[0]
                    # Delete the old account and all related data in the same transaction
                    await db.execute("DELETE FROM groups WHERE account_id = ?", (existing_id,))
                    await db.execute("DELETE FROM logs WHERE account_id = ?", (existing_id,))
                    await db.execute("DELETE FROM schedules WHERE account_id = ?", (existing_id,))
                    await db.execute("DELETE FROM messages WHERE account_id = ?", (existing_id,))
                    await db.execute("DELETE FROM accounts WHERE id = ?", (existing_id,))
            
            # Now insert the new account
            cursor = await db.execute(
                """INSERT INTO accounts (user_id, phone_number, session_string, first_name) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, phone, session_string, first_name)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_user_accounts(self, user_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM accounts WHERE user_id = ? AND is_active = 1", 
                (user_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_account(self, account_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def update_account_broadcast_status(self, account_id: int, status: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE accounts SET is_broadcasting = ? WHERE id = ?",
                (1 if status else 0, account_id)
            )
            await db.commit()
    
    async def set_manual_interval(self, account_id: int, interval_minutes: int):
        """Set manual interval for account (must be > 7 minutes)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE accounts SET manual_interval = ? WHERE id = ?",
                (interval_minutes, account_id)
            )
            await db.commit()
    
    async def get_manual_interval(self, account_id: int) -> Optional[int]:
        """Get manual interval for account"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT manual_interval FROM accounts WHERE id = ?",
                (account_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else None
    
    async def delete_account(self, account_id: int):
        """Permanently delete account and all related data"""
        async with aiosqlite.connect(self.db_path) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            
            # Delete related data first (to avoid foreign key issues)
            # Delete groups
            await db.execute("DELETE FROM groups WHERE account_id = ?", (account_id,))
            
            # Delete logs
            await db.execute("DELETE FROM logs WHERE account_id = ?", (account_id,))
            
            # Delete schedules
            await db.execute("DELETE FROM schedules WHERE account_id = ?", (account_id,))
            
            # Delete messages
            await db.execute("DELETE FROM messages WHERE account_id = ?", (account_id,))
            
            # Finally, delete the account itself
            await db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            
            await db.commit()
    
    # MESSAGE OPERATIONS
    async def set_account_message(self, account_id: int, message_text: str):
        async with aiosqlite.connect(self.db_path) as db:
            # Deactivate old messages
            await db.execute(
                "UPDATE messages SET is_active = 0 WHERE account_id = ?",
                (account_id,)
            )
            # Insert new message
            await db.execute(
                "INSERT INTO messages (account_id, message_text) VALUES (?, ?)",
                (account_id, message_text)
            )
            await db.commit()
    
    async def get_account_message(self, account_id: int) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT message_text FROM messages WHERE account_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
                (account_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    
    # SCHEDULE OPERATIONS
    async def set_schedule(self, account_id: int, start_time: str, end_time: str, 
                          min_interval: int = 5, max_interval: int = 15):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM schedules WHERE account_id = ?", (account_id,)
            )
            await db.execute(
                """INSERT INTO schedules (account_id, start_time, end_time, min_interval, max_interval)
                   VALUES (?, ?, ?, ?, ?)""",
                (account_id, start_time, end_time, min_interval, max_interval)
            )
            await db.commit()
    
    async def get_schedule(self, account_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM schedules WHERE account_id = ? AND is_active = 1",
                (account_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    # LOG OPERATIONS
    async def add_log(self, account_id: int, log_type: str, message: str, status: str = "info"):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (account_id, log_type, message, status) VALUES (?, ?, ?, ?)",
                (account_id, log_type, message, status)
            )
            await db.commit()
    
    async def get_account_logs(self, account_id: int, limit: int = 50) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM logs WHERE account_id = ? ORDER BY timestamp DESC LIMIT ?",
                (account_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    # GROUP OPERATIONS
    async def save_groups(self, account_id: int, groups: List[Dict]):
        async with aiosqlite.connect(self.db_path) as db:
            for group in groups:
                await db.execute(
                    """INSERT OR REPLACE INTO groups (account_id, group_id, group_title, is_active)
                       VALUES (?, ?, ?, 1)""",
                    (account_id, group['id'], group.get('title', 'Unknown'))
                )
            await db.commit()
    
    async def get_account_groups(self, account_id: int) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM groups WHERE account_id = ? AND is_active = 1",
                (account_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def update_group_last_message(self, account_id: int, group_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE groups SET last_message_sent = CURRENT_TIMESTAMP WHERE account_id = ? AND group_id = ?",
                (account_id, group_id)
            )
            await db.commit()