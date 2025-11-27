from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.database.operations import DatabaseOperations
from app.utils.health_monitor import health_monitor
from app.utils.recovery_manager import recovery_manager
from app.utils.logger import external_logger
from app.bot.keyboards import back_button
import asyncio

router = Router()
db = DatabaseOperations()

@router.callback_query(F.data.startswith("health_"))
async def health_dashboard(callback: CallbackQuery, state: FSMContext):
    """Health monitoring dashboard"""
    action = callback.data.split("_", 1)[1]
    
    if action == "dashboard":
        await show_health_dashboard(callback)
    elif action == "refresh":
        await refresh_health_status(callback)
    elif action == "force_check":
        await force_health_check(callback)
    elif action == "recovery":
        await trigger_recovery(callback)

async def show_health_dashboard(callback: CallbackQuery):
    """Show comprehensive health dashboard"""
    try:
        await callback.answer("Loading health dashboard...")
        
        # Get health summary
        summary = await health_monitor.get_health_summary()
        
        # Build dashboard message
        message_parts = [
            "🏥 **SYSTEM HEALTH DASHBOARD**\\n",
            f"📊 **Total Accounts:** {summary.get('total_accounts', 0)}\\n",
            f"✅ **Healthy:** {summary.get('healthy', 0)}",
            f"⚠️ **Warning:** {summary.get('warning', 0)}", 
            f"🚨 **Critical:** {summary.get('critical', 0)}",
            f"🔴 **Inactive:** {summary.get('inactive', 0)}\\n"
        ]
        
        # Add account details
        details = summary.get('details', [])
        if details:
            message_parts.append("**📋 Account Details:**\\n")
            
            for account in details[:10]:  # Show first 10 accounts
                account_id = account['account_id']
                phone = account['phone']
                health = account['health']
                issues = account.get('issues', [])
                
                # Health emoji
                health_emoji = {
                    'healthy': '✅',
                    'warning': '⚠️', 
                    'critical': '🚨'
                }.get(health, '❓')
                
                message_parts.append(f"{health_emoji} **{phone}** (ID: {account_id})")
                
                if issues:
                    issues_text = ', '.join(issues[:3])  # Show first 3 issues
                    if len(issues) > 3:
                        issues_text += f" +{len(issues)-3} more"
                    message_parts.append(f"   └️ Issues: {issues_text}")
            
            if len(details) > 10:
                message_parts.append(f"\\n... and {len(details)-10} more accounts")
        
        # Add recovery status
        message_parts.extend([
            "\\n**🔧 Recovery System:**",
            f"🤖 Auto-Recovery: {'Active' if recovery_manager.recovery_running else 'Inactive'}",
            f"🔄 Last Check: N/A"  # Could be enhanced with timestamp
        ])
        
        # Add actions
        message_parts.extend([
            "\\n**🎯 Actions:**",
            "📊 Refresh Status",
            "🔍 Force Health Check", 
            "🛠️ Trigger Recovery"
        ])
        
        # Create inline keyboard
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Refresh", callback_data="health_refresh"),
                InlineKeyboardButton(text="🔍 Force Check", callback_data="health_force_check")
            ],
            [
                InlineKeyboardButton(text="🛠️ Trigger Recovery", callback_data="health_recovery"),
                InlineKeyboardButton(text="🔙 Back", callback_data="back_to_accounts")
            ]
        ])
        
        await callback.message.edit_text(
            text="\\n".join(message_parts),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Error loading health dashboard: {str(e)}",
            reply_markup=back_button("accounts")
        )

async def refresh_health_status(callback: CallbackQuery):
    """Refresh health status"""
    try:
        await callback.answer("Refreshing health status...")
        
        # Force health check
        await health_monitor.force_health_check()
        
        # Show updated dashboard
        await show_health_dashboard(callback)
        
    except Exception as e:
        await callback.answer(f"Error refreshing: {str(e)}", show_alert=True)

async def force_health_check(callback: CallbackQuery):
    """Force immediate health check on all accounts"""
    try:
        await callback.answer("Performing health check...")
        
        # Show loading message
        loading_msg = await callback.message.edit_text(
            "🔍 Performing comprehensive health check...\\n⏳ This may take a moment..."
        )
        
        # Force health check
        results = await health_monitor.force_health_check()
        
        # Count results
        healthy_count = sum(1 for r in results.values() if r['health'] == 'healthy')
        warning_count = sum(1 for r in results.values() if r['health'] == 'warning') 
        critical_count = sum(1 for r in results.values() if r['health'] == 'critical')
        
        # Update message with results
        await loading_msg.edit_text(
            f"✅ Health check completed!\\n"
            f"📊 Results: {healthy_count} healthy, {warning_count} warnings, {critical_count} critical\\n"
            f"🔄 Updating dashboard..."
        )
        
        # Wait a moment then show dashboard
        await asyncio.sleep(2)
        await show_health_dashboard(callback)
        
    except Exception as e:
        await callback.answer(f"Error during health check: {str(e)}", show_alert=True)

async def trigger_recovery(callback: CallbackQuery):
    """Trigger manual recovery process"""
    try:
        await callback.answer("Triggering recovery...")
        
        # Show loading message
        loading_msg = await callback.message.edit_text(
            "🛠️ Triggering recovery process...\\n"
            "🔍 Checking for frozen tasks and issues..."
        )
        
        # Force recovery check
        results = await recovery_manager.force_recovery_check()
        
        # Count issues found
        total_accounts = len(results)
        issues_found = sum(1 for r in results.values() if r['health'] != 'healthy')
        
        await loading_msg.edit_text(
            f"✅ Recovery check completed!\\n"
            f"📊 Checked {total_accounts} accounts\\n"
            f"🔧 Issues found: {issues_found}\\n"
            f"🔄 Updating dashboard..."
        )
        
        # Wait then show updated dashboard
        await asyncio.sleep(2)
        await show_health_dashboard(callback)
        
    except Exception as e:
        await callback.answer(f"Error during recovery: {str(e)}", show_alert=True)

# Register router
def register_health_handlers(dp):
    """Register health monitoring handlers"""
    dp.include_router(router)
