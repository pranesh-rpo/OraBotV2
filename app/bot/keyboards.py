from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict


def _chunk_buttons(buttons: List[InlineKeyboardButton], per_row: int = 2) -> List[List[InlineKeyboardButton]]:
    """Arrange buttons in rows with a fixed count per row."""
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main dashboard keyboard"""
    buttons = [
        InlineKeyboardButton(text="🔗 Link New Account", callback_data="link_account"),
        InlineKeyboardButton(text="📱 Manage Accounts", callback_data="manage_accounts"),
        InlineKeyboardButton(text="ℹ️ About Us", callback_data="about"),
        InlineKeyboardButton(text="💬 Support", url="https://t.me/HelpmeOrabot"),
        InlineKeyboardButton(text="🔒 Privacy Policy", callback_data="privacy"),
    ]
    rows = _chunk_buttons(buttons, per_row=2)
    return InlineKeyboardMarkup(inline_keyboard=rows)

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
    
    action_buttons = [
        start_stop_btn,
        InlineKeyboardButton(text="💬 Set Message", callback_data=f"set_message_{account_id}"),
        InlineKeyboardButton(text="⏱️ Set Interval", callback_data=f"set_interval_{account_id}"),
        InlineKeyboardButton(text="🕐 Set Schedule", callback_data=f"set_schedule_{account_id}"),
        InlineKeyboardButton(text="➕ Join Groups", callback_data=f"join_groups_{account_id}"),
        InlineKeyboardButton(text="📊 View Logs", callback_data=f"view_logs_{account_id}"),
        InlineKeyboardButton(text="🗑️ Delete Account", callback_data=f"delete_confirm_{account_id}")
    ]
    rows = _chunk_buttons(action_buttons, per_row=2)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="manage_accounts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def delete_confirmation_keyboard(account_id: int) -> InlineKeyboardMarkup:
    """Confirmation keyboard for account deletion"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"delete_account_{account_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"account_{account_id}")
        ]
    ])

def otp_keypad() -> InlineKeyboardMarkup:
    """Create a numeric keypad for OTP input"""
    buttons = []
    
    # Number pad layout (1-9, 0)
    for i in range(1, 10, 3):
        row = []
        for j in range(3):
            if i + j <= 9:
                row.append(InlineKeyboardButton(
                    text=str(i + j), 
                    callback_data=f"otp_{i + j}"
                ))
        buttons.append(row)
    
    # Last row with 0 and action buttons
    buttons.append([
        InlineKeyboardButton(text="0", callback_data="otp_0"),
        InlineKeyboardButton(text="⌫", callback_data="otp_backspace"),
        InlineKeyboardButton(text="✅", callback_data="otp_submit")
    ])
    
    # Clear and cancel buttons
    buttons.append([
        InlineKeyboardButton(text="🧹 Clear", callback_data="otp_clear"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="otp_cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def schedule_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting schedule type"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Normal Schedule", callback_data="schedule_type_normal"),
            InlineKeyboardButton(text="⭐ Special Schedule", callback_data="schedule_type_special")
        ]
    ])

def back_button(destination: str) -> InlineKeyboardMarkup:
    """Simple back button"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data=destination)]
        ]
    )

def join_groups_method_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing join groups method"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Send Links Manually", callback_data="join_method_manual"),
                InlineKeyboardButton(text="📄 Upload Text File", callback_data="join_method_file")
            ],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="manage_accounts")]
        ]
    )

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