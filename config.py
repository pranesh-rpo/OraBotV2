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
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    
    # Database
    DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/ora_ads.db")
    
    # Verification
    VERIFICATION_CHANNEL = os.getenv("VERIFICATION_CHANNEL")
    VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID"))
    
    # Logger Bot
    LOGGER_BOT_TOKEN = os.getenv("LOGGER_BOT_TOKEN")
    
    # Security
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY").encode()
    
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
        
        # Create directories
        cls.SESSIONS_DIR.mkdir(exist_ok=True)
        Path(cls.DATABASE_PATH).parent.mkdir(exist_ok=True)
        
        return True