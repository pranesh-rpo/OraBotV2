import asyncio
import logging
import os
import signal
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from config import Config
from app.database.models import Database
from app.bot import handlers_start, handlers_account
from app.scheduler import schedule_handlers
from app.scheduler.task_manager import schedule_task_manager
from app.scheduler.normal_schedule_manager import NormalScheduleTaskManager
from app.scheduler.special_schedule_manager import SpecialScheduleTaskManager
from app.client.session_manager import session_manager
from app.client.broadcast_worker import broadcast_worker
from app.utils.lock import lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
bot_instance = None
normal_schedule_task_manager = None
special_schedule_task_manager = None

async def on_startup(bot: Bot):
    """Actions on bot startup"""
    global normal_schedule_task_manager, special_schedule_task_manager
    
    logger.info("🚀 Ora Ads Bot v.0.1.2 Starting...")
    
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
    
    # Clean up any stale sessions and locks
    try:
        # Clean up old lock files
        import glob
        lock_patterns = ['/tmp/ora_ads*.lock', '/tmp/ora_ads_bot*.lock']
        for pattern in lock_patterns:
            for lock_file in glob.glob(pattern):
                try:
                    os.unlink(lock_file)
                    logger.info(f"🧹 Cleaned up old lock file: {lock_file}")
                except:
                    pass
    except Exception as e:
        logger.warning(f"⚠️  Could not clean up lock files: {e}")
    
    # Initialize schedule managers with bot instance
    normal_schedule_task_manager = NormalScheduleTaskManager(bot)
    special_schedule_task_manager = SpecialScheduleTaskManager(bot)
    logger.info("✅ Schedule managers initialized")
    
    # Set bot commands
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 Start the bot"),
    ])
    
    logger.info("✅ Bot commands set")
    logger.info(f"✅ Bot started: @{Config.BOT_USERNAME}")
    
    # Sync broadcast status on startup
    await broadcast_worker.sync_broadcast_status()
    logger.info("✅ Broadcast status synced")
    
    # Start all schedule managers
    await normal_schedule_task_manager.start()
    logger.info("✅ Normal schedule manager started")
    
    await special_schedule_task_manager.start()
    logger.info("✅ Special schedule manager started")

async def on_shutdown():
    """Actions on bot shutdown"""
    logger.info("⏸️  Shutting down...")
    
    # Disconnect all Telegram clients
    await session_manager.disconnect_all()
    
    # Stop all schedule managers if they exist
    if normal_schedule_task_manager:
        await normal_schedule_task_manager.stop()
    if special_schedule_task_manager:
        await special_schedule_task_manager.stop()
    
    # Release lock
    lock.release()
    
    logger.info("✅ Shutdown complete")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"⚠️  Received signal {signum}")
    sys.exit(0)

async def main():
    """Main function"""
    global bot_instance
    
    # Check for single instance
    if not lock.acquire():
        logger.error("❌ Another instance of Ora Ads is already running!")
        logger.error("❌ Please stop the other instance first.")
        logger.info("")
        logger.info("💡 Quick fix:")
        logger.info("   Linux/Mac: ./bot_manager.sh kill-all")
        logger.info("   Windows: bot_manager.bat -> Option 5")
        logger.info("")
        logger.info("💡 Manual fix:")
        logger.info("   ps aux | grep 'python.*main.py'")
        logger.info("   kill -9 <PID>")
        logger.info("   rm -f /tmp/ora_ads.lock")
        sys.exit(1)
    
    logger.info("✅ Lock acquired - Single instance confirmed")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize bot and dispatcher
        bot_instance = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher(storage=MemoryStorage())
        
        # Register routers
        dp.include_router(handlers_start.router)
        dp.include_router(handlers_account.router)
        dp.include_router(schedule_handlers.router)
        
        # Startup actions
        await on_startup(bot_instance)
        
        # Check for existing bot sessions and terminate them
        logger.info("🔍 Checking for conflicting bot sessions...")
        try:
            # Try to delete webhook (in case bot was running as webhook)
            await bot_instance.delete_webhook(drop_pending_updates=True)
            logger.info("✅ Webhook cleared")
        except Exception as e:
            logger.warning(f"⚠️  Could not clear webhook: {e}")
        
        # Short delay to ensure previous sessions are cleared
        await asyncio.sleep(2)
        
        # Start polling with optimized settings for low latency
        logger.info("🎯 Bot is polling...")
        await dp.start_polling(
            bot_instance, 
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,  # Drop pending updates on start
            handle_as_tasks=True,  # Handle updates concurrently
            polling_timeout=5  # Much faster timeout
        )
        
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