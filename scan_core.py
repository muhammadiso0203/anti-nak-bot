"""Kanal a'zolarini o'qib tahlil qilish — bot ham, scanner.py ham shu moduldan foydalanadi.

Telethon (sizning akkauntingiz) faqat a'zolar ro'yxatini O'QIYDI.
O'chirishni esa bot (Bot API) yoki CLI (Telethon) bajaradi — `remove` callback orqali.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import config
from detector import Candidate, analyze

try:
    from telethon import TelegramClient
    from telethon.errors import FloodWaitError, RPCError
    from telethon.tl.functions.users import GetFullUserRequest
    from telethon.tl.types import ChannelParticipantsAdmins, UserStatusOffline
    TELETHON_OK = True
except ImportError:  # telethon o'rnatilmagan bo'lsa bot ham ishlashi kerak
    TELETHON_OK = False
    TelegramClient = None  # type: ignore

    class FloodWaitError(Exception):  # type: ignore
        seconds = 1

    class RPCError(Exception):  # type: ignore
        pass

    ChannelParticipantsAdmins = object  # type: ignore
    UserStatusOffline = ()              # type: ignore
    GetFullUserRequest = None           # type: ignore

CSV_FIELDS = ["id", "ism", "username", "ball", "daraja", "kirgan_sana", "sabablar"]

# Skaner qaysi akkaunt orqali o'qiyotgani (bot ishga tushganda to'ldiriladi).
# Kanal egalariga "shu akkauntni admin qilib qo'shing" deb aytish uchun kerak.
ACCOUNT: dict = {}


def remember_account(user) -> None:
    ACCOUNT.update({
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "name": (getattr(user, "first_name", "") or "").strip(),
    })


def account_label() -> str:
    """Admin qilib qo'shish kerak bo'lgan akkaunt nomi."""
    if ACCOUNT.get("username"):
        return "@" + str(ACCOUNT["username"])
    if ACCOUNT.get("id"):
        return f"{ACCOUNT.get('name') or 'skaner akkaunti'} (ID {ACCOUNT['id']})"
    return "skaner akkaunti"


def is_admin_required(e: Exception) -> bool:
    """Xato 'kanalda admin bo'lish kerak' (CHAT_ADMIN_REQUIRED) degani mi?"""
    name = type(e).__name__.lower()
    s = str(e).lower()
    return ("adminrequired" in name
            or "chat_admin_required" in s
            or "admin privileges are required" in s
            or "admin rights" in s)


_INVITE_RE = re.compile(r"(?:t\.me/\+|t\.me/joinchat/|/\+|joinchat/)([A-Za-z0-9_\-]+)")


async def join_chat(client, link_or_username: str) -> tuple[bool, str | None]:
    """Skaner akkaunti kanalga qo'shiladi (public @username yoki taklif havolasi).

    Qaytaradi (muvaffaqiyat, xato). Allaqachon a'zo bo'lsa ham True qaytadi.
    """
    if not TELETHON_OK:
        return False, "Telethon o'rnatilmagan"
    link = (link_or_username or "").strip()
    m = _INVITE_RE.search(link)
    try:
        if m:
            from telethon.tl.functions.messages import ImportChatInviteRequest
            await client(ImportChatInviteRequest(m.group(1)))
            return True, None
        uname = link.rstrip("/").split("/")[-1].lstrip("@")
        if not uname:
            return False, "havola yoki username noto'g'ri"
        from telethon.tl.functions.channels import JoinChannelRequest
        await client(JoinChannelRequest(uname))
        return True, None
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        low = msg.lower()
        if "already" in low or "participant" in low:
            return True, None          # allaqachon a'zo — bu yaxshi
        return False, msg


# ─────────────────────────────────────────────────────────── yordamchilar
def days_since_online(user) -> int | None:
    status = getattr(user, "status", None)
    if UserStatusOffline and isinstance(status, UserStatusOffline) and status.was_online:
        now = dt.datetime.now(dt.timezone.utc)
        return max(0, (now - status.was_online).days)
    return None


