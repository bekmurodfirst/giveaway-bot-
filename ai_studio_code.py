import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
import aiosqlite

BOT_TOKEN = "8906701401:AAFS8iJKfRRvOQrtK4rBm1At85eL2-CLFPM"
ADMIN_ID = 2091666040
DB_PATH = "giveaway.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                invited_by INTEGER,
                referrals_count INTEGER DEFAULT 0,
                gift_sent INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        defaults = [
            ("target_count", "3"),
            ("gift_file_id", ""),
            ("gift_caption", "Tabriklaymiz! Siz shartni bajardingiz va sovg'angizni qabul qilib oling! 🎁"),
            ("start_text", "Assalomu alaykum! Giveaway tanlovimizga xush kelibsiz.\n\nSovg'ani qo'lga kiritish uchun do'stlaringizni taklif qiling!")
        ]
        for key, val in defaults:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else ""

async def update_setting(key: str, val: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE settings SET value = ? WHERE key = ?", (val, key))
        await db.commit()

class AdminStates(StatesGroup):
    waiting_for_target = State()
    waiting_for_file = State()
    waiting_for_start_text = State()
    waiting_for_broadcast = State()

def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔗 Taklif havolam"), KeyboardButton(text="📊 Mening ballarim")],
            [KeyboardButton(text="🏆 Reyting (Top-10)"), KeyboardButton(text="🎁 Sovg'ani olish")]
        ],
        resize_keyboard=True
    )

def admin_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 To'liq statistika (Kim nechta qo'shgan)", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🎯 Shartni o'zgartirish (Odamlar soni)", callback_data="admin_set_target")],
            [InlineKeyboardButton(text="📁 Sovg'a faylini yuklash (PDF/DOC)", callback_data="admin_set_gift")],
            [InlineKeyboardButton(text="✍️ Kirish matnini o'zgartirish", callback_data="admin_set_text")],
            [InlineKeyboardButton(text="📢 Foydalanuvchilarga xabar yuborish", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🔄 Natijalarni nollash (Yangi tanlov)", callback_data="admin_reset_confirm")]
        ]
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username or ""

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    referrer_id = None
    if args and args[0].isdigit():
        ref_candidate = int(args[0])
        if ref_candidate != user_id:
            referrer_id = ref_candidate

    target = int(await get_setting("target_count"))
    start_text = await get_setting("start_text")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            exists = await cur.fetchone()

        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, full_name, username, invited_by) VALUES (?, ?, ?, ?)",
                (user_id, full_name, username, referrer_id)
            )

            if referrer_id:
                await db.execute(
                    "UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?",
                    (referrer_id,)
                )
                await db.commit()

                async with db.execute(
                    "SELECT referrals_count, gift_sent FROM users WHERE user_id = ?", (referrer_id,)
                ) as cur:
                    inviter_data = await cur.fetchone()

                if inviter_data:
                    count, gift_sent = inviter_data
                    try:
                        await bot.send_message(
                            chat_id=referrer_id,
                            text=f"🔔 Sizning havolangiz orqali <b>{full_name}</b> qo'shildi!\n"
                                 f"Jami takliflaringiz: <b>{count}/{target}</b>",
                            parse_mode="HTML"
                        )
                        if count >= target and not gift_sent:
                            file_id = await get_setting("gift_file_id")
                            caption = await get_setting("gift_caption")
                            if file_id:
                                await bot.send_document(chat_id=referrer_id, document=file_id, caption=caption)
                                await db.execute("UPDATE users SET gift_sent = 1 WHERE user_id = ?", (referrer_id,))
                                await db.commit()
                            else:
                                await bot.send_message(
                                    chat_id=referrer_id,
                                    text="🎉 Tabriklaymiz! Siz shartni bajardingiz! Tez orada sovg'a fayli yuboriladi."
                                )
                    except Exception as e:
                        logging.error(f"Xatolik: {e}")
            else:
                await db.commit()

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    msg = (
        f"{start_text}\n\n"
        f"🎯 <b>Sovg'ani olish sharti:</b> {target} ta do'st taklif qilish.\n"
        f"🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n<code>{ref_link}</code>"
    )
    await message.answer(msg, parse_mode="HTML", reply_markup=main_menu_kb())

@dp.message(F.text == "🔗 Taklif havolam")
async def show_link(message: types.Message):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    await message.answer(
        f"Do'stlaringizni taklif qilish uchun havolangiz:\n\n👉 <code>{ref_link}</code>\n\nBuni do'stlaringizga, guruh va kanallarga ulashing!",
        parse_mode="HTML"
    )

