"""Konfiguratsiya: .env faylidan sozlamalarni o'qiydi."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # .env yo'q bo'lsa jim o'tadi

VALID_MODES = ("ban", "kick", "mute", "report")


def _int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "ha", "on")


def _int_list(name: str) -> list[int]:
    raw = (os.getenv(name) or "").replace(";", ",")
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


BOT_TOKEN: str = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_IDS: list[int] = _int_list("ADMIN_IDS")
LOG_CHAT_ID: int | None = _int("LOG_CHAT_ID", 0) or None

MODE: str = (os.getenv("MODE") or "ban").strip().lower()
if MODE not in VALID_MODES:
    MODE = "ban"

SCORE_THRESHOLD: int = _int("SCORE_THRESHOLD", 50)

# Qattiq qoidalar: 0=o'chiq, 1=rasm va username yo'q, 2=rasm yo'q,
# 3=username yo'q yoki akkaunt yangi (eng qattiq). /panel dan ham o'zgartiriladi.
STRICT_LEVEL: int = max(0, min(3, _int("STRICT_LEVEL", 0)))

NEW_ACCOUNT_ID: int = _int("NEW_ACCOUNT_ID", 8_200_000_000)
VERY_NEW_ACCOUNT_ID: int = _int("VERY_NEW_ACCOUNT_ID", 8_600_000_000)
OLD_ACCOUNT_ID: int = _int("OLD_ACCOUNT_ID", 1_500_000_000)

BURST_WINDOW: int = _int("BURST_WINDOW", 60)
BURST_LIMIT: int = _int("BURST_LIMIT", 8)

AUTO_ROTATE_LINK: bool = _bool("AUTO_ROTATE_LINK", False)
PROTECT_PREMIUM: bool = _bool("PROTECT_PREMIUM", False)

# /scan (eski a'zolarni tekshirish) SIZNING akkauntingiz orqali o'qiydi.
# 1 = faqat ADMIN_IDS dagi egalar ishlatadi (tavsiya),
# 0 = kanal adminlari ham ishlatishi mumkin (xizmat rejimi).
SCAN_ONLY_OWNER: bool = _bool("SCAN_ONLY_OWNER", True)

# Skaner akkaunti kanalga a'zo bo'lmasa, bot taklif havolasi yaratib,
# akkaunt o'zi qo'shilsinmi? 1 = ha (xizmat uchun qulay), 0 = yo'q.
# DIQQAT: bitta akkaunt kuniga ko'p kanalga qo'shilsa Telegram cheklaydi.
AUTO_JOIN: bool = _bool("AUTO_JOIN", True)

# Eski a'zolarni avtomatik tekshirish: 0 = o'chiq, 24 = kunda bir marta
AUTO_SCAN_HOURS: int = _int("AUTO_SCAN_HOURS", 0)
# 1 bo'lsa — topilganlarni so'ramasdan bloklaydi (0 = avval tasdiq so'raydi)
AUTO_SCAN_APPLY: bool = _bool("AUTO_SCAN_APPLY", False)

DB_PATH: str = str(BASE_DIR / (os.getenv("DB_PATH") or "nakrutka.db").strip())

# --- Web App (Telegram Mini App) ---
# Ilovaning HTTPS manzili (BotFather'ga ham shu kiritiladi). Bo'sh bo'lsa
# web app o'chiq. Masalan: https://abcd.trycloudflare.com
WEBAPP_URL: str = (os.getenv("WEBAPP_URL") or "").strip()
WEBAPP_PORT: int = _int("WEBAPP_PORT", 8080)

# --- scanner.py uchun ---
API_ID: int = _int("API_ID", 0)
API_HASH: str = (os.getenv("API_HASH") or "").strip()
SESSION_NAME: str = (os.getenv("SESSION_NAME") or "scanner").strip()


def check() -> None:
    """Bot ishga tushishdan oldin majburiy sozlamalarni tekshiradi."""
    problems = []
    if not BOT_TOKEN or BOT_TOKEN.startswith("123456789:AAxx"):
        problems.append("BOT_TOKEN ko'rsatilmagan (.env faylga yozing)")
    if not ADMIN_IDS:
        problems.append("ADMIN_IDS ko'rsatilmagan (kamida 1 ta admin ID kerak)")
    if problems:
        raise SystemExit(
            "\n❌ Sozlamalarda xatolik:\n  - " + "\n  - ".join(problems) +
            "\n\n.env.example faylini .env nomi bilan nusxalab to'ldiring.\n"
        )
