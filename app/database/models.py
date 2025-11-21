import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict
from config import Config

class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        
    async def init_db(self):
        """Initialize database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_verified BOOLEAN DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Accounts table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL UNIQUE,
                    session_string TEXT NOT NULL,
                    first_name TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    is_broadcasting BOOLEAN DEFAULT 0,
                    manual_interval INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Add manual_interval column if it doesn't exist (for existing databases)
            try:
                # Check if column exists by trying to query it
                async with db.execute("SELECT manual_interval FROM accounts LIMIT 1") as cursor:
                    await cursor.fetchone()
            except:
                # Column doesn't exist, add it
                try:
                    await db.execute("ALTER TABLE accounts ADD COLUMN manual_interval INTEGER DEFAULT NULL")
                    await db.commit()
                except Exception as e:
                    # Ignore if column already exists or other errors
                    pass
            
            # Messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(id)
                )
            """)
            
            # Schedules table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    min_interval INTEGER DEFAULT 5,
                    max_interval INTEGER DEFAULT 15,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (account_id) REFERENCES accounts(id)
                )
            """)
            
            # Logs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    log_type TEXT NOT NULL,
                    message TEXT,
                    status TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (account_id) REFERENCES accounts(id)
                )
            """)
            
            # Groups table (cache joined groups)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    group_title TEXT,
                    last_message_sent TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (account_id) REFERENCES accounts(id),
                    UNIQUE(account_id, group_id)
                )
            """)
            
            await db.commit()
    
    async def close(self):
        """Close database connection"""
        pass  # aiosqlite handles connections per context