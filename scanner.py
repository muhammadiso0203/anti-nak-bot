"""
KANAL ICHIDAGI ESKI NAKRUTKALARNI SKANER QILISH (konsol varianti)
=================================================================
Eslatma: endi buni botning o'zidan ham qilish mumkin — botga yoki
kanalga **/scan** buyrug'ini yuborsangiz bo'ladi (alohida oyna kerak emas).
Bu skript katta kanallarni konsoldan tozalash va CSV olish uchun qoldirilgan.

my.telegram.org -> API development tools -> API_ID va API_HASH ni .env ga yozing.

Misollar
--------
  python scanner.py --list                               # kanallar ro'yxati
  python scanner.py --chat @mykanal                      # faqat tekshirish (CSV)
  python scanner.py --chat @mykanal --strict 2
  python scanner.py --chat @mykanal --since 2026-11-01   # shu kundan keyin kirganlar
  python scanner.py --chat @mykanal --apply --mode ban   # topilganlarni o'chirish
  python scanner.py --chat @mykanal --deep               # bio ham tekshiriladi (sekin)
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import re
import sys
from pathlib import Path

import config
import scan_core
from scan_core import scan_members

BASE_DIR = Path(__file__).resolve().parent

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def list_chats(client) -> None:
    print("\nSizning kanal/guruhlaringiz (ADMIN — o'chirish huquqi bor):\n")
    async for dialog in client.iter_dialogs():
        if not (dialog.is_channel or dialog.is_group):
            continue
        ent = dialog.entity
        admin = "ADMIN" if getattr(ent, "creator", False) or \
            getattr(ent, "admin_rights", None) else "     "
        uname = f"@{ent.username}" if getattr(ent, "username", None) else ""
        print(f"  [{admin}] {dialog.id:>15}  {str(dialog.name)[:40]:<42} {uname}")
    print()


async def run(args: argparse.Namespace) -> int:
    client, err = await scan_core.connect_client()
    if client is None:
        print("\nXATO: " + re.sub(r"<[^>]+>", "", err or "ulanmadi"))
        if "login" in (err or ""):
            print("\nBir marta login qilish kerak: python login.py")
        return 1

    me = await client.get_me()
    print(f"Kirildi: {me.first_name} (@{me.username})")

    if args.list or not args.chat:
        await list_chats(client)
        if not args.chat:
            print("Tekshirish uchun: python scanner.py --chat @kanal_username")
            await client.disconnect()
            return 0

    target = args.chat
    if isinstance(target, str) and target.lstrip("-").isdigit():
        target = int(target)
    try:
        entity = await client.get_entity(target)
    except Exception as e:  # noqa: BLE001
        print(f"\nXATO: kanal topilmadi ({e}). --list bilan ro'yxatni ko'ring.")
        await client.disconnect()
        return 1
    title = getattr(entity, "title", str(target))

    since = None
    if args.since:
        since = dt.datetime.strptime(args.since, "%Y-%m-%d").replace(
            tzinfo=dt.timezone.utc)

    mode_label = f"O'CHIRISH ({args.mode})" if args.apply else "FAQAT TEKSHIRISH"
    print(f"\nKanal     : {title}")
    print(f"Chegara   : {args.threshold} ball | Qattiqlik: {args.strict}")
    print(f"Rejim     : {mode_label}"
          + (f" | Sana: {args.since} dan keyin" if args.since else ""))
    print("-" * 70)

    remover = None
    if args.apply:
        async def remover(user):  # noqa: F811
            name = scan_core.full_name(user) or "(ismsiz)"
            print(f"  o'chirilmoqda: {user.id} {name[:30]}")
            if args.mode == "ban":
                await client.edit_permissions(entity, user, view_messages=False)
            else:
                await client.kick_participant(entity, user)
            return True

    async def progress(checked, found):
        print(f"  ... {checked} ta tekshirildi, {found} ta nakrutka")

    res = await scan_members(
        client, entity,
        threshold=args.threshold,
        strict_level=args.strict,
        since=since,
        limit=args.limit,
        deep=args.deep,
        remove=remover,
        delay=args.delay,
        progress=progress,
        progress_every=200,
    )

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    safe_title = "".join(c for c in str(title) if c.isalnum() or c in " _-")[:30].strip()
    res.write_csv(BASE_DIR / f"hisobot_{safe_title or 'kanal'}_{stamp}.csv")

    print("-" * 70)
    print(f"Tekshirildi : {res.checked}")
    print(f"Nakrutka    : {len(res.fakes)}  ({res.percent}%)")
    print(f"Adminlar    : {res.admins} (tegilmadi)")
    if res.skipped:
        print(f"Sanadan oldin kirganlar: {res.skipped} (o'tkazib yuborildi)")
    if args.apply:
        print(f"O'chirildi  : {res.removed}")
        if res.failed:
            print(f"O'chirilmadi: {res.failed} (huquq yoki flood xatosi)")
    print(f"Hisobot     : {Path(res.csv_path).name if res.csv_path else '-'}")
    if not args.apply and res.fakes:
        print("\nCSV ni Excel'da ko'rib chiqing. Rozi bo'lsangiz shu buyruqni")
        print("qayta ishlatib oxiriga --apply qo'shing.")
    await client.disconnect()
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Kanal ichidagi nakrutkalarni topish")
    p.add_argument("--chat", help="@username yoki -100... ID")
    p.add_argument("--list", action="store_true", help="kanallar ro'yxatini ko'rsatish")
    p.add_argument("--threshold", type=int, default=config.SCORE_THRESHOLD,
                   help="nakrutka chegarasi (default: .env dan)")
    p.add_argument("--strict", type=int, choices=[0, 1, 2, 3],
                   default=config.STRICT_LEVEL,
                   help="qattiq qoidalar: 1=rasm+username yo'q, 2=rasm yo'q, 3=maksimal")
    p.add_argument("--apply", action="store_true", help="topilganlarni haqiqatan o'chirish")
    p.add_argument("--mode", choices=["ban", "kick"], default="ban")
    p.add_argument("--since", help="YYYY-MM-DD: shu sanadan keyin kirganlar")
    p.add_argument("--limit", type=int, default=None, help="maksimal a'zo soni")
    p.add_argument("--deep", action="store_true", help="bio ham tekshiriladi (sekin)")
    p.add_argument("--delay", type=float, default=1.0, help="o'chirishlar orasidagi pauza")
    args = p.parse_args()

    if args.apply:
        print("\n!!! DIQQAT: topilgan akkauntlar kanaldan O'CHIRILADI.")
        print("Avval --apply BERMASDAN ishlatib, CSV hisobotni ko'rib chiqing.")
        if input("Davom etamizmi? (HA deb yozing): ").strip().upper() != "HA":
            sys.exit("Bekor qilindi.")

    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
