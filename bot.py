"""
NAKRUTKA BLOCKER BOT
====================
Telegram kanal va guruhlarga kelayotgan nakrutka (fake/bot) akkauntlarni
avtomatik aniqlab bloklaydi.

Ishga tushirish:  python bot.py
"""
from __future__ import annotations

import asyncio
import html
import logging
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import ChatMemberUpdatedFilter, Command, CommandObject, JOIN_TRANSITION
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ChatJoinRequest,
    ChatMemberUpdated,
    ChatPermissions,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    User,
    WebAppInfo,
)

import config
import scan_core
import webapp_server
from database import DB
from detector import Candidate, Verdict, analyze

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nakrutka")

router = Router()
db = DB()

MODE_LABELS = {
    "ban": "🚫 Bloklash (ban)",
    "kick": "👋 Chiqarish (kick)",
    "mute": "🔇 Ovozini o'chirish",
    "report": "📝 Faqat xabar berish",
}
_last_link_rotate: dict[int, float] = {}

STRICT_LABELS = {
    0: "o'chiq",
    1: "rasm+username yo'q",
    2: "rasm yo'q",
    3: "maksimal",
}
# Tezkor sozlash: (chegara, qattiqlik)
PRESETS = {
    "soft":     ("🟢 Yumshoq — faqat aniq nakrutkalar", 65, 0),
    "balanced": ("🔵 Muvozanatli — tavsiya etiladi", 50, 0),
    "hard":     ("🟠 Qattiq — rasm+username yo'q = blok", 42, 1),
    "iron":     ("🔴 Temir — rasmsizlar bloklanadi", 34, 2),
    "max":      ("⚫️ Maksimal — yangi/usernamesiz ham blok", 25, 3),
}


# ═══════════════════════════════════════════════════════════ yordamchilar
def esc(text: str | None) -> str:
    return html.escape(text or "")


def user_link(user_id: int, name: str) -> str:
    return f'<a href="tg://user?id={user_id}">{esc(name) or user_id}</a>'


async def safe(method, *args, **kwargs):
    """Telegram API'ni xavfsiz chaqiradi.

    Metodni EMAS, metod nomini uzatamiz: flood-limit bo'lsa qayta urinish uchun
    har safar yangi so'rov yaratish kerak (bir marta await qilingan coroutine'ni
    qayta await qilish mumkin emas).
    """
    for attempt in range(1, 4):
        try:
            return await method(*args, **kwargs)
        except TelegramRetryAfter as e:
            log.warning("Flood-limit: %s sek kutilmoqda (urinish %s/3)",
                        e.retry_after, attempt)
            await asyncio.sleep(e.retry_after + 1)
        except TelegramAPIError as e:
            log.warning("API xato (%s): %s", getattr(method, "__name__", method), e)
            return None
    return None


async def fetch_profile(bot: Bot, user_id: int) -> tuple[bool | None, str | None]:
    """Profil rasmi bor-yo'qligi va bio (aniqlanmasa — None)."""
    try:
        info = await bot.get_chat(user_id)
    except TelegramAPIError:
        return None, None
    return (info.photo is not None), getattr(info, "bio", None)


def reply_user(msg: Message) -> User | None:
    """Reply qilingan xabar egasi (forward bo'lsa — asl muallif)."""
    r = msg.reply_to_message
    if r is None:
        return None
    origin = getattr(r, "forward_origin", None)
    sender = getattr(origin, "sender_user", None) if origin is not None else None
    return sender or r.from_user


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR)


def log_targets() -> list[int]:
    return [config.LOG_CHAT_ID] if config.LOG_CHAT_ID else list(config.ADMIN_IDS)


async def send_log(bot: Bot, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    for target in log_targets():
        await safe(bot.send_message, target, text, reply_markup=kb, disable_web_page_preview=True)


# ═══════════════════════════════════════════════════════════ tahlil
async def judge(bot: Bot, chat_id: int, user: User, link: str | None) -> Verdict:
    st = db.settings(chat_id)
    has_photo, bio = await fetch_profile(bot, user.id)

    db.record_join(chat_id, user.id, link)
    burst = db.joins_in_window(chat_id, config.BURST_WINDOW)
    same_link = db.same_link_in_window(chat_id, link, config.BURST_WINDOW)

    cand = Candidate(
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language_code=user.language_code,
        is_bot=bool(user.is_bot),
        is_premium=bool(user.is_premium),
        has_photo=has_photo,
        bio=bio,
        burst_count=burst,
        same_link_count=same_link,
    )
    return analyze(
        cand,
        threshold=st["threshold"],
        new_account_id=config.NEW_ACCOUNT_ID,
        very_new_account_id=config.VERY_NEW_ACCOUNT_ID,
        old_account_id=config.OLD_ACCOUNT_ID,
        burst_limit=config.BURST_LIMIT,
        strict_level=st["strict"],
    )


def verdict_card(chat_title: str, user: User, v: Verdict, action_text: str) -> str:
    uname = f"@{user.username}" if user.username else "—"
    return (
        f"{v.emoji} <b>{esc(action_text)}</b>\n\n"
        f"👤 {user_link(user.id, user.full_name)}\n"
        f"🆔 <code>{user.id}</code>\n"
        f"🔗 {esc(uname)}\n"
        f"💬 {esc(chat_title)}\n"
        f"📊 Ball: <b>{v.score}</b>/{v.threshold}\n\n"
        f"<b>Sabablar:</b>\n{esc(v.report())}"
    )


def action_kb(chat_id: int, user_id: int, blocked: bool) -> InlineKeyboardMarkup:
    if blocked:
        rows = [[
            InlineKeyboardButton(text="♻️ Blokdan chiqarish",
                                 callback_data=f"act:unban:{chat_id}:{user_id}"),
            InlineKeyboardButton(text="✅ Oq ro'yxat",
                                 callback_data=f"act:white:{chat_id}:{user_id}"),
        ]]
    else:
        rows = [[
            InlineKeyboardButton(text="🚫 Bloklash",
                                 callback_data=f"act:ban:{chat_id}:{user_id}"),
            InlineKeyboardButton(text="✅ Oq ro'yxat",
                                 callback_data=f"act:white:{chat_id}:{user_id}"),
        ]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


RIGHTS_WARNING = (
    "\n\n❗️ <b>Chora qo'llanmadi!</b> Sabab odatda bitta: botda "
    "«A'zolarni bloklash» (Ban Users) huquqi yo'q.\n"
    "Kanal → Administrators → bot → <b>Ban Users</b> ni yoqing."
)


async def apply_action(bot: Bot, chat_id: int, user_id: int,
                       mode: str) -> tuple[str, bool]:
    """Chora qo'llaydi. Qaytaradi: (amal nomi, haqiqatan bajarildimi).

    Telegram xatosi (huquq yo'q, flood va h.k.) bo'lsa False qaytadi —
    shunda logda «bloklandi» deb yolg'on yozilmaydi.
    """
    if mode == "ban":
        ok = await safe(bot.ban_chat_member, chat_id, user_id)
        return "ban", ok is not None
    if mode == "kick":
        ok = await safe(bot.ban_chat_member, chat_id, user_id)
        if ok is not None:
            await asyncio.sleep(0.5)
            await safe(bot.unban_chat_member, chat_id, user_id, only_if_banned=True)
        return "kick", ok is not None
    if mode == "mute":
        ok = await safe(bot.restrict_chat_member, chat_id, user_id,
                        permissions=ChatPermissions(can_send_messages=False))
        if ok is None:  # kanalda mute ishlamaydi -> ban
            ok2 = await safe(bot.ban_chat_member, chat_id, user_id)
            return "ban", ok2 is not None
        return "mute", True
    return "report", True


async def maybe_rotate_link(bot: Bot, chat_id: int, burst: int) -> None:
    if not config.AUTO_ROTATE_LINK or burst < config.BURST_LIMIT:
        return
    if time.time() - _last_link_rotate.get(chat_id, 0) < 600:
        return
    _last_link_rotate[chat_id] = time.time()
    new_link = await safe(bot.export_chat_invite_link, chat_id)
    if new_link:
        await send_log(bot, (
            "🔄 <b>Nakrutka to'lqini aniqlandi — taklif havolasi yangilandi.</b>\n"
            f"💬 {esc(db.settings(chat_id)['title'])}\n"
            f"🔗 Yangi havola: {esc(str(new_link))}\n"
            "<i>Eski havola endi ishlamaydi.</i>"
        ))


# ═══════════════════════════════════════════════ 1) Kirish so'rovlari
# Kanalda "Yangi a'zolarni tasdiqlash" yoqilgan bo'lsa, bot fake'ni
# KANALGA KIRISHIDAN OLDIN rad etadi — eng ishonchli himoya.
@router.chat_join_request()
async def on_join_request(req: ChatJoinRequest) -> None:
    bot = req.bot
    chat_id = req.chat.id
    user = req.from_user
    db.register_chat(chat_id, req.chat.title or str(chat_id), req.chat.type)
    st = db.settings(chat_id)

    if not st["enabled"]:
        await safe(bot.approve_chat_join_request, chat_id, user.id)
        return
    if db.is_whitelisted(chat_id, user.id) or await is_chat_admin(bot, chat_id, user.id):
        await safe(bot.approve_chat_join_request, chat_id, user.id)
        return

    link = req.invite_link.invite_link if req.invite_link else None
    v = await judge(bot, chat_id, user, link)

    if config.PROTECT_PREMIUM and user.is_premium:
        v.reasons.append("Premium himoyasi: chora qo'llanmadi")
        v.score = 0

    if v.is_fake and st["mode"] != "report":
        ok = await safe(bot.decline_chat_join_request, chat_id, user.id)
        if ok is None:
            db.log_event(chat_id, user.id, user.full_name, user.username,
                         v.score, v.reasons + ["So'rov rad etilmadi"], "failed")
            await send_log(bot, verdict_card(st["title"], user, v,
                                             "Nakrutka aniqlandi, lekin rad etilmadi")
                           + RIGHTS_WARNING,
                           action_kb(chat_id, user.id, blocked=False))
            log.error("RAD ETILMADI %s (%s)", user.full_name, user.id)
            return
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons, "decline")
        await send_log(bot, verdict_card(st["title"], user, v,
                                         "Kirish so'rovi RAD ETILDI (nakrutka)"),
                       action_kb(chat_id, user.id, blocked=True))
        log.info("RAD ETILDI %s (%s) ball=%s", user.full_name, user.id, v.score)
    elif v.is_fake:
        await safe(bot.approve_chat_join_request, chat_id, user.id)
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons, "pass")
        await send_log(bot, verdict_card(st["title"], user, v,
                                         "Shubhali (report rejimi — tasdiqlandi)"),
                       action_kb(chat_id, user.id, blocked=False))
    else:
        await safe(bot.approve_chat_join_request, chat_id, user.id)
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons, "approve")
        if v.level == "suspicious":
            await send_log(bot, verdict_card(st["title"], user, v,
                                             "Shubhali, lekin tasdiqlandi"),
                           action_kb(chat_id, user.id, blocked=False))


