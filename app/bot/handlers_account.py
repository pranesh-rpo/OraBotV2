from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    UserAlreadyParticipantError, InviteHashExpiredError, 
    InviteHashInvalidError, UsernameNotOccupiedError,
    ChannelPrivateError, FloodWaitError
)
from app.database.operations import DatabaseOperations
from app.client.session_manager import session_manager
from app.client.broadcast_worker import broadcast_worker
from app.utils.encryption import encryption
from app.bot.keyboards import (
    accounts_list_keyboard, account_dashboard_keyboard,
    delete_confirmation_keyboard, cancel_keyboard, back_button, otp_keypad,
    join_groups_method_keyboard
)
from app.bot.menus import (
    account_info_message, link_account_start, logs_message
)

router = Router()
db = DatabaseOperations()

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode=None):
    """Safely edit a message, avoiding 'message not modified' errors"""
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    except Exception as e:
        if "message is not modified" not in str(e):
            # Re-raise if it's not the "not modified" error
            raise

# FSM States
class LinkAccount(StatesGroup):
    phone = State()
    code = State()
    password = State()
    otp_code = State()  # New state for keypad OTP input

class SetMessage(StatesGroup):
    message = State()

class SetInterval(StatesGroup):
    interval = State()


class JoinGroups(StatesGroup):
    group_link = State()
    file_upload = State()

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
    if not phone.startswith('+'):
        await message.answer(
            "❌ <b>Invalid Format</b>\n\n"
            "Phone number must start with '+'\n"
            "Example: <code>+1234567890</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    if not phone[1:].replace(' ', '').replace('-', '').isdigit():
        await message.answer(
            "❌ <b>Invalid Format</b>\n\n"
            "Phone number must contain only digits after '+'\n"
            "Example: <code>+1234567890</code>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Remove spaces and dashes
    phone = phone.replace(' ', '').replace('-', '')
    
    # Show connecting message
    status_msg = await message.answer(
        "🔄 <b>Connecting to Telegram...</b>\n\n"
        "⏳ Please wait, this may take a moment...",
        parse_mode="HTML"
    )
    
    client = None
    try:
        # Create client
        await status_msg.edit_text(
            "🔌 <b>Establishing Connection...</b>\n\n"
            "⏳ Connecting to Telegram servers...",
            parse_mode="HTML"
        )
        client = await session_manager.create_client(phone)
        
        await status_msg.edit_text(
            "📱 <b>Sending Verification Code...</b>\n\n"
            "⏳ Requesting OTP from Telegram...\n"
            "This usually takes 5-10 seconds.",
            parse_mode="HTML"
        )
        
        # Send code with retry
        phone_code_hash = await session_manager.send_code(client, phone)
        
        # Store in FSM
        await state.update_data(
            phone=phone,
            client=client,
            phone_code_hash=phone_code_hash
        )
        
        await status_msg.edit_text(
            "✅ <b>Code Sent Successfully!</b>\n\n"
            "📨 Check your Telegram for the verification code.\n"
            "💬 Enter the code using the keypad below:\n\n"
            "<i>The code is usually 5 digits (e.g., 12345)</i>\n\n"
            "<b>Your code:</b> <code>_</code>",
            reply_markup=otp_keypad(),
            parse_mode="HTML"
        )
        await state.update_data(otp_code="")  # Initialize empty OTP code
        await state.set_state(LinkAccount.otp_code)
        
    except Exception as e:
        error_text = str(e)
        
        # Cleanup client on error
        if client:
            try:
                await client.disconnect()
            except:
                pass
        
        # User-friendly error messages
        if "wait" in error_text.lower() and "minute" in error_text.lower():
            await status_msg.edit_text(
                "⏰ <b>Rate Limited</b>\n\n"
                f"{error_text}\n\n"
                "📋 <b>What to do:</b>\n"
                "1. Wait the specified time\n"
                "2. Try again with /start\n"
                "3. Or use a different phone number\n\n"
                "<i>Telegram limits how often codes can be requested.</i>",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        elif "flood" in error_text.lower():
            await status_msg.edit_text(
                "🚫 <b>Too Many Attempts</b>\n\n"
                f"{error_text}\n\n"
                "📋 <b>Solutions:</b>\n"
                "• Wait 1-2 hours before trying again\n"
                "• Use this number in official Telegram app first\n"
                "• Try a different phone number\n\n"
                "<i>This is a Telegram security measure.</i>",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        elif "banned" in error_text.lower():
            await status_msg.edit_text(
                "🚫 <b>Phone Number Banned</b>\n\n"
                f"{error_text}\n\n"
                "📋 <b>This means:</b>\n"
                "• Telegram has banned this number\n"
                "• You need to contact Telegram support\n"
                "• Or use a different phone number\n\n"
                "<i>Bot cannot bypass Telegram bans.</i>",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        elif "invalid" in error_text.lower() and "format" in error_text.lower():
            await status_msg.edit_text(
                "❌ <b>Invalid Phone Format</b>\n\n"
                f"{error_text}\n\n"
                "📋 <b>Correct format:</b>\n"
                "• Start with + (plus sign)\n"
                "• Include country code\n"
                "• Example: <code>+1234567890</code>\n\n"
                "Try again with /start",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        elif "unavailable" in error_text.lower() or "timeout" in error_text.lower():
            await status_msg.edit_text(
                "⚠️ <b>Connection Issue</b>\n\n"
                f"{error_text}\n\n"
                "📋 <b>Please try:</b>\n"
                "1. Check your internet connection\n"
                "2. Wait 2-3 minutes\n"
                "3. Try again with /start\n\n"
                "<i>Telegram servers may be temporarily busy.</i>",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text(
                "❌ <b>Unable to Send Code</b>\n\n"
                f"{error_text}\n\n"
                "📋 <b>Suggestions:</b>\n"
                "• Wait 5-10 minutes\n"
                "• Check phone number format\n"
                "• Try again with /start\n"
                "• Contact support if issue persists",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        
        await state.clear()

# OTP KEYPAD HANDLERS
@router.callback_query(F.data.startswith("otp_"))
async def handle_otp_keypad(callback: CallbackQuery, state: FSMContext):
    """Handle OTP keypad button presses"""
    data = await state.get_data()
    current_code = data.get('otp_code', '')
    
    if callback.data == "otp_cancel":
        # Cancel OTP input
        await callback.message.edit_text(
            "❌ <b>Verification Cancelled</b>\n\n"
            "Please start again with /start",
            reply_markup=back_button("main_menu"),
            parse_mode="HTML"
        )
        await state.clear()
        await callback.answer()
        return
    
    elif callback.data == "otp_clear":
        # Clear the code
        current_code = ""
        await state.update_data(otp_code="")
        
    elif callback.data == "otp_backspace":
        # Remove last digit
        if current_code:
            current_code = current_code[:-1]
            await state.update_data(otp_code=current_code)
    
    elif callback.data == "otp_submit":
        # Submit the code
        if len(current_code) < 3:
            await callback.answer("⚠️ Code too short!", show_alert=True)
            return
        
        # Process the OTP code
        await process_otp_verification(callback, current_code, state)
        return
    
    else:
        # Number button pressed
        digit = callback.data.split("_")[1]
        if len(current_code) < 10:  # Limit code length
            current_code += digit
            await state.update_data(otp_code=current_code)
    
    # Update the display
    code_display = current_code if current_code else "_"
    masked_code = "●" * (len(current_code) - 1) + current_code[-1:] if current_code else "_"
    
    await callback.message.edit_text(
        "✅ <b>Code Sent Successfully!</b>\n\n"
        "📨 Check your Telegram for the verification code.\n"
        "💬 Enter the code using the keypad below:\n\n"
        "<i>The code is usually 5 digits (e.g., 12345)</i>\n\n"
        f"<b>Your code:</b> <code>{masked_code}</code>",
        reply_markup=otp_keypad(),
        parse_mode="HTML"
    )
    await callback.answer()

async def process_otp_verification(callback: CallbackQuery, code: str, state: FSMContext):
    """Process the OTP verification"""
    data = await state.get_data()
    
    if not data.get('client'):
        await callback.message.edit_text(
            "❌ <b>Session Expired</b>\n\n"
            "Please start again with /start",
            reply_markup=back_button("main_menu"),
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    # Show processing message
    await callback.message.edit_text(
        "🔄 <b>Verifying Code...</b>\n\n"
        "⏳ Authenticating with Telegram...",
        parse_mode="HTML"
    )
    
    client = data['client']
    
    try:
        # Ensure client is still connected
        if not client.is_connected():
            await callback.message.edit_text(
                "🔌 <b>Reconnecting...</b>\n\n"
                "⏳ Re-establishing connection...",
                parse_mode="HTML"
            )
            await client.connect()
        
        # Update status
        await callback.message.edit_text(
            "🔐 <b>Signing In...</b>\n\n"
            "⏳ Creating secure session...",
            parse_mode="HTML"
        )
        
        # Try to sign in
        session_string, first_name, user_id = await session_manager.sign_in(
            client,
            data['phone'],
            code,
            data['phone_code_hash']
        )
        
        # Update status
        await callback.message.edit_text(
            "📊 <b>Fetching Your Groups...</b>\n\n"
            "⏳ This may take a moment...",
            parse_mode="HTML"
        )
        
        # Encrypt and save
        encrypted_session = encryption.encrypt(session_string)
        account_id = await db.add_account(
            callback.from_user.id,
            data['phone'],
            encrypted_session,
            first_name
        )
        
        # Fetch and save groups
        groups = await session_manager.get_dialogs(client)
        await db.save_groups(account_id, groups)
        
        # Disconnect client
        await client.disconnect()
        
        await callback.message.edit_text(
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
            # Store code for 2FA step
            await state.update_data(last_code=code, otp_code="")
            
            await callback.message.edit_text(
                "🔐 <b>Two-Factor Authentication Required</b>\n\n"
                "Your account has 2FA enabled.\n"
                "Please enter your 2FA password:\n\n"
                "<i>Your password will be deleted immediately after use.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(LinkAccount.password)
            
        elif "PHONE_CODE_INVALID" in error_msg or "Invalid verification code" in error_msg:
            await callback.message.edit_text(
                "❌ <b>Invalid Code</b>\n\n"
                "The verification code you entered is incorrect.\n\n"
                "📋 <b>Tips:</b>\n"
                "• Check for typos\n"
                "• Code is usually 5 digits\n"
                "• Don't include spaces or dashes\n\n"
                "Please try again with /start to get a new code.",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
            
        elif "PHONE_CODE_EXPIRED" in error_msg or "confirmation code has expired" in error_msg:
            await callback.message.edit_text(
                "⏰ <b>Code Expired</b>\n\n"
                "The verification code has expired.\n"
                "Codes are valid for 2-3 minutes only.\n\n"
                "Please try again with /start to get a new code.",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
            
        elif "CONNECTION_LOST" in error_msg or "disconnected" in error_msg.lower():
            await callback.message.edit_text(
                "🔌 <b>Connection Lost</b>\n\n"
                "Lost connection to Telegram during authentication.\n\n"
                "📋 <b>Please try:</b>\n"
                "1. Check your internet connection\n"
                "2. Wait 1-2 minutes\n"
                "3. Try again with /start\n\n"
                "<i>This can happen due to network issues.</i>",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
            
        else:
            await callback.message.edit_text(
                f"❌ <b>Authentication Error</b>\n\n"
                f"{error_msg}\n\n"
                "📋 <b>Suggestions:</b>\n"
                "• Try again with /start\n"
                "• Check your internet connection\n"
                "• Contact support if issue persists",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
async def process_code(message: Message, state: FSMContext):
    """Process OTP code"""
    code = message.text.strip().replace('-', '').replace(' ', '')
    data = await state.get_data()
    
    if not data.get('client'):
        await message.answer(
            "❌ <b>Session Expired</b>\n\n"
            "Please start again with /start",
            reply_markup=back_button("main_menu"),
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    # Show processing message
    status_msg = await message.answer(
        "🔄 <b>Verifying Code...</b>\n\n"
        "⏳ Authenticating with Telegram...",
        parse_mode="HTML"
    )
    
    client = data['client']
    
    try:
        # Ensure client is still connected
        if not client.is_connected():
            await status_msg.edit_text(
                "🔌 <b>Reconnecting...</b>\n\n"
                "⏳ Re-establishing connection...",
                parse_mode="HTML"
            )
            await client.connect()
        
        # Update status
        await status_msg.edit_text(
            "🔐 <b>Signing In...</b>\n\n"
            "⏳ Creating secure session...",
            parse_mode="HTML"
        )
        
        # Try to sign in
        session_string, first_name, user_id = await session_manager.sign_in(
            client,
            data['phone'],
            code,
            data['phone_code_hash']
        )
        
        # Update status
        await status_msg.edit_text(
            "📊 <b>Fetching Your Groups...</b>\n\n"
            "⏳ This may take a moment...",
            parse_mode="HTML"
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
        groups = await session_manager.get_dialogs(client)
        await db.save_groups(account_id, groups)
        
        # Disconnect client
        await client.disconnect()
        
        await status_msg.edit_text(
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
            # Store code for 2FA step
            await state.update_data(last_code=code)
            
            await status_msg.edit_text(
                "🔐 <b>Two-Factor Authentication Required</b>\n\n"
                "Your account has 2FA enabled.\n"
                "Please enter your 2FA password:\n\n"
                "<i>Your password will be deleted immediately after use.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(LinkAccount.password)
            
        elif "PHONE_CODE_INVALID" in error_msg:
            await status_msg.edit_text(
                "❌ <b>Invalid Code</b>\n\n"
                "The verification code you entered is incorrect.\n\n"
                "📋 <b>Tips:</b>\n"
                "• Check for typos\n"
                "• Code is usually 5 digits\n"
                "• Don't include spaces or dashes\n\n"
                "Please try again with /start to get a new code.",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
            
        elif "PHONE_CODE_EXPIRED" in error_msg:
            await status_msg.edit_text(
                "⏰ <b>Code Expired</b>\n\n"
                "The verification code has expired.\n"
                "Codes are valid for 2-3 minutes only.\n\n"
                "Please try again with /start to get a new code.",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
            
        elif "CONNECTION_LOST" in error_msg or "disconnected" in error_msg.lower():
            await status_msg.edit_text(
                "🔌 <b>Connection Lost</b>\n\n"
                "Lost connection to Telegram during authentication.\n\n"
                "📋 <b>Please try:</b>\n"
                "1. Check your internet connection\n"
                "2. Wait 1-2 minutes\n"
                "3. Try again with /start\n\n"
                "<i>This can happen due to network issues.</i>",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass
            
        else:
            await status_msg.edit_text(
                f"❌ <b>Authentication Error</b>\n\n"
                f"{error_msg}\n\n"
                "📋 <b>Suggestions:</b>\n"
                "• Try again with /start\n"
                "• Check your internet connection\n"
                "• Contact support if issue persists",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
            await state.clear()
            try:
                await client.disconnect()
            except:
                pass

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
    
    # Show processing message
    status_msg = await message.answer(
        "🔐 <b>Verifying 2FA password...</b>\n\n"
        "⏳ Authenticating...",
        parse_mode="HTML"
    )
    
    try:
        # Update status
        await status_msg.edit_text(
            "🔄 <b>Signing in...</b>\n\n"
            "⏳ Creating secure session...",
            parse_mode="HTML"
        )
        
        # Try to sign in with password
        session_string, first_name, user_id = await session_manager.sign_in(
            data['client'],
            data['phone'],
            data.get('last_code', ''),
            data['phone_code_hash'],
            password
        )
        
        # Update status
        await status_msg.edit_text(
            "📊 <b>Fetching your groups...</b>\n\n"
            "⏳ This may take a moment...",
            parse_mode="HTML"
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
        
        await status_msg.edit_text(
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
        
        if "PASSWORD_HASH_INVALID" in error_msg or "password" in error_msg.lower():
            await status_msg.edit_text(
                "❌ <b>Incorrect Password</b>\n\n"
                "The 2FA password you entered is incorrect.\n\n"
                "Please try again with /start",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        else:
            await status_msg.edit_text(
                f"❌ <b>Authentication Error</b>\n\n"
                f"{error_msg}\n\n"
                "Please try again with /start",
                reply_markup=back_button("main_menu"),
                parse_mode="HTML"
            )
        
        await state.clear()
        
        # Cleanup client
        try:
            await data['client'].disconnect()
        except:
            pass

# ACCOUNT DASHBOARD
@router.callback_query(F.data.startswith("account_"))
async def callback_account_dashboard(callback: CallbackQuery):
    """Show account dashboard"""
    account_id = int(callback.data.split("_")[1])
    account = await db.get_account(account_id)
    
    if not account or account['user_id'] != callback.from_user.id:
        await callback.answer("Account not found", show_alert=True)
        return
    
    await safe_edit_message(
        callback,
        await account_info_message(account, db),
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
        # User manually stopping broadcast - clear manual override
        success, msg = await broadcast_worker.stop_broadcast(account_id)
        await db.set_manual_override(account_id, False)  # Clear manual override
        await db.add_log(account_id, "broadcast", "Manual stop broadcast", "info")
    else:
        # User manually starting broadcast - set manual override
        success, msg = await broadcast_worker.start_broadcast(account_id)
        if success:
            await db.set_manual_override(account_id, True)  # Set manual override
            await db.add_log(account_id, "broadcast", "Manual start broadcast (schedule override)", "info")
    
    await callback.answer(msg, show_alert=True)
    
    # Refresh dashboard
    account = await db.get_account(account_id)
    await safe_edit_message(
        callback,
        await account_info_message(account, db),
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

# SET INTERVAL
@router.callback_query(F.data.startswith("set_interval_"))
async def callback_set_interval(callback: CallbackQuery, state: FSMContext):
    """Start set interval process"""
    account_id = int(callback.data.split("_")[2])
    
    current_interval = await db.get_manual_interval(account_id)
    interval_text = f"{current_interval} minutes" if current_interval else "Not set (using default)"
    
    await callback.message.edit_text(
        f"⏱️ <b>Set Manual Interval</b>\n\n"
        f"<b>Current Interval:</b> {interval_text}\n\n"
        f"Enter the interval in minutes between messages.\n"
        f"<b>⚠️ Minimum:</b> 7 minutes\n"
        f"<b>⚠️ Maximum:</b> 1440 minutes (24 hours)\n\n"
        f"<i>This will override the default random interval.</i>\n"
        f"<i>Send a number (e.g., 10 for 10 minutes)</i>",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.update_data(account_id=account_id)
    await state.set_state(SetInterval.interval)
    await callback.answer()

@router.message(SetInterval.interval)
async def process_set_interval(message: Message, state: FSMContext):
    """Save manual interval"""
    data = await state.get_data()
    account_id = data['account_id']
    
    try:
        interval = int(message.text.strip())
        
        if interval < 7:
            await message.answer(
                "❌ <b>Invalid Interval</b>\n\n"
                "Interval must be at least 7 minutes.\n"
                "Please enter a number >= 7:",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        if interval > 1440:
            await message.answer(
                "❌ <b>Invalid Interval</b>\n\n"
                "Interval cannot exceed 1440 minutes (24 hours).\n"
                "Please enter a number <= 1440:",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        await db.set_manual_interval(account_id, interval)
        await db.add_log(account_id, "settings", f"Manual interval set to {interval} minutes", "success")
        
        await message.answer(
            f"✅ <b>Interval Set Successfully!</b>\n\n"
            f"Manual interval: <b>{interval} minutes</b>\n\n"
            f"<i>This will be used for all broadcasts.</i>",
            reply_markup=back_button(f"account_{account_id}"),
            parse_mode="HTML"
        )
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Input</b>\n\n"
            "Please enter a valid number (e.g., 10 for 10 minutes).\n"
            "Minimum: 7 minutes",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )


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

# CANCEL HANDLER
@router.callback_query(F.data == "main_menu")
async def handle_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle cancel during FSM flows"""
    # Get FSM data to cleanup client if exists
    data = await state.get_data()
    
    # Cleanup any active client
    if 'client' in data:
        try:
            await data['client'].disconnect()
        except:
            pass
    
    # Clear state
    await state.clear()
    
    # Return to main menu
    from app.bot.handlers_start import callback_main_menu as main_menu_handler
    await main_menu_handler(callback, state)
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
    
    # Verify account belongs to user
    account = await db.get_account(account_id)
    if not account or account['user_id'] != callback.from_user.id:
        await callback.answer("Account not found", show_alert=True)
        return
    
    # Stop broadcast if running
    await broadcast_worker.stop_broadcast(account_id)
    
    # Disconnect client if active
    try:
        await session_manager.disconnect_client(account_id)
    except:
        pass  # Ignore if client not connected
    
    # Delete account and all related data
    try:
        await db.delete_account(account_id)
        await callback.message.edit_text(
            "✅ Account deleted successfully!",
            reply_markup=back_button("manage_accounts")
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ <b>Error deleting account</b>\n\n"
            f"{str(e)}\n\n"
            f"Please try again or contact support.",
            reply_markup=back_button("manage_accounts"),
            parse_mode="HTML"
        )
    
    await callback.answer()

# JOIN GROUPS
@router.callback_query(F.data.startswith("join_groups_"))
async def callback_join_groups(callback: CallbackQuery, state: FSMContext):
    """Start join groups process"""
    account_id = int(callback.data.split("_")[2])
    account = await db.get_account(account_id)
    
    if not account or account['user_id'] != callback.from_user.id:
        await callback.answer("Account not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        "➕ <b>Join Groups</b>\n\n"
        "Choose how you want to add groups:\n\n"
        "<b>Options:</b>\n"
        "• 📝 <b>Send links manually</b> - One by one\n"
        "• 📄 <b>Upload text file</b> - File with multiple links\n\n"
        "<b>File format:</b>\n"
        "• .txt file with group links\n"
        "• One link per line\n"
        "• Supports all link formats\n\n"
        "<i>Choose your preferred method below:</i>",
        reply_markup=join_groups_method_keyboard(),
        parse_mode="HTML"
    )
    await state.update_data(account_id=account_id)
    await callback.answer()

# JOIN GROUPS METHOD SELECTION
@router.callback_query(F.data.startswith("join_method_"))
async def callback_join_method(callback: CallbackQuery, state: FSMContext):
    """Handle join groups method selection"""
    method = callback.data.split("_")[2]
    
    if method == "manual":
        await callback.message.edit_text(
            "📝 <b>Send Group Links Manually</b>\n\n"
            "Send me group links or usernames to join:\n\n"
            "<b>Supported formats:</b>\n"
            "• <code>https://t.me/groupname</code>\n"
            "• <code>@groupname</code>\n"
            "• <code>t.me/groupname</code>\n"
            "• <code>https://t.me/joinchat/xxxxx</code>\n\n"
            "<i>You can send multiple links, one per message.</i>\n"
            "<i>Send /done when finished.</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(JoinGroups.group_link)
        
    elif method == "file":
        await callback.message.edit_text(
            "📄 <b>Upload Text File</b>\n\n"
            "Upload a .txt file containing group links:\n\n"
            "<b>File requirements:</b>\n"
            "• .txt format only\n"
            "• One group link per line\n"
            "• No empty lines\n"
            "• Max 1000 links per file\n\n"
            "<b>Supported link formats:</b>\n"
            "• <code>https://t.me/groupname</code>\n"
            "• <code>@groupname</code>\n"
            "• <code>t.me/groupname</code>\n"
            "• <code>https://t.me/joinchat/xxxxx</code>\n\n"
            "<i>The bot will join 5 groups every 5 minutes automatically.</i>\n"
            "<i>You'll get progress updates.</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(JoinGroups.file_upload)
    
    await callback.answer()

@router.message(JoinGroups.file_upload)
async def process_file_upload(message: Message, state: FSMContext):
    """Process uploaded file with group links"""
    if not message.document:
        await message.answer(
            "❌ <b>Please upload a text file</b>\n\n"
            "Make sure to upload a .txt file containing group links.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Check file type
    if not message.document.file_name.endswith('.txt'):
        await message.answer(
            "❌ <b>Invalid file format</b>\n\n"
            "Please upload a .txt file only.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Check file size (max 1MB)
    if message.document.file_size > 1024 * 1024:  # 1MB
        await message.answer(
            "❌ <b>File too large</b>\n\n"
            "Maximum file size is 1MB.\n"
            "Please split your file into smaller parts.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    try:
        # Download file
        file_info = await message.bot.get_file(message.document.file_id)
        file_content = await message.bot.download_file(file_info.file_path)
        
        # Decode and parse links
        if hasattr(file_content, 'read'):
            # It's a BytesIO object, read the bytes first
            content_bytes = file_content.read()
        else:
            # It's already bytes
            content_bytes = file_content
            
        content = content_bytes.decode('utf-8')
        links = [line.strip() for line in content.split('\n') if line.strip()]
        
        if not links:
            await message.answer(
                "❌ <b>No links found</b>\n\n"
                "The file appears to be empty or contains no valid links.",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        if len(links) > 1000:
            await message.answer(
                "❌ <b>Too many links</b>\n\n"
                f"Found {len(links)} links. Maximum allowed is 1000.\n"
                "Please split your file into smaller parts.",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        # Validate links format
        valid_links = []
        for link in links:
            if any(x in link.lower() for x in ['t.me/', '@', 'joinchat']):
                valid_links.append(link)
        
        if not valid_links:
            await message.answer(
                "❌ <b>No valid links found</b>\n\n"
                "No valid Telegram group links were found in the file.\n\n"
                "<b>Valid formats:</b>\n"
                "• https://t.me/groupname\n"
                "• @groupname\n"
                "• t.me/groupname\n"
                "• https://t.me/joinchat/xxxxx",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        # Get account info
        data = await state.get_data()
        account_id = data['account_id']
        account = await db.get_account(account_id)
        
        if not account:
            await message.answer(
                "❌ Account not found. Please start again.",
                reply_markup=back_button("manage_accounts"),
                parse_mode="HTML"
            )
            await state.clear()
            return
        
        # Start batch joining process
        await message.answer(
            f"📄 <b>File Processed Successfully!</b>\n\n"
            f"📊 Found <b>{len(valid_links)}</b> valid group links\n"
            f"📱 Account: <code>{account['phone_number']}</code>\n\n"
            f"⚡ <b>Batch joining started:</b>\n"
            f"• 5 groups every 5 minutes\n"
            f"• Automatic progress updates\n"
            f"• Flood wait protection\n\n"
            f"🕐 Estimated time: {len(valid_links) // 5 * 5} minutes\n\n"
            f"<i>You'll receive updates as the process continues.</i>",
            reply_markup=back_button(f"account_{account_id}"),
            parse_mode="HTML"
        )
        
        # Start background task for batch joining
        asyncio.create_task(batch_join_groups(account_id, valid_links, message.from_user.id, message.chat.id))
        await state.clear()
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Failed to process file</b>\n\n"
            f"Error: {str(e)}\n\n"
            f"Please check your file format and try again.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )

async def batch_join_groups(account_id: int, links: list, user_id: int, chat_id: int):
    """Background task to join groups in batches"""
    try:
        # Load account client
        account = await db.get_account(account_id)
        if not account:
            return
        
        client = await session_manager.load_client(
            account['session_string'],
            account_id
        )
        
        # Get bot instance for sending messages
        from main import bot_instance
        
        joined_count = 0
        failed_count = 0
        already_member_count = 0
        
        # Process in batches of 5
        for i in range(0, len(links), 5):
            batch = links[i:i+5]
            batch_results = []
            
            # Join each group in the batch
            for link in batch:
                try:
                    result = await join_single_group(client, link)
                    batch_results.append(result)
                    
                    if result['status'] == 'joined':
                        joined_count += 1
                    elif result['status'] == 'already_member':
                        already_member_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    failed_count += 1
                    batch_results.append({'status': 'error', 'message': str(e)})
            
            # Send batch progress update
            progress = i + len(batch)
            total = len(links)
            percentage = (progress / total) * 100
            
            await bot_instance.send_message(
                chat_id,
                f"📊 <b>Batch Progress Update</b>\n\n"
                f"🔄 Progress: {progress}/{total} ({percentage:.1f}%)\n"
                f"✅ Joined: {joined_count}\n"
                f"ℹ️ Already member: {already_member_count}\n"
                f"❌ Failed: {failed_count}\n\n"
                f"<i>Processing next batch in 5 minutes...</i>",
                parse_mode="HTML"
            )
            
            # Wait 5 minutes between batches (except for last batch)
            if progress < total:
                await asyncio.sleep(300)  # 5 minutes
        
        # Final completion message
        await bot_instance.send_message(
            chat_id,
            f"🎉 <b>Batch Joining Completed!</b>\n\n"
            f"📊 <b>Final Results:</b>\n"
            f"✅ Successfully joined: {joined_count}\n"
            f"ℹ️ Already member: {already_member_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"📝 Total processed: {len(links)}\n\n"
            f"<i>All groups have been processed. Check your account dashboard.</i>",
            parse_mode="HTML"
        )
        
        # Refresh groups if broadcast is running
        if account['is_broadcasting']:
            await broadcast_worker.refresh_groups(account_id)
            
        # Disconnect client
        await client.disconnect()
        
    except Exception as e:
        try:
            from main import bot_instance
            await bot_instance.send_message(
                chat_id,
                f"❌ <b>Batch Joining Error</b>\n\n"
                f"An error occurred during batch processing:\n"
                f"{str(e)}\n\n"
                f"Please check your account and try again.",
                parse_mode="HTML"
            )
        except:
            pass  # If we can't send message, at least don't crash

async def join_single_group(client, group_input: str) -> dict:
    """Join a single group and return result"""
    try:
        # Extract group identifier (reuse existing logic)
        group_identifier = None
        group_input_lower = group_input.lower()
        
        if 'joinchat' in group_input_lower:
            if 'joinchat/' in group_input_lower:
                group_identifier = group_input.split('joinchat/')[-1].split('?')[0].split('/')[0].strip()
            else:
                group_identifier = group_input.strip()
        elif group_input_lower.startswith('https://t.me/') or group_input_lower.startswith('t.me/'):
            group_identifier = group_input.split('t.me/')[-1].split('?')[0].split('/')[0].lstrip('@').strip()
        elif group_input.startswith('@'):
            group_identifier = group_input.lstrip('@').strip()
        else:
            return {'status': 'error', 'message': 'Invalid format'}
        
        # Try to join
        try:
            entity = None
            group_title = None
            group_id = None
            already_member = False
            
            is_invite_link = 'joinchat' in group_input.lower() or (
                len(group_identifier) > 20 and 
                not group_identifier.startswith('@') and
                '/' not in group_identifier
            )
            
            if is_invite_link:
                if 'joinchat/' in group_input.lower():
                    invite_hash = group_input.split('joinchat/')[-1].split('?')[0].split('/')[0]
                else:
                    invite_hash = group_identifier
                
                result = await client(ImportChatInviteRequest(invite_hash))
                if result.chats:
                    entity = result.chats[0]
                    group_title = getattr(entity, 'title', 'Unknown')
                    group_id = entity.id
            else:
                entity = await client.get_entity(group_identifier)
                group_title = getattr(entity, 'title', group_identifier)
                group_id = entity.id
                
                try:
                    await client(JoinChannelRequest(entity))
                except UserAlreadyParticipantError:
                    already_member = True
                except Exception as join_err:
                    try:
                        await client(JoinChannelRequest(group_identifier))
                    except UserAlreadyParticipantError:
                        already_member = True
                    except Exception:
                        raise join_err
            
            return {
                'status': 'already_member' if already_member else 'joined',
                'title': group_title,
                'id': group_id
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
            
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@router.message(JoinGroups.group_link)
async def process_join_group(message: Message, state: FSMContext):
    """Process group link/username and join"""
    data = await state.get_data()
    account_id = data['account_id']
    
    # Check if user wants to finish
    if message.text and message.text.strip().lower() in ['/done', 'done', '/finish', 'finish']:
        await message.answer(
            "✅ Finished joining groups!",
            reply_markup=back_button(f"account_{account_id}")
        )
        await state.clear()
        return
    
    group_input = message.text.strip()
    
    # Validate input
    if not group_input or len(group_input) < 3:
        await message.answer(
            "❌ <b>Invalid Input</b>\n\n"
            "Please send a valid group link or username.\n"
            "Or send <code>/done</code> to finish.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Extract group identifier from various formats
    group_identifier = None
    
    # Normalize input (lowercase for comparison, but keep original for processing)
    group_input_lower = group_input.lower()
    
    if 'joinchat' in group_input_lower:
        # Invite link format: https://t.me/joinchat/xxxxx or t.me/joinchat/xxxxx
        if 'joinchat/' in group_input_lower:
            group_identifier = group_input.split('joinchat/')[-1].split('?')[0].split('/')[0].strip()
        else:
            group_identifier = group_input.strip()
    elif group_input_lower.startswith('https://t.me/') or group_input_lower.startswith('t.me/'):
        # Username format: https://t.me/groupname or t.me/groupname
        group_identifier = group_input.split('t.me/')[-1].split('?')[0].split('/')[0].lstrip('@').strip()
    elif group_input.startswith('@'):
        # Direct username: @groupname
        group_identifier = group_input.lstrip('@').strip()
    else:
        # Assume it's a username without @
        group_identifier = group_input.strip()
    
    # Validate extracted identifier
    if not group_identifier or len(group_identifier) < 3:
        await message.answer(
            "❌ <b>Invalid Format</b>\n\n"
            "Please send a valid group link or username.\n"
            "Examples:\n"
            "• <code>@groupname</code>\n"
            "• <code>https://t.me/groupname</code>\n"
            "• <code>https://t.me/joinchat/xxxxx</code>\n\n"
            "Or send <code>/done</code> to finish.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return
    
    # Show processing message
    status_msg = await message.answer(
        f"🔄 <b>Joining group...</b>\n\n"
        f"⏳ Processing: <code>{group_identifier}</code>",
        parse_mode="HTML"
    )
    
    try:
        # Get account and load client
        account = await db.get_account(account_id)
        if not account:
            await status_msg.edit_text(
                "❌ Account not found",
                reply_markup=back_button("manage_accounts")
            )
            await state.clear()
            return
        
        # Load client (reuse if already loaded for broadcasting)
        client = None
        try:
            # Check if client is already loaded (for broadcasting)
            client = session_manager.get_client(account_id)
            if not client or not client.is_connected():
                # Load new client
                client = await session_manager.load_client(
                    account['session_string'],
                    account_id
                )
            elif not await client.is_user_authorized():
                # Session expired, reload
                await session_manager.disconnect_client(account_id)
                client = await session_manager.load_client(
                    account['session_string'],
                    account_id
                )
        except Exception as e:
            await status_msg.edit_text(
                f"❌ <b>Failed to load account</b>\n\n"
                f"{str(e)}\n\n"
                "Please try again.",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
            return
        
        # Try to join the group
        try:
            entity = None
            group_title = None
            group_id = None
            already_member = False
            
            # Check if it's an invite link or username
            is_invite_link = 'joinchat' in group_input.lower() or (
                len(group_identifier) > 20 and 
                not group_identifier.startswith('@') and
                '/' not in group_identifier
            )
            
            if is_invite_link:
                # Invite link format
                if 'joinchat/' in group_input.lower():
                    invite_hash = group_input.split('joinchat/')[-1].split('?')[0].split('/')[0]
                else:
                    invite_hash = group_identifier
                
                # Join using invite
                try:
                    result = await client(ImportChatInviteRequest(invite_hash))
                    if result.chats:
                        entity = result.chats[0]
                        group_title = getattr(entity, 'title', 'Unknown')
                        group_id = entity.id
                except UserAlreadyParticipantError:
                    # Already a member via invite link - need to get entity differently
                    already_member = True
                    # Try to find the group in dialogs
                    try:
                        async for dialog in client.iter_dialogs():
                            if dialog.is_group or dialog.is_channel:
                                # Check if this might be the group (we can't know for sure from invite hash)
                                # So we'll just inform user they're already a member
                                pass
                    except:
                        pass
            else:
                # Username format - try to get entity and join
                try:
                    # Try to get entity first
                    entity = await client.get_entity(group_identifier)
                    group_title = getattr(entity, 'title', group_identifier)
                    group_id = entity.id
                    
                    # Try to join
                    try:
                        await client(JoinChannelRequest(entity))
                    except UserAlreadyParticipantError:
                        # Already a member - that's fine, we'll save it anyway
                        already_member = True
                    except Exception as join_err:
                        # If JoinChannelRequest fails, try with username string
                        try:
                            await client(JoinChannelRequest(group_identifier))
                        except UserAlreadyParticipantError:
                            already_member = True
                        except Exception:
                            raise join_err
                    
                except (ValueError, UsernameNotOccupiedError):
                    # Entity not found
                    raise ValueError(f"Group '{group_identifier}' not found")
                except ChannelPrivateError:
                    raise Exception("This group is private and requires an invitation link")
            
            # If we have entity info, save it (even if already a member)
            if entity and group_id:
                # Save to database
                await db.save_groups(account_id, [{
                    'id': group_id,
                    'title': group_title,
                    'username': getattr(entity, 'username', None)
                }])
                
                # Refresh groups in broadcast if running
                if account['is_broadcasting']:
                    await broadcast_worker.refresh_groups(account_id)
                
                await db.add_log(
                    account_id,
                    "groups",
                    f"{'Already in' if already_member else 'Joined'} group: {group_title}",
                    "success" if not already_member else "info"
                )
                
                if already_member:
                    await status_msg.edit_text(
                        f"ℹ️ <b>Already a member</b>\n\n"
                        f"📢 Group: <b>{group_title}</b>\n"
                        f"🆔 ID: <code>{group_id}</code>\n\n"
                        f"<i>Group has been added to your broadcast list.</i>\n"
                        f"<i>Send another link or /done to finish.</i>",
                        reply_markup=cancel_keyboard(),
                        parse_mode="HTML"
                    )
                else:
                    await status_msg.edit_text(
                        f"✅ <b>Successfully joined!</b>\n\n"
                        f"📢 Group: <b>{group_title}</b>\n"
                        f"🆔 ID: <code>{group_id}</code>\n\n"
                        f"<i>Send another link or /done to finish.</i>",
                        reply_markup=cancel_keyboard(),
                        parse_mode="HTML"
                    )
            elif already_member:
                # Already member but couldn't get entity (invite link case)
                await status_msg.edit_text(
                    f"ℹ️ <b>Already a member</b>\n\n"
                    f"You're already in this group.\n\n"
                    f"<i>Send another link or /done to finish.</i>",
                    reply_markup=cancel_keyboard(),
                    parse_mode="HTML"
                )
            else:
                raise Exception("Failed to join group - could not get group information")
            
        except ValueError as e:
            # Entity not found
            await status_msg.edit_text(
                f"❌ <b>Group not found</b>\n\n"
                f"The group <code>{group_identifier}</code> could not be found.\n\n"
                f"<b>Possible reasons:</b>\n"
                f"• Invalid username or link\n"
                f"• Group is private and requires invitation\n"
                f"• Group doesn't exist\n\n"
                f"<i>Try another link or send /done to finish.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
        except (InviteHashExpiredError, InviteHashInvalidError) as e:
            await status_msg.edit_text(
                f"❌ <b>Invalid invite link</b>\n\n"
                f"The invite link is invalid or expired.\n\n"
                f"<i>Try another link or send /done to finish.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
        except ChannelPrivateError:
            await status_msg.edit_text(
                f"❌ <b>Private Group</b>\n\n"
                f"This group is private and requires an invitation link.\n\n"
                f"<i>Try another link or send /done to finish.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
        except FloodWaitError as e:
            wait_time = e.seconds
            await status_msg.edit_text(
                f"⏰ <b>Rate Limited</b>\n\n"
                f"Please wait {wait_time} seconds before trying again.\n\n"
                f"<i>Telegram limits how often you can join groups.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            error_msg = str(e)
            await status_msg.edit_text(
                f"❌ <b>Failed to join</b>\n\n"
                f"{error_msg}\n\n"
                f"<i>Try another link or send /done to finish.</i>",
                reply_markup=cancel_keyboard(),
                parse_mode="HTML"
            )
    
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>Error</b>\n\n"
            f"{str(e)}\n\n"
            f"<i>Try another link or send /done to finish.</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )

# Import required Telethon functions
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest