from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.database.operations import DatabaseOperations
from app.client.session_manager import session_manager
from app.client.broadcast_worker import broadcast_worker
from app.utils.encryption import encryption
from app.bot.keyboards import (
    accounts_list_keyboard, account_dashboard_keyboard,
    delete_confirmation_keyboard, cancel_keyboard, back_button
)
from app.bot.menus import (
    account_info_message, link_account_start, logs_message
)

router = Router()
db = DatabaseOperations()

# FSM States
class LinkAccount(StatesGroup):
    phone = State()
    code = State()
    password = State()

class SetMessage(StatesGroup):
    message = State()

class SetInterval(StatesGroup):
    interval = State()

class SetSchedule(StatesGroup):
    start_time = State()
    end_time = State()

# MANAGE ACCOUNTS
@router.callback_query(F.data == "manage_accounts")
async def callback_manage_accounts(callback: CallbackQuery):
    """Show list of linked accounts"""
    accounts = await db.get_user_accounts(callback.from_user.id)
    
    if not accounts:
        await callback.message.edit_text(
            "📱 <b>No Accounts Linked</b>\n\n"
            "You haven't linked any accounts yet.\n"
            "Use <b>Link New Account</b> to add one.",
            reply_markup=back_button("main_menu"),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"📱 <b>Your Accounts ({len(accounts)})</b>\n\n"
            "Select an account to manage:",
            reply_markup=accounts_list_keyboard(accounts),
            parse_mode="HTML"
        )
    await callback.answer()