# ═══════════════════════════════════════════════ 2) Kanalga/guruhga kirish
@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def on_member_joined(ev: ChatMemberUpdated) -> None:
    bot = ev.bot
    chat_id = ev.chat.id
    user = ev.new_chat_member.user
    if user.id == (await bot.me()).id:
        return

    db.register_chat(chat_id, ev.chat.title or str(chat_id), ev.chat.type)
    st = db.settings(chat_id)
    if not st["enabled"]:
        return
    if db.is_whitelisted(chat_id, user.id):
        return
    if await is_chat_admin(bot, chat_id, user.id):
        return

    link = ev.invite_link.invite_link if ev.invite_link else None
    v = await judge(bot, chat_id, user, link)

    if config.PROTECT_PREMIUM and user.is_premium:
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons + ["Premium himoyasi"], "pass")
        return

    burst = db.joins_in_window(chat_id, config.BURST_WINDOW)
    await maybe_rotate_link(bot, chat_id, burst)

    if not v.is_fake:
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons, "pass")
        if v.level == "suspicious":
            await send_log(bot, verdict_card(st["title"], user, v, "Shubhali a'zo"),
                           action_kb(chat_id, user.id, blocked=False))
        return

    mode = st["mode"]
    if mode == "report":
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons, "report")
        await send_log(bot, verdict_card(st["title"], user, v,
                                         "NAKRUTKA aniqlandi (report rejimi)"),
                       action_kb(chat_id, user.id, blocked=False))
        return

    done, ok = await apply_action(bot, chat_id, user.id, mode)
    if not ok:
        db.log_event(chat_id, user.id, user.full_name, user.username,
                     v.score, v.reasons + ["Chora qo'llanmadi (huquq yo'q?)"], "failed")
        await send_log(bot, verdict_card(st["title"], user, v,
                                         "Nakrutka ANIQLANDI, lekin bloklanmadi")
                       + RIGHTS_WARNING,
                       action_kb(chat_id, user.id, blocked=False))
        log.error("BLOKLANMADI %s (%s) — botda huquq yo'q?", user.full_name, user.id)
        return

    db.log_event(chat_id, user.id, user.full_name, user.username, v.score, v.reasons, done)
    titles = {"ban": "BLOKLANDI", "kick": "CHIQARILDI", "mute": "OVOZI O'CHIRILDI"}
    await send_log(bot, verdict_card(st["title"], user, v,
                                     f"Nakrutka {titles.get(done, done)}"),
                   action_kb(chat_id, user.id, blocked=True))
    log.info("%s %s (%s) ball=%s", done.upper(), user.full_name, user.id, v.score)


# ═══════════════════════════════════════════════ 3) Bot qo'shilganda
async def notify_channel_owner(bot: Bot, chat_id: int, title: str, adder: User,
                               is_admin: bool) -> bool:
    """Botni admin qilgan odamga shaxsiy xabar + «Tekshirish» tugmasi.

    Qaytaradi: xabar yetib bordimi (odam botni oldin /start qilган bo'lsa — ha).
    """
    if adder is None or adder.is_bot:
        return False
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔍 Nakrutkalarni tekshirish",
                             callback_data=f"scan:pick:{chat_id}")]])
    text = (
        f"✅ <b>{esc(title)}</b> kanaliga qo'shdingiz, rahmat!\n\n"
        + ("🛡 Admin huquqim bor — <b>yangi</b> nakrutkalardan himoya allaqachon "
           "ishlayapti.\n\n"
           if is_admin else
           "⚠️ Hali admin emasman. «A'zolarni bloklash» (Ban Users) huquqini "
           "bersangiz himoya boshlanadi.\n\n")
        + "Kanalda <b>allaqachon o'tirgan</b> eski nakrutkalarni ham tozalash "
          "uchun pastdagi tugmani bosing 👇"
    )
    ok = await safe(bot.send_message, adder.id, text, reply_markup=kb)
    return ok is not None


@router.my_chat_member()
async def on_bot_status(ev: ChatMemberUpdated) -> None:
    bot = ev.bot
    me = await bot.me()
    if ev.new_chat_member.user.id != me.id:
        return
    status = ev.new_chat_member.status
    title = ev.chat.title or str(ev.chat.id)
    adder = ev.from_user

    if status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
        db.register_chat(ev.chat.id, title, ev.chat.type)
        is_admin = status == ChatMemberStatus.ADMINISTRATOR
        if adder is not None and not adder.is_bot:
            db.set_added_by(ev.chat.id, adder.id, adder.full_name)

        # 1) botni qo'shgan ODAMGA xabar
        delivered = await notify_channel_owner(bot, ev.chat.id, title, adder, is_admin)

        # 2) agar xabar yetmasa (odam botni /start qilmagan) — kanalga havolali tugma
        if not delivered and adder is not None and not adder.is_bot:
            try:
                uname = (await bot.me()).username
                deep = f"https://t.me/{uname}?start=scan_{ev.chat.id}"
                await safe(bot.send_message, ev.chat.id,
                           "🛡 <b>Nakrutka himoyasi yoqildi.</b>\n"
                           "Eski nakrutkalarni tekshirish uchun bosing:",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                               InlineKeyboardButton(text="🔍 Botni ochish va tekshirish",
                                                    url=deep)]]))
            except Exception:  # noqa: BLE001
                pass

        # 3) bot egasiga qisqa bildirishnoma
        who = f"{esc(adder.full_name)}" + (f" (@{adder.username})" if adder and adder.username else "") \
            if adder else "—"
        await send_log(bot,
                       f"➕ Bot yangi joyga qo'shildi: <b>{esc(title)}</b>\n"
                       f"🆔 <code>{ev.chat.id}</code>\n"
                       f"👤 Qo'shgan: {who}\n"
                       f"{'🛡 Admin' if is_admin else '⚠️ Admin emas'} · "
                       f"{'✉️ xabar yetkazildi' if delivered else '✉️ odam botni ochmagan'}")
    elif status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        db.set_present(ev.chat.id, 0)   # ro'yxatlardan yashiramiz
        await send_log(bot, f"⚠️ Bot <b>{esc(title)}</b> dan chiqarildi.")


# ═══════════════════════════════════════════════ 4) Tugmalar menyusi
BTN_PANEL = "⚙️ Sozlamalar"
BTN_SCAN = "🧹 Nakrutkalarni tekshirish"
BTN_STATS = "📊 Statistika"
BTN_LOG = "📜 Loglar"
BTN_PASSED = "🔍 O'tkazilganlar"
BTN_ACCOUNT = "👤 Skaner akkaunti"
BTN_HELP = "❓ Yordam"
BTN_LABELS = {BTN_PANEL, BTN_SCAN, BTN_STATS, BTN_LOG, BTN_PASSED, BTN_ACCOUNT, BTN_HELP}


def main_menu_kb() -> ReplyKeyboardMarkup:
    """Pastda doimiy turadigan tugmalar (qo'lda buyruq yozish shart emas)."""
    rows: list[list[KeyboardButton]] = []
    if config.WEBAPP_URL:
        rows.append([KeyboardButton(text="📱 Mini App", web_app=WebAppInfo(url=config.WEBAPP_URL))])
    rows.extend([
        [KeyboardButton(text=BTN_SCAN)],
        [KeyboardButton(text=BTN_PANEL), KeyboardButton(text=BTN_STATS)],
        [KeyboardButton(text=BTN_PASSED), KeyboardButton(text=BTN_LOG)],
        [KeyboardButton(text=BTN_ACCOUNT), KeyboardButton(text=BTN_HELP)],
    ])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Tugmani tanlang yoki buyruq yozing…",
    )


