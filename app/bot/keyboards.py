from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main dashboard keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Link New Account", callback_data="link_account")],
        [InlineKeyboardButton(text="📱 Manage Accounts", callback_data="manage_accounts")],
        [InlineKeyboardButton(text="ℹ️ About Us", callback_data="about")],
        [InlineKeyboardButton(text="💬 Support", url="https://t.me/OraAdbotSupport")],
        [InlineKeyboardButton(text="🔒 Privacy Policy", callback_data="privacy")]
    ])

def accounts_list_keyboard(accounts: List[Dict]) -> InlineKeyboardMarkup:
    """Keyboard showing list of accounts"""
    buttons = []
    for acc in accounts:
        status = "🟢" if acc['is_broadcasting'] else "🔴"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {acc['phone_number']}", 
                callback_data=f"account_{acc['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def account_dashboard_keyboard(account_id: int, is_broadcasting: bool) -> InlineKeyboardMarkup:
    """Individual account dashboard"""
    start_stop_btn = InlineKeyboardButton(
        text="⏸️ Stop Broadcast" if is_broadcasting else "▶️ Start Broadcast",
        callback_data=f"toggle_broadcast_{account_id}"
    )
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [start_stop_btn],
        [InlineKeyboardButton(text="💬 Set Message", callback_data=f"set_message_{account_id}")],
        [InlineKeyboardButton(text="⏱️ Set Interval", callback_data=f"set_interval_{account_id}")],
        [InlineKeyboardButton(text="🕐 Set Schedule", callback_data=f"set_schedule_{account_id}")],
        [InlineKeyboardButton(text="📊 View Logs", callback_data=f"view_logs_{account_id}")],
        [InlineKeyboardButton(text="🗑️ Delete Account", callback_data=f"delete_confirm_{account_id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="manage_accounts")]
    ])

def delete_confirmation_keyboard(account_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard for account deletion"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"delete_account_{account_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"account_{account_id}")
        ]
    ])

def back_button(callback_data: str = "main_menu") -> InlineKeyboardMarkup:
    """Simple back button"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Back", callback_data=callback_data)]
    ])

def verification_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    """Verification keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel", url=f"https://t.me/{channel_link.replace('@', '')}")],
        [InlineKeyboardButton(text="✅ I Joined", callback_data="check_verification")]
    ])

def cancel_keyboard() -> InlineKeyboardMarkup:
    """Cancel operation keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Cancel", callback_data="main_menu")]
    ])