@dp.message(F.text == "📊 Mening ballarim")
async def show_score(message: types.Message):
    target = int(await get_setting("target_count"))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT referrals_count, gift_sent FROM users WHERE user_id = ?", (message.from_user.id,)
        ) as cur:
            data = await cur.fetchone()

    count = data[0] if data else 0
    status = "Yuborilgan ✅" if (data and data[1]) else f"Yana {max(0, target - count)} ta kerak ⏳"

    await message.answer(
        f"📊 <b>Sizning holatingiz:</b>\n\n👥 Taklif qilinganlar: <b>{count} ta</b>\n🎯 Kerakli miqdor: <b>{target} ta</b>\n🎁 Sovg'a holati: <b>{status}</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "🎁 Sovg'ani olish")
async def claim_gift(message: types.Message):
    target = int(await get_setting("target_count"))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referrals_count FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            data = await cur.fetchone()

    count = data[0] if data else 0
    if count >= target:
        file_id = await get_setting("gift_file_id")
        caption = await get_setting("gift_caption")
        if file_id:
            await message.answer_document(document=file_id, caption=caption)
        else:
            await message.answer("Siz shartni bajardingiz! Tez orada admin sovg'a faylini joylaydi.")
    else:
        await message.answer(f"Siz hali shartni bajarmadingiz. Yana <b>{target - count}</b> ta do'st taklif qilishingiz kerak!", parse_mode="HTML")

@dp.message(F.text == "🏆 Reyting (Top-10)")
async def show_top(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name, referrals_count FROM users ORDER BY referrals_count DESC LIMIT 10") as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.answer("Hozircha hech kim taklif qilinmagan.")
        return

    text = "🏆 <b>Eng ko'p odam taklif qilganlar (Top-10):</b>\n\n"
    for i, (name, count) in enumerate(rows, 1):
        text += f"{i}. <b>{name}</b> — {count} ta taklif\n"

    await message.answer(text, parse_mode="HTML")

@dp.message(Command("admin"))
async def open_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("⚙️ <b>Giveaway boshqaruv paneli:</b>", parse_mode="HTML", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*), SUM(referrals_count) FROM users") as cur:
            total_users, total_refs = await cur.fetchone()

        async with db.execute(
            "SELECT user_id, full_name, username, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT 20"
        ) as cur:
            active_users = await cur.fetchall()

    text = (
        f"📊 <b>Umumiy statistika:</b>\n"
        f"👥 Jami bot foydalanuvchilari: <b>{total_users or 0} ta</b>\n"
        f"🔗 Jami takliflar: <b>{total_refs or 0} ta</b>\n\n"
        f"📋 <b>Eng faol taklif qiluvchilar (Top-20):</b>\n"
    )

    if active_users:
        for uid, name, uname, count in active_users:
            mention = f"@{uname}" if uname else f"ID: <code>{uid}</code>"
            text += f"• {name} ({mention}) — <b>{count} ta</b>\n"
    else:
        text += "Hali hech kim do'st taklif qilmagan.\n"

    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_set_target")
async def admin_set_target(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    cur_val = await get_setting("target_count")
    await call.message.answer(f"Hozirgi talab: <b>{cur_val} ta</b> do'st.\nYangi sonni yuboring (masalan: 5):", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_target)

@dp.message(AdminStates.waiting_for_target)
async def save_target(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Faqat musbat butun son kiriting!")
        return
    await update_setting("target_count", message.text)
    await message.answer(f"✅ Yangi shart belgilandi: <b>{message.text} ta</b> do'st!", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "admin_set_gift")
async def admin_set_gift(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("Sovg'a qilinadigan PDF yoki DOC faylni shu yerga yuboring:")
    await state.set_state(AdminStates.waiting_for_file)

@dp.message(AdminStates.waiting_for_file, F.document)
async def save_gift_file(message: types.Message, state: FSMContext):
    file_id = message.document.file_id
    await update_setting("gift_file_id", file_id)
    await message.answer("✅ Yangi sovg'a fayli saqlandi! Endi shartni bajarganlarga shu fayl beriladi.")
    await state.clear()

@dp.callback_query(F.data == "admin_set_text")
async def admin_set_text(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("Botga yangi kiruvchilar uchun kirish xabari matnini yuboring:")
    await state.set_state(AdminStates.waiting_for_start_text)

@dp.message(AdminStates.waiting_for_start_text)
async def save_start_text(message: types.Message, state: FSMContext):
    await update_setting("start_text", message.text)
    await message.answer("✅ Start matni yangilandi!")
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("Barcha a'zolarga jo'natiladigan xabar matnini yuboring:")
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def send_broadcast(message: types.Message, state: FSMContext):
    text_to_send = message.text
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = await cur.fetchall()

    count = 0
    for (u_id,) in users:
        try:
            await bot.send_message(chat_id=u_id, text=text_to_send)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Xabar <b>{count}</b> ta foydalanuvchiga yetkazildi.", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "admin_reset_confirm")
async def reset_scores(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET referrals_count = 0, gift_sent = 0")
        await db.commit()
    await call.message.edit_text("🔄 Barcha taklif ballari nollashtirildi!", reply_markup=admin_menu_kb())

async def main():
    await init_db()
    print("Bot muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())