# ═══════════════════════════════════════════════ 5) Buyruqlar
WELCOME = (
    "🛡 <b>Nakrutka Blocker</b>\n\n"
    "Men kanal va guruhlaringizga kelayotgan nakrutka (fake/bot) "
    "akkauntlarni avtomatik aniqlab bloklayman.\n\n"
    "<b>Ishga tushirish:</b>\n"
    "1️⃣ Meni kanal/guruhga <b>admin</b> qilib qo'shing\n"
    "2️⃣ «A'zolarni bloklash» (Ban users) huquqini bering\n"
    "3️⃣ Kanalda — Sozlamalar → <b>Yangi a'zolarni tasdiqlash</b>ni yoqing "
    "(shunda fake kanalga <i>kirishidan oldin</i> rad etiladi)\n"
    "4️⃣ Pastdagi <b>tugmalardan</b> foydalaning 👇\n\n"
    "<b>Tugmalar:</b>\n"
    f"{BTN_SCAN} — kanal ichidagi <b>eski</b> nakrutkalarni tozalash\n"
    f"{BTN_PANEL} — rejim, chegara, qattiqlik\n"
    f"{BTN_STATS} — statistika · {BTN_LOG} — hodisalar\n"
    f"{BTN_PASSED} — o'tkazib yuborilganlar\n"
    f"{BTN_ACCOUNT} — tozalash uchun qaysi akkauntni admin qilish kerak\n\n"
    "<i>Qo'lda ham yozsa bo'ladi: /check (akkauntni tekshirish), /oq "
    "(oq ro'yxat), /unban, /qattiq 0-3, /id.</i>\n\n"
    "🧹 Tekshirish birinchi marta ishlatilganda bir marta "
    "<b>login.bat</b> ni ishga tushirasiz (a'zolar ro'yxatini Telegram botga bermaydi)."
)


@router.message(Command("start", "help", "yordam"))
async def cmd_start(msg: Message, command: CommandObject) -> None:
    # chuqur havola: /start scan_<chat_id>  (kanaldagi tugmadan keladi)
    arg = (command.args or "").strip()
    if arg.startswith("scan_"):
        try:
            chat_id = int(arg[5:])
        except ValueError:
            chat_id = 0
        if chat_id:
            if not await can_scan(msg.bot, chat_id, msg.from_user.id):
                await msg.answer("Bu kanalni tekshirishga ruxsatingiz yo'q. "
                                 "Botni kanalga siz admin qilgan bo'lishingiz kerak.")
                return
            st = db.settings(chat_id)
            status = await msg.answer(f"🔍 <b>{esc(st['title'])}</b> tanlandi. "
                                      "Tekshiruv boshlanmoqda...")
            await do_scan(msg.bot, chat_id, status)
            return
    await msg.answer(WELCOME, reply_markup=main_menu_kb())


@router.message(F.text.in_(BTN_LABELS))
async def on_menu_button(msg: Message) -> None:
    """Pastdagi tugmalar — mos buyruqni ishga tushiradi."""
    t = msg.text
    if t == BTN_PANEL:
        await cmd_panel(msg)
    elif t == BTN_SCAN:
        await cmd_scan(msg)
    elif t == BTN_STATS:
        await cmd_stats(msg)
    elif t == BTN_LOG:
        await cmd_log(msg)
    elif t == BTN_PASSED:
        await cmd_passed(msg)
    elif t == BTN_ACCOUNT:
        await cmd_scan_account(msg)
    elif t == BTN_HELP:
        await msg.answer(WELCOME, reply_markup=main_menu_kb())


@router.message(Command("id"))
async def cmd_id(msg: Message) -> None:
    target = msg.reply_to_message.from_user if msg.reply_to_message else msg.from_user
    await msg.answer(
        f"👤 Foydalanuvchi ID: <code>{target.id}</code>\n"
        f"💬 Chat ID: <code>{msg.chat.id}</code>"
    )


def panel_kb(st: dict) -> InlineKeyboardMarkup:
    cid = st["chat_id"]
    rows: list[list[InlineKeyboardButton]] = []
    if config.WEBAPP_URL:
        rows.append([InlineKeyboardButton(text="📱 Web App orqali boshqarish",
                                          web_app=WebAppInfo(url=config.WEBAPP_URL))])
    rows.extend([
        [InlineKeyboardButton(
            text=("🟢 Himoya YONIQ" if st["enabled"] else "🔴 Himoya O'CHIQ"),
            callback_data=f"set:toggle:0:{cid}")],
        [InlineKeyboardButton(text=f"Rejim: {MODE_LABELS[st['mode']]}",
                              callback_data=f"set:modemenu:0:{cid}")],
        [
            InlineKeyboardButton(text="➖5", callback_data=f"set:thr:-5:{cid}"),
            InlineKeyboardButton(text=f"Chegara: {st['threshold']}",
                                 callback_data=f"set:thr:0:{cid}"),
            InlineKeyboardButton(text="➕5", callback_data=f"set:thr:5:{cid}"),
        ],
        [InlineKeyboardButton(
            text=f"🔒 Qattiq qoidalar: {STRICT_LABELS[st['strict']]}",
            callback_data=f"set:strictmenu:0:{cid}")],
        [InlineKeyboardButton(text="⚡️ Tezkor sozlash (preset)",
                              callback_data=f"set:presetmenu:0:{cid}")],
        [InlineKeyboardButton(text="🧹 Eski a'zolarni tekshirish",
                              callback_data=f"scan:pick:{cid}")],
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data=f"show:stats:0:{cid}"),
            InlineKeyboardButton(text="📜 Loglar", callback_data=f"show:log:0:{cid}"),
        ],
        [InlineKeyboardButton(text="❌ Yopish", callback_data="show:close:0:0")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def panel_text(st: dict) -> str:
    return (
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"💬 Chat: <b>{esc(st['title'])}</b>\n"
        f"🆔 <code>{st['chat_id']}</code>\n"
        f"🛡 Himoya: {'yoniq' if st['enabled'] else 'o‘chiq'}\n"
        f"⚡️ Rejim: {MODE_LABELS[st['mode']]}\n"
        f"📊 Nakrutka chegarasi: <b>{st['threshold']}</b> ball\n"
        f"🔒 Qattiq qoidalar: <b>{STRICT_LABELS[st['strict']]}</b>\n\n"
        f"<i>Chegara past bo'lsa — qattiqroq tekshiradi (xato bloklash ehtimoli ortadi), "
        f"baland bo'lsa — yumshoqroq. Nakrutka o'tib ketayotgan bo'lsa "
        f"/otkazilganlar buyrug'i bilan ularning ballini ko'ring.</i>"
    )


@router.message(Command("app", "webapp", "miniapp"))
async def cmd_webapp(msg: Message) -> None:
    if not config.WEBAPP_URL:
        await msg.answer(
            "ℹ️ <b>Web App manzili (WEBAPP_URL) ulanmagan.</b>\n\n"
            "Web App ishlashi uchun <code>.env</code> faylida <code>WEBAPP_URL</code> sozlamasini ko'rsating "
            "(masalan Cloudflare Tunnel orqali olingan HTTPS havola).\n\n"
            f"Lokal server porti: <code>{config.WEBAPP_PORT}</code>",
            reply_markup=main_menu_kb()
        )
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Web App'ni ochish", web_app=WebAppInfo(url=config.WEBAPP_URL))]
    ])
    await msg.answer(
        "📱 <b>Nakrutka Blocker Web App</b>\n\n"
        "Kanallaringizni qulay vizual interfeys orqali boshqaring, "
        "nakrutkalarni tozalang va loglarni kuzatib boring.",
        reply_markup=kb
    )