# LINK NEW ACCOUNT
@router.callback_query(F.data == "link_account")
async def callback_link_account(callback: CallbackQuery, state: FSMContext):
    """Start account linking process"""
    await callback.message.edit_text(
        link_account_start(),
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(LinkAccount.phone)
    await callback.answer()

@router.message(LinkAccount.phone)
async def process_phone(message: Message, state: FSMContext):
    """Process phone number"""
    phone = message.text.strip()
    
    # Validate phone format
    if not phone.startswith('+') or not phone[1:].isdigit():
        await message.answer(
            "❌ Invalid format!\n\n"
            "Please use format: +1234567890",
            reply_markup=cancel_keyboard()
        )
        return
    
    try:
        # Create client and send code
        client = await session_manager.create_client(phone)
        phone_code_hash = await session_manager.send_code(client, phone)
        
        # Store in FSM
        await state.update_data(
            phone=phone,
            client=client,
            phone_code_hash=phone_code_hash
        )
        
        await message.answer(
            "✅ <b>Code Sent!</b>\n\n"
            "Please enter the OTP code you received from Telegram:",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(LinkAccount.code)
        
    except Exception as e:
        await message.answer(
            f"❌ Error: {str(e)}\n\n"
            "Please try again with /start",
            reply_markup=back_button("main_menu")
        )
        await state.clear()

@router.message(LinkAccount.code)
async def process_code(message: Message, state: FSMContext):
    """Process OTP code"""
    code = message.text.strip().replace('-', '').replace(' ', '')
    data = await state.get_data()
    
    try:
        # Try to sign in
        session_string, first_name, user_id = await session_manager.sign_in(
            data['client'],
            data['phone'],
            code,
            data['phone_code_hash']
        )
        
        # Encrypt and save
        encrypted_session = encryption.encrypt(session_string)
        account_id = await db.add_account(
            message.from_user.id,
            data['phone'],
            encrypted_session,
            first_name
        )
        
        # Fetch and save groups
        groups = await session_manager.get_dialogs(data['client'])
        await db.save_groups(account_id, groups)
        
        await data['client'].disconnect()
        
        await message.answer(
            f"✅ <b>Account Linked Successfully!</b>\n\n"
            f"📱 Phone: <code>{data['phone']}</code>\n"
            f"👤 Name: {first_name}\n"
            f"📊 Groups Found: {len(groups)}\n\n"
            f"Your account is ready to broadcast!",
            reply_markup=back_button("manage_accounts"),
            parse_mode="HTML"
        )
        await state.clear()
        
    except Exception as e:
        error_msg = str(e)
        
        if "2FA_REQUIRED" in error_msg:
            await message.answer(
                "🔐 <b>2FA Detected</b>\n\n"
                "Please enter your 2FA password:",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(LinkAccount.password)
        else:
            await message.answer(
                f"❌ Error: {error_msg}\n\n"
                "Please try again with /start",
                reply_markup=back_button("main_menu")
            )
            await state.clear()

@router.message(LinkAccount.password)
async def process_password(message: Message, state: FSMContext):
    """Process 2FA password"""
    password = message.text.strip()
    data = await state.get_data()
    
    # Delete password message for security
    try:
        await message.delete()
    except:
        pass
    
    try:
        # Try to sign in with password
        session_string, first_name, user_id = await session_manager.sign_in(
            data['client'],
            data['phone'],
            data.get('last_code', ''),
            data['phone_code_hash'],
            password
        )
        
        # Encrypt and save
        encrypted_session = encryption.encrypt(session_string)
        account_id = await db.add_account(
            message.from_user.id,
            data['phone'],
            encrypted_session,
            first_name
        )
        
        # Fetch and save groups
        groups = await session_manager.get_dialogs(data['client'])
        await db.save_groups(account_id, groups)
        
        await data['client'].disconnect()
        
        await message.answer(
            f"✅ <b>Account Linked Successfully!</b>\n\n"
            f"📱 Phone: <code>{data['phone']}</code>\n"
            f"👤 Name: {first_name}\n"
            f"📊 Groups Found: {len(groups)}\n\n"
            f"Your account is ready to broadcast!",
            reply_markup=back_button("manage_accounts"),
            parse_mode="HTML"
        )
        await state.clear()
        
    except Exception as e:
        await message.answer(
            f"❌ Error: {str(e)}\n\n"
            "Please try again with /start",
            reply_markup=back_button("main_menu")
        )
        await state.clear()

# ACCOUNT DASHBOARD
@router.callback_query(F.data.startswith("account_"))
async def callback_account_dashboard(callback: CallbackQuery):
    """Show account dashboard"""
    account_id = int(callback.data.split("_")[1])
    account = await db.get_account(account_id)
    
    if not account or account['user_id'] != callback.from_user.id:
        await callback.answer("Account not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        account_info_message(account),
        reply_markup=account_dashboard_keyboard(account_id, account['is_broadcasting']),
        parse_mode="HTML"
    )
    await callback.answer()

# TOGGLE BROADCAST
@router.callback_query(F.data.startswith("toggle_broadcast_"))
async def callback_toggle_broadcast(callback: CallbackQuery):
    """Start or stop broadcast"""
    account_id = int(callback.data.split("_")[2])
    account = await db.get_account(account_id)
    
    if not account or account['user_id'] != callback.from_user.id:
        await callback.answer("Account not found", show_alert=True)
        return
    
    if account['is_broadcasting']:
        success, msg = await broadcast_worker.stop_broadcast(account_id)
    else:
        success, msg = await broadcast_worker.start_broadcast(account_id)
    
    await callback.answer(msg, show_alert=True)
    
    # Refresh dashboard
    account = await db.get_account(account_id)
    await callback.message.edit_text(
        account_info_message(account),
        reply_markup=account_dashboard_keyboard(account_id, account['is_broadcasting']),
        parse_mode="HTML"
    )

# SET MESSAGE
@router.callback_query(F.data.startswith("set_message_"))
async def callback_set_message(callback: CallbackQuery, state: FSMContext):
    """Start set message process"""
    account_id = int(callback.data.split("_")[2])
    
    current_msg = await db.get_account_message(account_id)
    msg_text = f"<b>Current Message:</b>\n{current_msg}\n\n" if current_msg else ""
    
    await callback.message.edit_text(
        f"💬 <b>Set Broadcast Message</b>\n\n"
        f"{msg_text}"
        f"Send me the new message you want to broadcast:\n\n"
        f"<i>You can use formatting, emojis, etc.</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.update_data(account_id=account_id)
    await state.set_state(SetMessage.message)
    await callback.answer()

@router.message(SetMessage.message)
async def process_set_message(message: Message, state: FSMContext):
    """Save broadcast message"""
    data = await state.get_data()
    account_id = data['account_id']
    
    await db.set_account_message(account_id, message.text)
    await db.add_log(account_id, "settings", "Message updated", "success")
    
    await message.answer(
        "✅ Message saved successfully!",
        reply_markup=back_button(f"account_{account_id}")
    )
    await state.clear()

# VIEW LOGS
@router.callback_query(F.data.startswith("view_logs_"))
async def callback_view_logs(callback: CallbackQuery):
    """Show account logs"""
    account_id = int(callback.data.split("_")[2])
    logs = await db.get_account_logs(account_id)
    
    await callback.message.edit_text(
        logs_message(logs),
        reply_markup=back_button(f"account_{account_id}"),
        parse_mode="HTML"
    )
    await callback.answer()

# DELETE ACCOUNT
@router.callback_query(F.data.startswith("delete_confirm_"))
async def callback_delete_confirm(callback: CallbackQuery):
    """Confirm account deletion"""
    account_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_text(
        "⚠️ <b>Delete Account?</b>\n\n"
        "Are you sure you want to delete this account?\n"
        "This action cannot be undone.",
        reply_markup=delete_confirmation_keyboard(account_id),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("delete_account_"))
async def callback_delete_account(callback: CallbackQuery):
    """Delete account"""
    account_id = int(callback.data.split("_")[2])
    
    # Stop broadcast if running
    await broadcast_worker.stop_broadcast(account_id)
    
    # Delete account
    await db.delete_account(account_id)
    
    await callback.message.edit_text(
        "✅ Account deleted successfully!",
        reply_markup=back_button("manage_accounts")
    )
    await callback.answer()