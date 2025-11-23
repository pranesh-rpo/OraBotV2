from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from app.database.operations import DatabaseOperations
from app.client.broadcast_worker import broadcast_worker
from app.bot.keyboards import (
    cancel_keyboard, back_button, account_dashboard_keyboard, schedule_type_keyboard
)

router = Router()
db = DatabaseOperations()


class ScheduleSetup(StatesGroup):
    message = State()
    schedule_type = State()
    start_time = State()
    end_time = State()


@router.callback_query(F.data.startswith("set_schedule_"))
async def start_schedule_setup(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("_")[2])

    await callback.message.edit_text(
        "🕐 <b>Schedule Broadcast</b>\n\n"
        "Choose the type of schedule you want to set:\n\n"
        "⏰ <b>Normal Schedule:</b> Time-based windows (e.g., 9 AM - 5 PM)\n"
        "⭐ <b>Special Schedule:</b> Advanced patterns (specific days, dates, hourly patterns)",
        reply_markup=schedule_type_keyboard(),
        parse_mode="HTML"
    )
    await state.update_data(account_id=account_id)
    await state.set_state(ScheduleSetup.schedule_type)
    await callback.answer()


@router.callback_query(F.data.startswith("schedule_type_"))
async def handle_schedule_type(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    
    schedule_type = callback.data.split("_")[2]
    
    await state.update_data(schedule_type=schedule_type)
    
    if schedule_type == "normal":
        await callback.message.edit_text(
            "⏰ <b>Normal Schedule Setup</b>\n\n"
            "Send the broadcast message you want to post to your groups.\n\n"
            "<i>After the message, I will ask for start and end time (IST).</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
    else:  # special
        await callback.message.edit_text(
            "⭐ <b>Special Schedule Setup</b>\n\n"
            "Send the broadcast message you want to post to your groups.\n\n"
            "<i>After the message, I will ask for advanced schedule options.</i>",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
    
    await state.set_state(ScheduleSetup.message)
    await callback.answer()


@router.message(ScheduleSetup.message)
async def capture_message_text(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]

    text = message.text or ""
    text = text.strip()
    if not text:
        await message.answer(
            "❌ <b>Empty Message</b>\n\nSend some text to use for broadcast.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(message_text=text)
    await message.answer(
        "✅ <b>Message Saved</b>\n\n"
        "Enter the <b>start time</b> in 24-hour format (IST) like <code>09:00</code> or <code>14:30</code>.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ScheduleSetup.start_time)


@router.message(ScheduleSetup.start_time)
async def capture_start_time(message: Message, state: FSMContext):
    start_time = (message.text or "").strip()
    try:
        datetime.strptime(start_time, "%H:%M")
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Time</b>\n\nUse HH:MM (24-hour). Examples: <code>09:00</code>, <code>18:30</code>.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.update_data(start_time=start_time)
    await message.answer(
        f"✅ <b>Start Time Set:</b> {start_time} (IST)\n\nEnter the <b>end time</b> in HH:MM.",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(ScheduleSetup.end_time)


@router.message(ScheduleSetup.end_time)
async def finalize_schedule(message: Message, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]
    message_text = data["message_text"]
    start_time = data["start_time"]
    end_time = (message.text or "").strip()
    schedule_type = data.get("schedule_type", "normal")

    try:
        datetime.strptime(end_time, "%H:%M")
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Time</b>\n\nUse HH:MM (24-hour). Examples: <code>09:00</code>, <code>23:59</code>.",
            reply_markup=cancel_keyboard(),
            parse_mode="HTML"
        )
        return

    await db.set_account_message(account_id, message_text)
    await db.set_schedule(account_id, start_time, end_time, schedule_type)
    await db.add_log(account_id, "settings", f"{schedule_type.title()} schedule set: {start_time} - {end_time}", "success")

    account = await db.get_account(account_id)
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(tz=ist)
    def _within(s: str, e: str) -> bool:
        st = datetime.strptime(s, "%H:%M").time()
        et = datetime.strptime(e, "%H:%M").time()
        cur = now_ist.time()
        if st > et:
            return cur >= st or cur <= et
        return st <= cur <= et
    if _within(start_time, end_time) and not bool(account.get("is_broadcasting")):
        ok, info = await broadcast_worker.start_broadcast(account_id)
        status = "success" if ok else "error"
        await db.add_log(account_id, "broadcast", f"Auto-start after scheduling: {info}", status)
    await message.answer(
        f"✅ <b>{schedule_type.title()} Schedule Saved</b>\n\n"
        f"<b>Message:</b> {message_text[:120]}{'…' if len(message_text)>120 else ''}\n"
        f"<b>Start:</b> {start_time} IST\n"
        f"<b>End:</b> {end_time} IST\n\n"
        f"Broadcast will auto start/stop based on this schedule.",
        reply_markup=account_dashboard_keyboard(account_id, bool(account and account.get("is_broadcasting"))),
        parse_mode="HTML"
    )
    await state.clear()