@router.message(Command("panel", "sozlamalar"))
async def cmd_panel(msg: Message) -> None:
    bot = msg.bot
    if msg.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await is_chat_admin(bot, msg.chat.id, msg.from_user.id):
            return
        db.register_chat(msg.chat.id, msg.chat.title or "", msg.chat.type)
        st = db.settings(msg.chat.id)
        await msg.answer(panel_text(st), reply_markup=panel_kb(st))
        return

    # faqat shu odam BOSHQARA oladigan kanallar: ega yoki botni o'zi qo'shgan
    # (xizmat rejimida kanal adminlari ham). Boshqaning kanali ko'rinmaydi.
    allowed = [c for c in db.all_chats(present_only=True)
               if await can_scan(bot, c["chat_id"], msg.from_user.id)]
    if not allowed:
        await msg.answer(
            "🤔 Sizga biriktirilgan kanal/guruh topilmadi.\n\n"
            "Meni kanalingizga admin qilib qo'shing, keyin qayta /panel yuboring."
        )
        return
    rows = [[InlineKeyboardButton(text=f"💬 {c['title']}",
                                  callback_data=f"show:panel:0:{c['chat_id']}")]
            for c in allowed[:25]]
    await msg.answer("Qaysi chatni sozlaymiz?",
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


# ═══════════════════════════════════════════════ ADMIN PANEL (faqat ega)
def admin_dashboard_text() -> str:
    present = db.all_chats(present_only=True)
    custs = [c for c in db.customers() if c[0] not in config.ADMIN_IDS]
    s = db.stats()
    acc = scan_core.account_label() if scan_core.ACCOUNT.get("id") else "ulanmagan"
    scan_state = ("✅ " + esc(acc)) if scan_core.ACCOUNT.get("id") \
        else "⚠️ login kerak (login.bat)"
    return (
        "🛠 <b>Admin panel</b>\n\n"
        f"💬 Faol kanal/guruh: <b>{len(present)}</b>\n"
        f"👥 Mijozlar (qo'shganlar): <b>{len(custs)}</b>\n"
        f"🚫 Jami bloklangan: <b>{s['blocked']}</b> (bugun: {s['blocked_today']})\n"
        f"✅ O'tkazilgan: <b>{s['passed']}</b>\n"
        f"🔍 Jami tekshirilgan: <b>{s['total']}</b>\n"
        + (f"❗️ Bajarilmagan chora: <b>{s['failed']}</b>\n" if s.get("failed") else "")
        + f"👤 Skaner akkaunti: {scan_state}"
    )


def admin_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if config.WEBAPP_URL:
        rows.append([InlineKeyboardButton(text="👑 Admin Web App'ni ochish",
                                          web_app=WebAppInfo(url=f"{config.WEBAPP_URL}/admin.html"))])
    rows.extend([
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="adm:chats:0"),
         InlineKeyboardButton(text="👥 Mijozlar", callback_data="adm:custs:0")],
        [InlineKeyboardButton(text="📢 Mijozlarga xabar", callback_data="adm:bc:0")],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="adm:refresh:0"),
         InlineKeyboardButton(text="❌ Yopish", callback_data="adm:close:0")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin_app", "adminapp"))
async def cmd_admin_app(msg: Message) -> None:
    if not is_owner(msg.from_user.id):
        await msg.answer("🔒 Bu buyruq faqat bot adminlari uchun.")
        return
    if not config.WEBAPP_URL:
        await msg.answer(
            "ℹ️ <b>WEBAPP_URL ulanmagan.</b>\n"
            "Admin Web App ochilishi uchun <code>.env</code> faylida <code>WEBAPP_URL</code> ni ko'rsating.",
            reply_markup=main_menu_kb()
        )
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👑 Admin Web App'ni ochish",
                             web_app=WebAppInfo(url=f"{config.WEBAPP_URL}/admin.html"))
    ]])
    await msg.answer(
        "👑 <b>Nakrutka Blocker — Bosh Admin Web App</b>\n\n"
        "Barcha kanallar, mijozlar, statistika va tizim sozlamalarini boshqarish uchun pastdagi tugmani bosing:",
        reply_markup=kb
    )


@router.message(Command("admin", "boshqaruv"))
async def cmd_admin(msg: Message) -> None:
    if not is_owner(msg.from_user.id):
        await msg.answer("🔒 Admin panel faqat bot egasi uchun.")
        return
    await msg.answer(admin_dashboard_text(), reply_markup=admin_kb())


@router.callback_query(F.data.startswith("adm:"))
async def cb_admin(cq: CallbackQuery) -> None:
    if not is_owner(cq.from_user.id):
        await cq.answer("Faqat bot egasi uchun", show_alert=True)
        return
    _, key, _val = cq.data.split(":")
    edit = cq.message.edit_text if (cq.message is not None
                                    and hasattr(cq.message, "edit_text")) else None

    if key == "close":
        await cq.answer()
        if cq.message is not None:
            await safe(cq.message.delete)
        return

    if key in ("refresh",):
        await cq.answer("Yangilandi")
        if edit:
            await safe(edit, admin_dashboard_text(), reply_markup=admin_kb())
        return

    back = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm:refresh:0")]])

    if key == "chats":
        present = db.all_chats(present_only=True)
        counts = db.block_counts()
        if not present:
            await cq.answer("Kanal yo'q", show_alert=True)
            return
        lines = ["📋 <b>Kanallar</b>\n"]
        for c in present[:40]:
            cid = c["chat_id"]
            lines.append(
                f"• <b>{esc(c.get('title') or str(cid))}</b> — "
                f"🚫 {counts.get(cid, 0)}\n"
                f"   qo'shgan: {esc(c.get('added_by_name') or '—')} · "
                f"<code>{cid}</code>")
        await cq.answer()
        if edit:
            await safe(edit, "\n".join(lines), reply_markup=back)
        return

    if key == "custs":
        custs = [c for c in db.customers() if c[0] not in config.ADMIN_IDS]
        if not custs:
            await cq.answer("Hali mijoz yo'q", show_alert=True)
            return
        lines = ["👥 <b>Mijozlar</b> (botni qo'shganlar)\n"]
        for uid, name in custs[:50]:
            lines.append(f"• {esc(name or 'Nomsiz')} · <code>{uid}</code>")
        await cq.answer()
        if edit:
            await safe(edit, "\n".join(lines), reply_markup=back)
        return

    if key == "bc":
        await cq.answer()
        if edit:
            await safe(edit,
                       "📢 <b>Mijozlarga xabar yuborish</b>\n\n"
                       "Barcha mijozlarga (botni qo'shganlarga) xabar yuborish uchun:\n"
                       "<code>/xabar Sizning matningiz</code>\n\n"
                       "<i>Faqat botni oldin ochgan mijozlarga yetib boradi.</i>",
                       reply_markup=back)
        return


@router.message(Command("xabar", "broadcast"))
async def cmd_broadcast(msg: Message, command: CommandObject) -> None:
    if not is_owner(msg.from_user.id):
        return
    text = (command.args or "").strip()
    if not text:
        await msg.answer("Foydalanish: <code>/xabar Yubormoqchi bo'lgan matningiz</code>")
        return
    targets = {uid for uid, _ in db.customers() if uid not in config.ADMIN_IDS}
    if not targets:
        await msg.answer("Hali mijoz yo'q.")
        return
    sent = failed = 0
    note = await msg.answer(f"📢 {len(targets)} ta mijozga yuborilmoqda...")
    for uid in targets:
        ok = await safe(msg.bot.send_message, uid,
                        f"📢 <b>Xabar</b>\n\n{esc(text)}")
        if ok is None:
            failed += 1
        else:
            sent += 1
        await asyncio.sleep(0.1)
    result = (f"✅ Yuborildi: <b>{sent}</b>\n"
              + (f"❌ Yetmadi (botni ochmagan): {failed}" if failed else ""))
    if note is not None and hasattr(note, "edit_text"):
        await safe(note.edit_text, result)
    else:
        await msg.answer(result)


@router.message(Command("stats", "statistika"))
async def cmd_stats(msg: Message) -> None:
    if msg.chat.type != ChatType.PRIVATE:
        s = db.stats(msg.chat.id)
        scope_note = ""
    else:
        # shaxsiy chatda — faqat shu odamning kanallari
        if is_owner(msg.from_user.id):
            s = db.stats()                      # ega -> hamma kanal
            scope_note = "\n\n<i>Barcha kanallar bo'yicha (bot egasi).</i>"
        else:
            ids = await my_chat_ids(msg.bot, msg.from_user.id)
            if not ids:
                await msg.answer("Sizga biriktirilgan kanal topilmadi. "
                                 "Botni kanalingizga admin qilib qo'shing.")
                return
            s = db.stats(chat_ids=ids)
            scope_note = f"\n\n<i>Sizning {len(ids)} ta kanalingiz bo'yicha.</i>"
    await msg.answer(
        "📊 <b>Statistika</b>\n\n"
        f"🚫 Bloklangan (jami): <b>{s['blocked']}</b>\n"
        f"📅 Bugun bloklangan: <b>{s['blocked_today']}</b>\n"
        f"✅ O'tkazilgan: <b>{s['passed']}</b>\n"
        f"🔍 Tekshirilgan: <b>{s['total']}</b>"
        + (f"\n\n❗️ <b>Bajarilmagan chora: {s['failed']}</b> — botda "
           f"«Ban Users» huquqi yo'qmi? Tekshirib ko'ring." if s["failed"] else "")
        + scope_note
    )


@router.message(Command("log", "loglar"))
async def cmd_log(msg: Message) -> None:
    if msg.chat.type != ChatType.PRIVATE:
        events = db.last_events(msg.chat.id, 10)
    elif is_owner(msg.from_user.id):
        events = db.last_events(None, 10)
    else:
        ids = await my_chat_ids(msg.bot, msg.from_user.id)
        events = db.last_events(limit=10, chat_ids=ids) if ids else []
    if not events:
        await msg.answer("📜 Hozircha hodisa yo'q.")
        return
    lines = ["📜 <b>Oxirgi hodisalar</b>\n"]
    for e in events:
        icon = {"ban": "🚫", "kick": "👋", "mute": "🔇", "decline": "⛔️",
                "report": "📝", "pass": "✅", "approve": "✅"}.get(e["action"], "•")
        when = time.strftime("%d.%m %H:%M", time.localtime(e["ts"]))
        lines.append(f"{icon} {when} · {esc(e['name'])} · {e['score']} ball")
    await msg.answer("\n".join(lines))


