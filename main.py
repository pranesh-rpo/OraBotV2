import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import Config
from app.database.models import Database
from app.bot import handlers_start, handlers_account
from app.client.session_manager import session_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    """Actions on bot startup"""
    logger.info("🚀 Ora Ads Bot Starting...")
    
    # Validate config
    try:
        Config.validate()
        logger.info("✅ Configuration validated")
    except Exception as e:
        logger.error(f"❌ Configuration error: {e}")
        raise
    
    # Initialize database
    try:
        db = Database()
        await db.init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        raise
    
    # Set bot commands
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 Start the bot"),
    ])
    
    logger.info("✅ Bot commands set")
    logger.info(f"✅ Bot started: @{Config.BOT_USERNAME}")

async def on_shutdown():
    """Actions on bot shutdown"""
    logger.info("⏸️  Shutting down...")
    
    # Disconnect all Telegram clients
    await session_manager.disconnect_all()
    
    logger.info("✅ Shutdown complete")

async def main():
    """Main function"""
    try:
        # Initialize bot and dispatcher
        bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
        dp = Dispatcher(storage=MemoryStorage())
        
        # Register routers
        dp.include_router(handlers_start.router)
        dp.include_router(handlers_account.router)
        
        # Startup actions
        await on_startup(bot)
        
        # Start polling
        logger.info("🎯 Bot is polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        
    except KeyboardInterrupt:
        logger.info("⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")