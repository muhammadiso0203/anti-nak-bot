"""
BIR MARTALIK LOGIN
==================
Kanal ichidagi eski a'zolarni tekshirish uchun Telegram sizning
akkauntingizdan ruxsat so'raydi (botga a'zolar ro'yxatini ko'rsatmaydi).

Bu skriptni BIR MARTA ishga tushirasiz: telefon raqam + Telegramdan kelgan kod.
Keyin sessiya faylga saqlanadi va bot /scan buyrug'ini o'zi bajara oladi.

Ishga tushirish:  python login.py   (yoki login.bat)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import config

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

try:
    from telethon import TelegramClient
except ImportError:
    sys.exit("Telethon o'rnatilmagan. Buyruq: pip install telethon")


async def main() -> None:
    print("=" * 60)
    print("  TELEGRAM AKKAUNTGA BIR MARTALIK KIRISH")
    print("=" * 60)

    if not config.API_ID or not config.API_HASH:
        sys.exit(
            "\nXATO: .env faylda API_ID va API_HASH yo'q.\n\n"
            "1) https://my.telegram.org ga kiring (telefon raqamingiz bilan)\n"
            "2) «API development tools» -> ilova yarating\n"
            "3) api_id va api_hash ni .env fayliga yozing:\n"
            "     API_ID=1234567\n"
            "     API_HASH=abcdef...\n"
        )

    session = Path(config.BASE_DIR) / config.SESSION_NAME
    client = TelegramClient(str(session), config.API_ID, config.API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"\nSiz allaqachon kirgansiz: {me.first_name} (@{me.username})")
        print("Hech narsa qilish shart emas. Bot /scan ni ishlatishi mumkin.")
        await client.disconnect()
        return

    print("\nTelefon raqamingizni xalqaro formatda kiriting (masalan +998901234567)")
    print("Telegram sizga kod yuboradi — uni shu oynaga kiritasiz.\n")
    await client.disconnect()

    # start() o'zi telefon/kod/parolni so'raydi
    async with client:
        await client.start()
        me = await client.get_me()
        print(f"\nTayyor! Kirildi: {me.first_name} (@{me.username})")
        print(f"Sessiya saqlandi: {session.name}.session")
        print("\nEndi botda /scan buyrug'ini ishlatsangiz bo'ladi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBekor qilindi.")
    input("\nDavom etish uchun Enter...")