@router.message(Command("otkazilganlar", "passed"))
async def cmd_passed(msg: Message) -> None:
    """O'tkazib yuborilganlar — chegarani to'g'ri sozlash uchun."""
    if msg.chat.type != ChatType.PRIVATE:
        events = db.last_passed(msg.chat.id, 15)
    elif is_owner(msg.from_user.id):
        events = db.last_passed(None, 15)
    else:
        ids = await my_chat_ids(msg.bot, msg.from_user.id)
        events = db.last_passed(limit=15, chat_ids=ids) if ids else []
    if not events:
        await msg.answer("Hozircha o'tkazib yuborilgan a'zo yo'q.")
        return
    st = db.settings(msg.chat.id)
    lines = ["🔍 <b>O'tkazib yuborilganlar</b> (oxirgi 15 ta)\n"]
    for e in events:
        when = time.strftime("%d.%m %H:%M", time.localtime(e["ts"]))
        uname = f"@{e['username']}" if e["username"] else f"<code>{e['user_id']}</code>"
        lines.append(f"• <b>{e['score']}</b> ball · {when} · {esc(e['name'])} · {uname}")
    scores = [e["score"] for e in events]
    top = max(scores)
    lines.append(
        f"\nHozirgi chegara: <b>{st['threshold']}</b> ball."
        f"\nAgar bu ro'yxatdagilar nakrutka bo'lsa, chegarani "
        f"<b>{max(20, top)}</b> ga tushirsangiz ular ham bloklanadi."
        f"\n\n⚡️ Osonroq yo'l: /panel → «Tezkor sozlash» → <b>Qattiq</b> yoki <b>Temir</b>."
        f"\n<i>Diqqat: past chegara haqiqiy obunachilarni ham bloklashi mumkin.</i>")
    await msg.answer("\n".join(lines))


@router.message(Command("qattiq", "strict"))
async def cmd_strict(msg: Message, command: CommandObject) -> None:
    if msg.chat.type == ChatType.PRIVATE:
        await msg.answer("Bu buyruqni kanal/guruh ichida ishlating yoki "
                         "/panel → «Qattiq qoidalar» dan tanlang.")
        return
    if not await is_chat_admin(msg.bot, msg.chat.id, msg.from_user.id):
        return
    st = db.settings(msg.chat.id)
    arg = (command.args or "").strip()
    if arg.isdigit() and 0 <= int(arg) <= 3:
        db.set_setting(msg.chat.id, "strict", int(arg))
        await msg.answer(f"🔒 Qattiq qoidalar: <b>{STRICT_LABELS[int(arg)]}</b>")
        return
    await msg.answer(
        f"🔒 Hozirgi daraja: <b>{st['strict']} — {STRICT_LABELS[st['strict']]}</b>\n\n"
        "<code>/qattiq 0</code> — o'chiq\n"
        "<code>/qattiq 1</code> — rasm ham, username ham yo'q bo'lsa blok\n"
        "<code>/qattiq 2</code> — profil rasmi yo'q bo'lsa blok\n"
        "<code>/qattiq 3</code> — username yo'q yoki yangi akkaunt bo'lsa blok")


@router.message(Command("check", "tekshir"))
async def cmd_check(msg: Message, command: CommandObject) -> None:
    bot = msg.bot
    target: User | None = reply_user(msg)
    user_id: int | None = target.id if target else None
    if command.args:
        arg = command.args.strip().lstrip("@")
        if arg.isdigit():
            user_id = int(arg)
            target = None
        else:
            await msg.answer("Username bo'yicha tekshirish Bot API'da mumkin emas. "
                             "Odamning xabarini reply qiling yoki ID yuboring.")
            return
    if user_id is None:
        await msg.answer(
            "Foydalanish:\n"
            "• <code>/check 123456789</code>\n"
            "• yoki tekshiriladigan odamning xabariga reply qilib /check")
        return

    if target is None:
        try:
            info = await bot.get_chat(user_id)
        except TelegramAPIError:
            await msg.answer("❌ Bu foydalanuvchini topa olmadim "
                             "(bot u bilan hech qachon to'qnashmagan).")
            return
        cand = Candidate(
            user_id=user_id,
            first_name=getattr(info, "first_name", None),
            last_name=getattr(info, "last_name", None),
            username=getattr(info, "username", None),
            has_photo=info.photo is not None,
            bio=getattr(info, "bio", None),
            check_language=False,
        )
        name = " ".join(filter(None, [cand.first_name or "", cand.last_name or ""])) or str(user_id)
    else:
        has_photo, bio = await fetch_profile(bot, user_id)
        cand = Candidate(
            user_id=user_id,
            first_name=target.first_name,
            last_name=target.last_name,
            username=target.username,
            language_code=target.language_code,
            is_bot=bool(target.is_bot),
            is_premium=bool(target.is_premium),
            has_photo=has_photo,
            bio=bio,
        )
        name = target.full_name

    st = db.settings(msg.chat.id)
    v = analyze(cand, threshold=st["threshold"],
                new_account_id=config.NEW_ACCOUNT_ID,
                very_new_account_id=config.VERY_NEW_ACCOUNT_ID,
                old_account_id=config.OLD_ACCOUNT_ID,
                burst_limit=config.BURST_LIMIT,
                strict_level=st["strict"])
    labels = {"fake": "Nakrutka ehtimoli YUQORI", "suspicious": "Shubhali",
              "clean": "Tirik odamga o'xshaydi"}
    await msg.answer(
        f"{v.emoji} <b>{labels[v.level]}</b>\n\n"
        f"👤 {user_link(user_id, name)}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"📊 Ball: <b>{v.score}</b>/{v.threshold}\n\n"
        f"<b>Sabablar:</b>\n{esc(v.report())}"
    )


@router.message(Command("oq", "whitelist"))
async def cmd_whitelist(msg: Message, command: CommandObject) -> None:
    if msg.chat.type == ChatType.PRIVATE and msg.from_user.id not in config.ADMIN_IDS:
        return
    if msg.chat.type != ChatType.PRIVATE and \
            not await is_chat_admin(msg.bot, msg.chat.id, msg.from_user.id):
        return
    # shaxsiy chatda — umumiy (barcha chatlar uchun) oq ro'yxat
    scope = 0 if msg.chat.type == ChatType.PRIVATE else msg.chat.id
    target = reply_user(msg)
    uid = target.id if target else None
    if uid is None and command.args and command.args.strip().isdigit():
        uid = int(command.args.strip())
    if uid is None:
        wl = db.whitelist_list(scope)
        await msg.answer(
            "Foydalanish: <code>/oq 123456789</code> yoki xabarga reply.\n\n"
            f"Oq ro'yxatda: <b>{len(wl)}</b> ta foydalanuvchi")
        return
    db.whitelist_add(scope, uid)
    where = "barcha chatlar" if scope == 0 else "shu chat"
    await msg.answer(f"✅ <code>{uid}</code> oq ro'yxatga qo'shildi ({where}) — "
                     "bu akkaunt endi bloklanmaydi.")


@router.message(Command("unban", "blokdan"))
async def cmd_unban(msg: Message, command: CommandObject) -> None:
    if msg.chat.type == ChatType.PRIVATE:
        await msg.answer("Bu buyruqni kanal/guruh ichida ishlating yoki "
                         "log xabaridagi «♻️ Blokdan chiqarish» tugmasini bosing.")
        return
    if not await is_chat_admin(msg.bot, msg.chat.id, msg.from_user.id):
        return
    if not (command.args and command.args.strip().isdigit()):
        await msg.answer("Foydalanish: <code>/unban 123456789</code>")
        return
    uid = int(command.args.strip())
    await safe(msg.bot.unban_chat_member, msg.chat.id, uid, only_if_banned=True)
    await msg.answer(f"♻️ <code>{uid}</code> blokdan chiqarildi.")


# ═══════════════════════════════════ 4.1) Eski a'zolarni skanerlash
# Telethon (foydalanuvchi akkaunti) a'zolar ro'yxatini FAQAT O'QIYDI,
# bloklashni esa bot o'zi (Bot API orqali) bajaradi.
_scan_lock = asyncio.Lock()
PENDING: dict[int, dict] = {}        # chat_id -> {"rows": [...], "ts": ..., "title": ...}


SCAN_DENIED = (
    "🔒 <b>Bu buyruq faqat bot egasi uchun.</b>\n\n"
    "Eski a'zolarni tekshirish bot emas, <b>bot egasining Telegram akkaunti</b> "
    "orqali amalga oshiriladi (Telegram a'zolar ro'yxatini botga bermaydi). "
    "Shuning uchun uni faqat egasi ishlatadi.\n\n"
    "Yangi kelayotgan nakrutkalardan himoya esa oddiy ishlaydi — hech kimga "
    "akkaunt ulash kerak emas.\n\n"
    "O'z kanalingizni tozalamoqchi bo'lsangiz — /skaner_akkaunt buyrug'iga qarang."
)


