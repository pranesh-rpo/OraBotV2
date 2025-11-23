from aiogram import Router, F
import asyncio
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.database.operations import DatabaseOperations
from app.bot.keyboards import (
    main_menu_keyboard, verification_keyboard, back_button
)
from app.bot.menus import (
    welcome_message, verification_message, about_message, privacy_message
)
from config import Config

router = Router()
db = DatabaseOperations()

async def check_user_verification(bot, user_id: int) -> bool:
    """Check if user is member of verification channel"""
    try:
        member = await bot.get_chat_member(
            Config.VERIFICATION_CHANNEL_ID,
            user_id
        )
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        # Log the error for debugging but return False quickly
        return False

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    await state.clear()
    
    user = message.from_user
    
    # Run user data addition and verification check concurrently
    user_task = db.add_user(user.id, user.username, user.first_name)
    verify_task = check_user_verification(message.bot, user.id)
    
    # Quick cleanup - only delete last 10 messages to reduce delay
    cleanup_task = None
    try:
        if message.chat.type == "private":
            chat_id = message.chat.id
            start_id = message.message_id
            ids = list(range(max(1, start_id - 10), start_id))  # Reduced from 200 to 10
            batch = []
            for mid in ids:
                async def del_one(m=mid):
                    try:
                        await message.bot.delete_message(chat_id, m)
                    except Exception:
                        return
                batch.append(del_one())
                if len(batch) >= 5:  # Reduced batch size from 20 to 5
                    await asyncio.gather(*batch, return_exceptions=True)
                    batch = []
            if batch:
                await asyncio.gather(*batch, return_exceptions=True)
    except Exception:
        pass
    
    # Wait for user data and verification to complete
    await user_task
    is_verified = await verify_task
    
    if not is_verified:
        await message.answer(
            verification_message(),
            reply_markup=verification_keyboard(Config.VERIFICATION_CHANNEL),
            parse_mode="HTML"
        )
    else:
        await db.verify_user(user.id)
        await message.answer(
            welcome_message(user.first_name),
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "check_verification")
async def callback_check_verification(callback: CallbackQuery):
    """Check if user joined channel"""
    is_verified = await check_user_verification(callback.bot, callback.from_user.id)
    
    if is_verified:
        await db.verify_user(callback.from_user.id)
        await callback.message.edit_text(
            welcome_message(callback.from_user.first_name),
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer("✅ Verification successful!")
    else:
        await callback.answer(
            "❌ Please join the channel first!",
            show_alert=True
        )

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Return to main menu"""
    await state.clear()
    
    # Check verification again
    is_verified = await check_user_verification(callback.bot, callback.from_user.id)
    
    if not is_verified:
        await callback.message.edit_text(
            verification_message(),
            reply_markup=verification_keyboard(Config.VERIFICATION_CHANNEL),
            parse_mode="HTML"
        )
        await callback.answer("Please verify first")
        return
    
    await callback.message.edit_text(
        welcome_message(callback.from_user.first_name),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery):
    """Show about information"""
    await callback.message.edit_text(
        about_message(),
        reply_markup=back_button("main_menu"),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "privacy")
async def callback_privacy(callback: CallbackQuery):
    """Show privacy policy"""
    await callback.message.edit_text(
        privacy_message(),
        reply_markup=back_button("main_menu"),
        parse_mode="HTML"
    )
    await callback.answer()