def join_date(user) -> dt.datetime | None:
    part = getattr(user, "participant", None)
    return getattr(part, "date", None) if part is not None else None


def full_name(user) -> str:
    parts = [getattr(user, "first_name", "") or "", getattr(user, "last_name", "") or ""]
    return " ".join(p for p in parts if p).strip()


def to_candidate(user, bio: str | None = None) -> Candidate:
    return Candidate(
        user_id=user.id,
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        username=getattr(user, "username", None),
        is_bot=bool(getattr(user, "bot", False)),
        is_premium=bool(getattr(user, "premium", False)),
        is_deleted=bool(getattr(user, "deleted", False)),
        has_photo=getattr(user, "photo", None) is not None,
        bio=bio,
        is_scam=bool(getattr(user, "scam", False)),
        is_fake_flag=bool(getattr(user, "fake", False)),
        is_restricted=bool(getattr(user, "restricted", False)),
        days_since_online=days_since_online(user),
        check_language=False,   # Telethon'da ilova tili ko'rinmaydi
    )


# ─────────────────────────────────────────────────────────────── natija
@dataclass
class ScanResult:
    checked: int = 0
    skipped: int = 0
    removed: int = 0
    failed: int = 0
    admins: int = 0
    rows: list[dict] = field(default_factory=list)      # hammasi
    fakes: list[dict] = field(default_factory=list)     # nakrutkalar
    csv_path: str | None = None
    error: str | None = None

    @property
    def percent(self) -> int:
        return (len(self.fakes) * 100 // self.checked) if self.checked else 0

    def write_csv(self, path: str | Path) -> str:
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(sorted(self.rows, key=lambda r: -r["ball"]))
        self.csv_path = str(path)
        return self.csv_path


# ───────────────────────────────────────────────────────── ulanish
async def connect_client(session_name: str | None = None) -> tuple[object | None, str | None]:
    """Telethon klientini ULAYDI (interaktiv login QILMAYDI).

    Qaytaradi: (client, xato matni). Bot uchun: xato bo'lsa foydalanuvchiga
    tushunarli matn ko'rsatiladi, bot esa ishlashda davom etadi.
    """
    if not TELETHON_OK:
        return None, ("Telethon kutubxonasi o'rnatilmagan.\n"
                      "Buyruq: <code>pip install telethon</code>")
    if not config.API_ID or not config.API_HASH:
        return None, ("API_ID / API_HASH ko'rsatilmagan.\n"
                      "https://my.telegram.org → API development tools → "
                      "olingan qiymatlarni <code>.env</code> fayliga yozing.")
    name = session_name or config.SESSION_NAME
    path = Path(config.BASE_DIR) / name if hasattr(config, "BASE_DIR") else Path(name)
    client = TelegramClient(str(path), config.API_ID, config.API_HASH)
    try:
        await client.connect()
    except Exception as e:  # noqa: BLE001
        return None, f"Telegramga ulanmadi: {e}"
    if not await client.is_user_authorized():
        await client.disconnect()
        return None, ("Akkaunt kirmagan. Bir marta <b>login.bat</b> ni "
                      "ishga tushirib telefon raqam va kodni kiriting "
                      "(keyin qayta so'ralmaydi).")
    try:
        remember_account(await client.get_me())
    except Exception:  # noqa: BLE001
        pass
    return client, None


# ──────────────────────────────────────────────────────────── skaner
async def scan_members(
    client,
    entity,
    *,
    threshold: int = 50,
    strict_level: int = 0,
    since: dt.datetime | None = None,
    limit: int | None = None,
    deep: bool = False,
    remove=None,                 # async callable(user) -> bool | None
    delay: float = 1.0,
    progress=None,               # async callable(checked, found)
    progress_every: int = 300,
    skip_ids: set[int] | None = None,
) -> ScanResult:
    """Kanal a'zolarini tekshiradi. `remove` berilsa — topilganlarni o'chiradi."""
    res = ScanResult()
    skip = set(skip_ids or ())

    # adminlarga hech qachon tegilmaydi
    try:
        async for a in client.iter_participants(entity, filter=ChannelParticipantsAdmins):
            skip.add(a.id)
            res.admins += 1
    except RPCError:
        pass
    try:
        me = await client.get_me()
        if me is not None:
            skip.add(me.id)
    except RPCError:
        pass

    async for user in client.iter_participants(entity, limit=limit):
        if user.id in skip:
            continue
        jd = join_date(user)
        if since is not None and jd is not None and jd < since:
            res.skipped += 1
            continue

        bio = None
        if deep and not getattr(user, "deleted", False) and GetFullUserRequest:
            try:
                full = await client(GetFullUserRequest(user.id))
                bio = getattr(full.full_user, "about", None)
                await asyncio.sleep(0.4)
            except FloodWaitError as e:
                await asyncio.sleep(getattr(e, "seconds", 5) + 2)
            except RPCError:
                pass

        v = analyze(
            to_candidate(user, bio),
            threshold=threshold,
            new_account_id=config.NEW_ACCOUNT_ID,
            very_new_account_id=config.VERY_NEW_ACCOUNT_ID,
            old_account_id=config.OLD_ACCOUNT_ID,
            strict_level=strict_level,
        )
        res.checked += 1
        row = {
            "id": user.id,
            "ism": full_name(user) or "(ismsiz)",
            "username": getattr(user, "username", "") or "",
            "ball": v.score,
            "daraja": v.level,
            "kirgan_sana": jd.strftime("%Y-%m-%d") if jd else "",
            "sabablar": " | ".join(v.reasons),
        }
        res.rows.append(row)

        if v.is_fake:
            res.fakes.append(row)
            if remove is not None:
                try:
                    ok = await remove(user)
                    if ok is False:
                        res.failed += 1
                    else:
                        res.removed += 1
                    await asyncio.sleep(delay)
                except FloodWaitError as e:
                    await asyncio.sleep(getattr(e, "seconds", 5) + 2)
                    res.failed += 1
                except RPCError:
                    res.failed += 1

        if progress is not None and res.checked % progress_every == 0:
            try:
                await progress(res.checked, len(res.fakes))
            except Exception:  # noqa: BLE001  (progress xatosi skanerni to'xtatmasin)
                pass

    return res


def report_text(title: str, res: ScanResult, threshold: int, strict_level: int,
                top: int = 10) -> str:
    """Telegram uchun qisqa hisobot matni (HTML)."""
    import html as _html

    lines = [
        f"🔍 <b>Skaner tugadi</b> — {_html.escape(title)}",
        "",
        f"Tekshirildi: <b>{res.checked}</b>",
        f"Nakrutka topildi: <b>{len(res.fakes)}</b> ({res.percent}%)",
        f"Adminlar (tegilmadi): {res.admins}",
    ]
    if res.skipped:
        lines.append(f"Sana filtridan o'tmagan: {res.skipped}")
    if res.removed:
        lines.append(f"O'chirildi: <b>{res.removed}</b>")
    if res.failed:
        lines.append(f"O'chirilmadi (xato): {res.failed}")
    lines += ["", f"<i>Chegara {threshold} ball, qattiqlik {strict_level}</i>"]

    if res.fakes:
        lines += ["", f"<b>Eng yuqori balli {min(top, len(res.fakes))} ta:</b>"]
        for r in sorted(res.fakes, key=lambda x: -x["ball"])[:top]:
            uname = f"@{r['username']}" if r["username"] else f"<code>{r['id']}</code>"
            lines.append(f"• <b>{r['ball']}</b> · {_html.escape(r['ism'][:24])} · {uname}")
    return "\n".join(lines)