@router.message(Command("skaner_akkaunt", "scanaccount"))
async def cmd_scan_account(msg: Message) -> None:
    """Kanalga admin qilib qo'shish kerak bo'lgan skaner akkauntini ko'rsatadi."""
    if msg.chat.type != ChatType.PRIVATE and \
            not await is_chat_admin(msg.bot, msg.chat.id, msg.from_user.id):
        return
    client, err = await scan_core.connect_client()
    if client is None:
        await msg.answer(f"❌ Skaner hozir ulanmagan.\n\n{err}")
        return
    try:
        acc = scan_core.account_label()
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    await msg.answer(
        "🧹 <b>Eski a'zolarni tozalash uchun</b>\n\n"
        f"Skaner akkaunti: <b>{esc(acc)}</b>\n\n"
        "Kanalingizni tozalash kerak bo'lsa:\n"
        f"1️⃣ Kanal → Administrators → Add Admin → <b>{esc(acc)}</b>\n"
        "2️⃣ «A'zolarni bloklash» (Ban Users) huquqini bering\n"
        "3️⃣ Shu botga /scan yuboring\n"
        "4️⃣ Tozalash tugagach uni adminlikdan olib tashlasangiz bo'ladi\n\n"
        "<i>Parol, kod yoki sessiya berish kerak emas — faqat adminlik huquqi. "
        "Telegram login kodini hech qachon hech kimga va hech qanday botga "
        "bermang.</i>")


def is_owner(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def my_chat_ids(bot: Bot, user_id: int) -> list[int]:
    """Shu foydalanuvchi ko'ra oladigan kanallar ro'yxati (ega -> hammasi)."""
    out = []
    for c in db.all_chats(present_only=True):
        if await can_scan(bot, c["chat_id"], user_id):
            out.append(c["chat_id"])
    return out


async def can_scan(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Shu foydalanuvchi shu kanalni /scan qila oladimi?

    Ruxsat beriladi agar: (1) bot egasi, YOKI (2) aynan shu botni shu kanalga
    qo'shgan odam, YOKI (3) xizmat rejimida (SCAN_ONLY_OWNER=0) kanal admini.
    Ya'ni botni o'zi taklif qilgan mijoz o'z kanalini doim tekshira oladi.
    """
    if is_owner(user_id):
        return True
    st = db.settings(chat_id)
    if st.get("added_by") and int(st["added_by"]) == user_id:
        return True
    if not config.SCAN_ONLY_OWNER and await is_chat_admin(bot, chat_id, user_id):
        return True
    return False


async def resolve_entity(client, chat_id: int):
    try:
        return await client.get_entity(chat_id)
    except Exception:  # noqa: BLE001  (sessiyada keshlanmagan bo'lsa)
        try:
            async for d in client.iter_dialogs():
                if d.id == chat_id:
                    return d.entity
        except Exception:  # noqa: BLE001
            return None
    return None


def make_admin_text() -> str:
    """Skaner akkauntini kanalda admin qilishni so'raydigan xabar."""
    acc = scan_core.account_label()
    return (
        "⚠️ <b>Kanal a'zolarini o'qiy olmayapman — admin emasman.</b>\n\n"
        "Telegram a'zolar ro'yxatini faqat kanal <b>admin</b>iga beradi. "
        f"Skaner {esc(acc)} akkaunti kanalda bor, lekin hali admin emas.\n\n"
        "<b>So'nggi qadam (bir marta, uch marta bosish):</b>\n"
        f"Kanal → Administrators → Add Admin → <b>{esc(acc)}</b> ni toping va "
        "qo'shing → «A'zolarni bloklash» (Ban Users) huquqini yoqing.\n\n"
        "Keyin /scan ni (yoki tugmani) qaytadan bosing. Tozalash tugagach "
        "adminlikdan olib tashlasangiz bo'ladi.\n\n"
        "<i>Parol, kod yoki sessiya kerak emas — faqat adminlik tugmasi.</i>")


async def try_auto_join(bot: Bot, client, chat_id: int, say) -> tuple[object | None, bool]:
    """Bot (admin) taklif havolasi yaratadi, skaner akkaunti o'sha havola orqali
    kanalga o'zi qo'shiladi.

    Qaytaradi (entity, handled). handled=True bo'lsa — xato haqida xabar allaqachon
    berilgan, chaqiruvchi boshqa narsa yozmay to'xtashi kerak.
    """
    acc = scan_core.account_label()
    await say(f"🔗 {esc(acc)} akkaunti kanalga qo'shilmoqda...")

    # 1) bot admin sifatida vaqtinchalik taklif havolasi yaratadi
    link = None
    created = await safe(bot.create_chat_invite_link, chat_id, member_limit=1)
    if created is not None:
        link = getattr(created, "invite_link", None)
    if link is None:
        link = await safe(bot.export_chat_invite_link, chat_id)
    if not link:
        await say("❌ Bot taklif havolasi yarata olmadi.\n"
                  "Botga kanalda «Havola orqali taklif qilish» (Invite via link) "
                  "huquqini bering va /scan ni qayta yuboring.")
        return None, True

    # 2) skaner akkaunti havola orqali qo'shiladi
    ok, err = await scan_core.join_chat(client, str(link))

    # 3) vaqtinchalik havolani bekor qilamiz (xavfsizlik uchun)
    revoked = getattr(created, "invite_link", None) if created is not None else None
    if revoked:
        await safe(bot.revoke_chat_invite_link, chat_id, revoked)

    if not ok:
        low = (err or "").lower()
        if "flood" in low or "too many" in low or "wait" in low:
            await say("⏳ <b>Telegram akkauntni vaqtincha chekladi</b> (qisqa vaqtda "
                      "ko'p kanalga qo'shilish). Bir oz kutib /scan ni qayta yuboring.\n"
                      f"<i>{esc((err or '')[:120])}</i>")
        else:
            await say(f"❌ Akkaunt kanalga qo'shilmadi: {esc((err or '')[:160])}")
        return None, True

    await asyncio.sleep(2)   # Telegram a'zolikni ro'yxatga olishini kutamiz
    return await resolve_entity(client, chat_id), False


def scan_kb(chat_id: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🗑 {count} ta akkauntni bloklash",
                             callback_data=f"scan:apply:{chat_id}"),
    ], [
        InlineKeyboardButton(text="❌ Bekor qilish",
                             callback_data=f"scan:cancel:{chat_id}"),
    ]])


async def do_scan(bot: Bot, chat_id: int, status: Message | None,
                  auto: bool = False, notify_chat_id: int | None = None) -> None:
    """Kanal ichidagi eski a'zolarni tekshiradi (hech kimni o'chirmaydi)."""
    st = db.settings(chat_id)
    last_notify_msg: Message | None = None

    async def say(text: str, kb=None):
        nonlocal last_notify_msg
        if status is not None:
            await safe(status.edit_text, text, reply_markup=kb)
        elif notify_chat_id:
            if last_notify_msg is not None and hasattr(last_notify_msg, "edit_text"):
                res = await safe(last_notify_msg.edit_text, text, reply_markup=kb)
                if res is not None:
                    return
            res = await safe(bot.send_message, notify_chat_id, text, reply_markup=kb)
            if isinstance(res, Message):
                last_notify_msg = res
        else:
            await send_log(bot, text, kb)

    if _scan_lock.locked():
        await say("⏳ Boshqa skaner hozir ishlayapti. Tugashini kutib qayta urinib ko'ring.")
        return

    async with _scan_lock:
        client, err = await scan_core.connect_client()
        if client is None:
            await say(f"❌ Skaner ishga tushmadi.\n\n{err}")
            return
        try:
            entity = await resolve_entity(client, chat_id)

            # Skaner akkaunti a'zo bo'lmasa — bot (admin sifatida) taklif havolasi
            # yaratadi va akkaunt o'sha havola orqali O'ZI qo'shiladi.
            if entity is None and config.AUTO_JOIN:
                entity, handled = await try_auto_join(bot, client, chat_id, say)
                if handled:
                    return

            if entity is None:
                await say(make_admin_text())
                return
            title = getattr(entity, "title", st["title"])
            await say(f"🔍 <b>{esc(title)}</b> tekshirilmoqda...\n"
                      f"<i>Chegara {st['threshold']} ball, qattiqlik {st['strict']}. "
                      f"Katta kanalda bu bir necha daqiqa olishi mumkin.</i>")

            async def progress(checked: int, found: int):
                await say(f"🔍 <b>{esc(title)}</b> tekshirilmoqda...\n\n"
                          f"Ko'rildi: <b>{checked}</b>\n"
                          f"Nakrutka topildi: <b>{found}</b>")

            res = await scan_core.scan_members(
                client, entity,
                threshold=st["threshold"],
                strict_level=st["strict"],
                remove=None,                      # o'chirishni bot keyin bajaradi
                progress=progress,
                progress_every=400,
                skip_ids=set(db.whitelist_list(chat_id)),
            )
        except Exception as e:  # noqa: BLE001
            if scan_core.is_admin_required(e):
                # akkaunt a'zo, lekin admin emas — tushunarli yo'riqnoma
                await say(make_admin_text())
                return
            log.exception("skaner xatosi")
            await say(f"❌ Skaner xatosi: {esc(str(e))}")
            return
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    text = scan_core.report_text(title, res, st["threshold"], st["strict"])
    if not res.fakes:
        await say(text + "\n\n✅ Tozalash kerak bo'lgan akkaunt topilmadi.")
        return

    PENDING[chat_id] = {"rows": res.fakes, "ts": time.time(), "title": title}
    hint = ("\n\n⚠️ <b>Hali hech kim o'chirilmadi.</b> Ro'yxatni (CSV) ko'rib chiqing, "
            "so'ng pastdagi tugmani bosing.")
    await say(text + hint, scan_kb(chat_id, len(res.fakes)))

    # CSV hisobotni yuborish — tekshirishni boshlagan odamga va bot egasiga
    try:
        stamp = time.strftime("%Y%m%d_%H%M")
        path = config.BASE_DIR / f"hisobot_{abs(chat_id)}_{stamp}.csv"
        res.write_csv(path)
        targets = list(log_targets())
        # tekshirishni shaxsiy chatda boshlagan odam (egadan boshqa bo'lsa ham)
        if status is not None and getattr(status.chat, "type", "") == ChatType.PRIVATE:
            if status.chat.id not in targets:
                targets.append(status.chat.id)
        if notify_chat_id and notify_chat_id not in targets:
            targets.append(notify_chat_id)
        for target in targets:
            await safe(bot.send_document, target, FSInputFile(str(path)),
                       caption=f"📄 To'liq hisobot — {esc(title)} ({len(res.fakes)} ta)")
    except Exception as e:  # noqa: BLE001
        log.warning("CSV yuborilmadi: %s", e)

    if auto and config.AUTO_SCAN_APPLY:
        await apply_scan(bot, chat_id, None)


