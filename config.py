import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class Config:
    # Bot Configuration
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "OraAdbot")
    APP_VERSION = os.getenv("APP_VERSION", "v0.1.1")
    
    # Telegram API
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    
    # Database
    DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/ora_ads.db")
    
    # Verification
    VERIFICATION_CHANNEL = os.getenv("VERIFICATION_CHANNEL")
    VERIFICATION_CHANNEL_ID = os.getenv("VERIFICATION_CHANNEL_ID")
    
    # Logger Bot
    LOGGER_BOT_TOKEN = os.getenv("LOGGER_BOT_TOKEN")
    
    # Security
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    
    # Admin
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    
    # Sessions Directory
    SESSIONS_DIR = Path("./sessions")
    
    # Broadcast Settings
    MIN_INTERVAL = 5  # minutes
    MAX_INTERVAL = 15  # minutes
    MESSAGES_PER_HOUR = 5
    
    @classmethod
    def validate(cls):
        """Validate all required configurations"""
        required = [
            "BOT_TOKEN", "API_ID", "API_HASH", 
            "VERIFICATION_CHANNEL_ID", "ENCRYPTION_KEY"
        ]
        missing = [key for key in required if not getattr(cls, key, None)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")
        
        # Convert string values to proper types
        try:
            cls.API_ID = int(cls.API_ID)
        except (ValueError, TypeError):
            raise ValueError("API_ID must be a valid integer")
        
        try:
            cls.VERIFICATION_CHANNEL_ID = int(cls.VERIFICATION_CHANNEL_ID)
        except (ValueError, TypeError):
            raise ValueError("VERIFICATION_CHANNEL_ID must be a valid integer")
        
        try:
            cls.ENCRYPTION_KEY = cls.ENCRYPTION_KEY.encode() if cls.ENCRYPTION_KEY else None
        except Exception:
            raise ValueError("ENCRYPTION_KEY must be a valid string")
        
        # Create directories
        cls.SESSIONS_DIR.mkdir(exist_ok=True)
        Path(cls.DATABASE_PATH).parent.mkdir(exist_ok=True)
        
        return True