async def apply_scan(bot: Bot, chat_id: int, cq: CallbackQuery | None = None) -> None:
    """Skaner topgan akkauntlarni bot o'zi bloklaydi."""
    data = PENDING.pop(chat_id, None)
    if not data:
        if cq:
            await cq.answer("Ro'yxat eskirgan — /scan ni qaytadan ishlating.",
                            show_alert=True)
        return
    rows = data["rows"]
    st = db.settings(chat_id)
    done = failed = 0
    for r in rows:
        ok = await safe(bot.ban_chat_member, chat_id, int(r["id"]))
        if ok is None:
            failed += 1
        else:
            done += 1
            db.log_event(chat_id, int(r["id"]), r["ism"], r["username"] or None,
                         int(r["ball"]), ["Skaner: eski nakrutka"], "ban")
        await asyncio.sleep(0.4)

    text = (f"🧹 <b>Tozalash tugadi</b> — {esc(data['title'])}\n\n"
            f"Bloklandi: <b>{done}</b>\n"
            + (f"Bloklanmadi: {failed}{RIGHTS_WARNING}" if failed else ""))
    if cq and cq.message is not None and hasattr(cq.message, "edit_text"):
        await safe(cq.message.edit_text, text)
    else:
        await send_log(bot, text)
    log.info("Skaner tozalashi: %s bloklandi, %s xato (chat %s)", done, failed, chat_id)
    _ = st


@router.message(Command("scan", "skaner", "tozalash"))
async def cmd_scan(msg: Message) -> None:
    bot = msg.bot
    uid = msg.from_user.id

    if msg.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if await can_scan(bot, msg.chat.id, uid):
            db.register_chat(msg.chat.id, msg.chat.title or "", msg.chat.type)
            status = await msg.answer("🔍 Skaner ishga tushirilmoqda...")
            await do_scan(bot, msg.chat.id, status)
            return
        # nega bo'lmadi — tushuntiramiz (jim qolmaymiz)
        if config.SCAN_ONLY_OWNER and not is_owner(uid) and \
                await is_chat_admin(bot, msg.chat.id, uid):
            await msg.answer(SCAN_DENIED)
        else:
            await msg.answer("🔒 Bu buyruq faqat shu guruh/kanal adminlari uchun.")
        return

    # shaxsiy chat: shu odam tekshira oladigan kanallar ro'yxati
    chats = [c for c in db.all_chats(present_only=True)
             if await can_scan(bot, c["chat_id"], uid)]
    if not chats:
        if config.SCAN_ONLY_OWNER and not is_owner(uid):
            await msg.answer(SCAN_DENIED)
        else:
            await msg.answer("Sizga biriktirilgan kanal topilmadi.\n"
                             "Botni kanalingizga admin qilib qo'shing, keyin "
                             "qaytadan /scan yuboring.")
        return
    rows = [[InlineKeyboardButton(text=f"🔍 {c['title']}",
                                  callback_data=f"scan:pick:{c['chat_id']}")]
            for c in chats[:25]]
    await msg.answer(
        "🧹 <b>Eski a'zolarni tekshirish</b>\n\n"
        "Qaysi kanalni tekshiraman? Avval faqat <b>ro'yxat</b> chiqadi — "
        "hech kim o'chirilmaydi, siz ko'rib chiqib tasdiqlaysiz.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.channel_post(Command("scan", "skaner", "tozalash", "panel", "start"))
async def cmd_in_channel(msg: Message) -> None:
    """Kanal ICHIGA yozilgan buyruq. Telegram botga kanaldagi buyruqlarni
    odatdagidek yetkazmaydi — shuning uchun botga shaxsiy yozishni so'raymiz."""
    await safe(msg.answer,
               "ℹ️ Buyruqlarni shu yerga (kanalga) emas, <b>botga shaxsiy</b> yozing.\n"
               "Botni oching → /scan yuboring → ro'yxatdan kanalni tanlang.")


@router.callback_query(F.data.startswith("scan:"))
async def cb_scan(cq: CallbackQuery) -> None:
    _, action, chat_id_s = cq.data.split(":")
    chat_id = int(chat_id_s)
    if not await can_scan(cq.bot, chat_id, cq.from_user.id):
        await cq.answer("Bu kanalni tekshirishga ruxsatingiz yo'q. "
                        "Botni kanalga siz admin qilgan bo'lishingiz kerak.",
                        show_alert=True)
        return

    if action == "cancel":
        PENDING.pop(chat_id, None)
        await cq.answer("Bekor qilindi")
        if cq.message is not None and hasattr(cq.message, "edit_text"):
            await safe(cq.message.edit_text,
                       "❌ Tozalash bekor qilindi — hech kim o'chirilmadi.")
        return

    if action == "pick":
        await cq.answer()
        status = cq.message if (cq.message is not None
                                and hasattr(cq.message, "edit_text")) else None
        if status is not None:
            await safe(status.edit_text, "🔍 Skaner ishga tushirilmoqda...")
        await do_scan(cq.bot, chat_id, status)
        return

    if action == "apply":
        count = len(PENDING.get(chat_id, {}).get("rows", []))
        await cq.answer(f"{count} ta akkaunt bloklanmoqda..." if count else "Ro'yxat bo'sh")
        await apply_scan(cq.bot, chat_id, cq)


# ═══════════════════════════════════════════════ 5) Tugmalar
@router.callback_query(F.data.startswith("act:"))
async def cb_action(cq: CallbackQuery) -> None:
    _, action, chat_id_s, user_id_s = cq.data.split(":")
    chat_id, user_id = int(chat_id_s), int(user_id_s)
    if not await is_chat_admin(cq.bot, chat_id, cq.from_user.id):
        await cq.answer("Faqat adminlar uchun", show_alert=True)
        return

    if action == "ban":
        await safe(cq.bot.ban_chat_member, chat_id, user_id)
        db.log_event(chat_id, user_id, "", None, 100, ["Admin qo'lda bloklagan"], "ban")
        note = "🚫 Bloklandi"
    elif action == "unban":
        await safe(cq.bot.unban_chat_member, chat_id, user_id, only_if_banned=True)
        db.log_event(chat_id, user_id, "", None, 0, ["Admin blokdan chiqargan"], "pass")
        note = "♻️ Blokdan chiqarildi"
    else:  # white
        db.whitelist_add(chat_id, user_id)
        await safe(cq.bot.unban_chat_member, chat_id, user_id, only_if_banned=True)
        db.log_event(chat_id, user_id, "", None, 0, ["Admin oq ro'yxatga qo'shgan"], "pass")
        note = "✅ Oq ro'yxatga qo'shildi"

    await cq.answer(note)
    old = getattr(cq.message, "html_text", None) if cq.message else None
    if old:
        try:
            await safe(cq.message.edit_text, f"{old}\n\n<b>➡️ {note}</b> (admin: {esc(cq.from_user.full_name)})")
        except Exception as e:  # noqa: BLE001  (eski xabarni tahrirlash imkonsiz)
            log.debug("log xabari tahrirlanmadi: %s", e)


@router.callback_query(F.data.startswith(("set:", "show:")))
async def cb_panel(cq: CallbackQuery) -> None:
    kind, key, value, chat_id_s = cq.data.split(":")
    chat_id = int(chat_id_s)

    if key == "close":
        await cq.answer()
        if cq.message:
            await safe(cq.message.delete)
        return

    in_group = cq.message is not None and \
        getattr(cq.message.chat, "type", "") in (ChatType.GROUP, ChatType.SUPERGROUP)
    if in_group:
        ok_perm = await is_chat_admin(cq.bot, chat_id, cq.from_user.id)
    else:
        ok_perm = await can_scan(cq.bot, chat_id, cq.from_user.id)
    if not ok_perm:
        await cq.answer("Bu kanalni boshqarishga ruxsatingiz yo'q.", show_alert=True)
        return

    st = db.settings(chat_id)

    if kind == "set":
        if key == "toggle":
            db.set_setting(chat_id, "enabled", 0 if st["enabled"] else 1)
            await cq.answer("Himoya o'chirildi" if st["enabled"] else "Himoya yoqildi")
        elif key == "thr":
            delta = int(value)
            if delta:
                new = max(20, min(90, st["threshold"] + delta))
                db.set_setting(chat_id, "threshold", new)
                await cq.answer(f"Chegara: {new}")
            else:
                await cq.answer("➖/➕ bilan o'zgartiring")
        elif key == "modemenu":
            rows = [[InlineKeyboardButton(text=label,
                                          callback_data=f"set:mode:{m}:{chat_id}")]
                    for m, label in MODE_LABELS.items()]
            rows.append([InlineKeyboardButton(text="⬅️ Orqaga",
                                              callback_data=f"show:panel:0:{chat_id}")])
            await cq.answer()
            if cq.message is not None and hasattr(cq.message, "edit_text"):
                await safe(cq.message.edit_text, "⚡️ <b>Rejimni tanlang</b>\n\n"
                    "🚫 <b>Ban</b> — butunlay bloklaydi (tavsiya etiladi)\n"
                    "👋 <b>Kick</b> — chiqaradi, qayta kirishi mumkin\n"
                    "🔇 <b>Mute</b> — guruhda ovozini o'chiradi\n"
                    "📝 <b>Report</b> — hech kimni o'chirmaydi, faqat xabar beradi",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            return
        elif key == "mode":
            if value in MODE_LABELS:
                db.set_setting(chat_id, "mode", value)
                await cq.answer(f"Rejim: {MODE_LABELS[value]}")
        elif key == "strictmenu":
            rows = [[InlineKeyboardButton(
                text=f"{'✅ ' if lvl == st['strict'] else ''}{lvl} — {label}",
                callback_data=f"set:strict:{lvl}:{chat_id}")]
                for lvl, label in STRICT_LABELS.items()]
            rows.append([InlineKeyboardButton(text="⬅️ Orqaga",
                                              callback_data=f"show:panel:0:{chat_id}")])
            await cq.answer()
            if cq.message is not None and hasattr(cq.message, "edit_text"):
                await safe(cq.message.edit_text,
                           "🔒 <b>Qattiq qoidalar</b>\n\n"
                           "Ball yetmasa ham darhol bloklaydi:\n\n"
                           "<b>0</b> — o'chiq, faqat ball tizimi\n"
                           "<b>1</b> — rasm ham, username ham yo'q bo'lsa\n"
                           "<b>2</b> — profil rasmi yo'q bo'lsa\n"
                           "<b>3</b> — username yo'q yoki akkaunt yangi bo'lsa\n\n"
                           "<i>Premium akkauntlar bu qoidalardan ozod. Daraja "
                           "oshgani sari haqiqiy odamni xato bloklash ehtimoli ham ortadi.</i>",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            return
        elif key == "strict":
            db.set_setting(chat_id, "strict", max(0, min(3, int(value))))
            await cq.answer(f"Qattiq qoidalar: {STRICT_LABELS[max(0, min(3, int(value)))]}")
        elif key == "presetmenu":
            rows = [[InlineKeyboardButton(text=f"{label}  ({thr} ball)",
                                          callback_data=f"set:preset:{name}:{chat_id}")]
                    for name, (label, thr, _s) in PRESETS.items()]
            rows.append([InlineKeyboardButton(text="⬅️ Orqaga",
                                              callback_data=f"show:panel:0:{chat_id}")])
            await cq.answer()
            if cq.message is not None and hasattr(cq.message, "edit_text"):
                await safe(cq.message.edit_text,
                           "⚡️ <b>Tezkor sozlash</b>\n\n"
                           "Chegara va qattiq qoidalarni birgalikda o'rnatadi.\n"
                           "Nakrutka o'tib ketayotgan bo'lsa — pastdagilardan tanlang.\n\n"
                           "<i>Pastga tushgan sari haqiqiy obunachini xato "
                           "bloklash ehtimoli ortadi — «Temir» va «Maksimal»ni "
                           "avval report rejimida sinab ko'ring.</i>",
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            return
        elif key == "preset":
            if value in PRESETS:
                label, thr, strict = PRESETS[value]
                db.set_setting(chat_id, "threshold", thr)
                db.set_setting(chat_id, "strict", strict)
                await cq.answer(f"{label}\nChegara {thr}, qattiqlik {strict}",
                                show_alert=True)

    elif kind == "show":
        if key == "stats":
            s = db.stats(chat_id)
            await cq.answer(
                f"Bloklangan: {s['blocked']}\nBugun: {s['blocked_today']}\n"
                f"O'tkazilgan: {s['passed']}", show_alert=True)
            return
        if key == "log":
            events = db.last_events(chat_id, 10)
            if not events:
                await cq.answer("Hodisa yo'q", show_alert=True)
                return
            text = "\n".join(
                f"{time.strftime('%d.%m %H:%M', time.localtime(e['ts']))} · "
                f"{e['action']} · {e['score']} ball · {e['name'] or e['user_id']}"
                for e in events)
            await cq.answer(text[:190], show_alert=True)
            return

    st = db.settings(chat_id)
    await cq.answer()
    if cq.message is not None and hasattr(cq.message, "edit_text"):
        try:
            await safe(cq.message.edit_text, panel_text(st), reply_markup=panel_kb(st))
        except Exception as e:  # noqa: BLE001
            log.debug("panel yangilanmadi: %s", e)


# ═══════════════════════════════════════════════ 6) Fon vazifalari
async def housekeeping() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            db.cleanup_joins()
        except Exception as e:  # noqa: BLE001
            log.warning("tozalash xatosi: %s", e)
        # eskirgan skaner ro'yxatlarini tashlash (6 soatdan keyin)
        for cid in [c for c, d in PENDING.items() if time.time() - d["ts"] > 21_600]:
            PENDING.pop(cid, None)


async def auto_scanner(bot: Bot) -> None:
    """Eski a'zolarni davriy tekshirish (AUTO_SCAN_HOURS > 0 bo'lsa)."""
    if config.AUTO_SCAN_HOURS <= 0:
        return
    await asyncio.sleep(120)   # bot to'liq ishga tushishini kutamiz
    while True:
        for c in db.all_chats(present_only=True):
            st = db.settings(c["chat_id"])
            if not st["enabled"]:
                continue
            try:
                log.info("Avtomatik skaner: %s", st["title"])
                await do_scan(bot, c["chat_id"], None, auto=True)
            except Exception as e:  # noqa: BLE001
                log.warning("avtoskaner xatosi (%s): %s", c["chat_id"], e)
            await asyncio.sleep(30)
        await asyncio.sleep(config.AUTO_SCAN_HOURS * 3600)


async def main() -> None:
    config.check()
    bot = Bot(config.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.me()
    log.info("Bot ishga tushdi: @%s (rejim: %s, chegara: %s)",
             me.username, config.MODE, config.SCORE_THRESHOLD)

    # Telegram «Menu» tugmasi uchun buyruqlar ro'yxati
    commands = [
        BotCommand(command="scan", description="🧹 Eski nakrutkalarni tekshirish"),
        BotCommand(command="panel", description="⚙️ Sozlamalar"),
        BotCommand(command="stats", description="📊 Statistika"),
        BotCommand(command="otkazilganlar", description="🔍 O'tkazib yuborilganlar"),
        BotCommand(command="log", description="📜 Oxirgi hodisalar"),
        BotCommand(command="skaner_akkaunt", description="👤 Skaner akkaunti"),
        BotCommand(command="check", description="Akkauntni tekshirish"),
        BotCommand(command="start", description="❓ Yordam / menyu"),
    ]
    if config.WEBAPP_URL:
        commands.insert(0, BotCommand(command="app", description="📱 Web App (Mini App)"))
        await safe(bot.set_chat_menu_button,
                   menu_button=MenuButtonWebApp(text="Ilova", web_app=WebAppInfo(url=config.WEBAPP_URL)))

    await safe(bot.set_my_commands, commands)

    # Web App serverini ishga tushirish (aiohttp)
    web_runner = None
    if config.WEBAPP_PORT:
        try:
            web_runner = await webapp_server.start_server(
                bot, db, config, scan_core, do_scan,
                pending_dict=PENDING, apply_scan_fn=apply_scan
            )
        except Exception as e:
            log.warning("Web App serveri ishga tushmadi: %s", e)

    # eski a'zolarni skanerlash imkoniyatini tekshiramiz
    scan_ready, scan_note = True, ""
    client, err = await scan_core.connect_client()
    if client is None:
        scan_ready = False
        scan_note = f"\n\n🧹 <b>Eski a'zolarni tozalash</b> hozir ishlamaydi:\n{err}"
        log.warning("Skaner tayyor emas: %s", err.replace("\n", " ") if err else "")
    else:
        try:
            who = await client.get_me()
            log.info("Skaner tayyor: @%s akkaunti orqali", getattr(who, "username", "?"))
        finally:
            await client.disconnect()

    hello = ("🟢 <b>Nakrutka Blocker ishga tushdi.</b>\n\n"
             "Pastdagi tugmalardan foydalaning 👇\n"
             "🛠 Butun xizmatni ko'rish: /admin"
             + ("" if scan_ready else scan_note))
    for admin in config.ADMIN_IDS:
        await safe(bot.send_message, admin, hello, reply_markup=main_menu_kb())

    asyncio.create_task(housekeeping())
    if config.AUTO_SCAN_HOURS > 0 and scan_ready:
        asyncio.create_task(auto_scanner(bot))
        log.info("Avtomatik skaner: har %s soatda", config.AUTO_SCAN_HOURS)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if web_runner:
            try:
                await web_runner.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("To'xtatildi.")
