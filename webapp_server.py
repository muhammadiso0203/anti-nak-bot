"""
TELEGRAM MINI APP backend (aiohttp)
===================================
Botning o'zi ichida kichik HTTP-server ishga tushadi:
- Oddiy mijozlar uchun Mini App (webapp/index.html)
- Faqat bot adminlari uchun Maxsus Admin Panel (webapp/admin.html)
- Himoyalangan JSON API lar

Xavfsizlik: har bir so'rovda Telegram yuboradigan initData HMAC-SHA256 bilan
tekshiriladi (bot token orqali). Admin API'lariga esa faqat ADMIN_IDS ro'yxatidagi
shaxslar kira oladi.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl

log = logging.getLogger("nakrutka.web")

try:
    from aiohttp import web
    AIOHTTP_OK = True
except ImportError:  # aiogram aiohttp'ni o'zi o'rnatadi, lekin ehtiyot uchun
    AIOHTTP_OK = False
    web = None  # type: ignore

BASE_DIR = Path(__file__).resolve().parent
INDEX = BASE_DIR / "webapp" / "index.html"
INDEX_ADMIN = BASE_DIR / "webapp" / "admin.html"

PRESETS = {
    "soft": {"label": "🌱 Yumshoq", "thr": 65, "strict": 0},
    "balanced": {"label": "⚖️ Muvozanatli", "thr": 50, "strict": 0},
    "hard": {"label": "⚡️ Qattiq", "thr": 42, "strict": 1},
    "iron": {"label": "🔒 Temir", "thr": 34, "strict": 2},
    "max": {"label": "🧱 Maksimal", "thr": 25, "strict": 3},
}


# ──────────────────────────────────────────── initData tekshiruvi
def verify_init_data(init_data: str, bot_token: str, max_age: int = 86_400
                     ) -> dict | None:
    """Telegram WebApp initData'sini tekshiradi. To'g'ri bo'lsa user dict qaytaradi."""
    if not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:  # noqa: BLE001
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None

    # auth_date — eskirganini rad etamiz
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        if max_age and auth_date and (time.time() - auth_date) > max_age:
            return None
    except ValueError:
        return None

    try:
        user = json.loads(pairs.get("user", "null"))
    except json.JSONDecodeError:
        user = None
    if not user or "id" not in user:
        return None
    return user


# ──────────────────────────────────────────── ruxsat yordamchisi
def _user_channels(db, user_id: int, is_owner: bool,
                   pending_dict: dict | None = None) -> list[dict]:
    counts = db.block_counts()
    out = []
    for c in db.all_chats(present_only=True):
        cid = c["chat_id"]
        mine = is_owner or (c.get("added_by") and int(c["added_by"]) == user_id)
        if not mine:
            continue
        st = db.settings(cid)
        pending_info = None
        if pending_dict and cid in pending_dict:
            p = pending_dict[cid]
            rows = p.get("rows", [])
            pending_info = {
                "count": len(rows),
                "fakes": rows[:50],  # oldindan ko'rish uchun 50 tagacha
                "title": p.get("title", ""),
                "ts": p.get("ts", 0),
            }
        out.append({
            "id": cid,
            "title": c.get("title") or str(cid),
            "type": c.get("type") or "",
            "enabled": bool(st["enabled"]),
            "mode": st["mode"],
            "threshold": st["threshold"],
            "strict": st["strict"],
            "blocked": counts.get(cid, 0),
            "added_by_name": c.get("added_by_name") or "",
            "whitelist_count": len(db.whitelist_list(cid)),
            "pending": pending_info,
        })
    return out


# ──────────────────────────────────────────── server
def build_app(bot, db, config, scan_core, do_scan,
              pending_dict: dict | None = None,
              apply_scan_fn=None):
    """aiohttp ilovasini yaratadi. do_scan — botdagi korutina (fon uchun)."""
    if not AIOHTTP_OK:
        raise RuntimeError("aiohttp o'rnatilmagan")

    MODE_LABELS = {
        "ban": "Bloklash", "kick": "Chiqarish",
        "mute": "Ovozini o'chirish", "report": "Faqat xabar",
    }

    async def with_auth(request):
        """Body (json) + initData'ni o'qib, userni qaytaradi."""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        init = request.headers.get("X-Init-Data") or body.get("initData") or ""
        user = verify_init_data(init, config.BOT_TOKEN)
        return user, body

    def is_owner(uid: int) -> bool:
        return uid in config.ADMIN_IDS

    async def with_admin(request):
        """Faqat ADMIN_IDS ro'yxatidagi shaxslar uchun tekshiruv."""
        user, body = await with_auth(request)
        if not user:
            return None, None, web.json_response({"error": "auth", "message": "Avtorizatsiya xatosi."}, status=401)
        uid = int(user["id"])
        if not is_owner(uid):
            return None, None, web.json_response({
                "error": "forbidden",
                "message": "Kirish taqiqlangan: Bu bo'lim faqat bot adminlari uchun."
            }, status=403)
        return user, body, None

    def may_manage(db_, uid, is_own, chat_id) -> bool:
        if is_own:
            return True
        st = db_.all_chats(present_only=True)
        for c in st:
            if c["chat_id"] == chat_id:
                return bool(c.get("added_by") and int(c["added_by"]) == uid)
        return False

    # ---- 1) Oddiy Web App routes ----
    async def h_index(request):
        if not INDEX.exists():
            return web.Response(text="index.html topilmadi", status=404)
        return web.FileResponse(INDEX)

    async def h_state(request):
        user, _ = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        channels = _user_channels(db, uid, owner, pending_dict=pending_dict)
        ids = [c["id"] for c in channels]
        stats = db.stats() if owner else db.stats(chat_ids=ids or [0])
        scan_ready = bool(scan_core.ACCOUNT.get("id"))
        return web.json_response({
            "user": {"id": uid, "first_name": user.get("first_name", ""),
                     "username": user.get("username", ""),
                     "photo_url": user.get("photo_url", "")},
            "is_owner": owner,
            "scan_account": scan_core.account_label() if scan_ready else "",
            "scan_ready": scan_ready,
            "channels": channels,
            "stats": stats,
            "mode_labels": MODE_LABELS,
            "presets": PRESETS,
        })

    async def h_settings(request):
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        try:
            chat_id = int(body.get("chat_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "chat_id"}, status=400)
        if not may_manage(db, uid, owner, chat_id):
            return web.json_response({"error": "forbidden"}, status=403)
        key = body.get("key")
        value = body.get("value")
        if key == "enabled":
            db.set_setting(chat_id, "enabled", 1 if value else 0)
        elif key == "mode" and value in MODE_LABELS:
            db.set_setting(chat_id, "mode", value)
        elif key == "threshold":
            db.set_setting(chat_id, "threshold", max(20, min(90, int(value))))
        elif key == "strict":
            db.set_setting(chat_id, "strict", max(0, min(3, int(value))))
        elif key == "preset" and value in PRESETS:
            p = PRESETS[value]
            db.set_setting(chat_id, "threshold", p["thr"])
            db.set_setting(chat_id, "strict", p["strict"])
        else:
            return web.json_response({"error": "key"}, status=400)
        return web.json_response({"ok": True, "settings": db.settings(chat_id)})

    async def h_scan(request):
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        try:
            chat_id = int(body.get("chat_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "chat_id"}, status=400)
        if not may_manage(db, uid, owner, chat_id):
            return web.json_response({"error": "forbidden"}, status=403)
        if not scan_core.ACCOUNT.get("id"):
            return web.json_response({"error": "login",
                                      "message": "Skaner akkaunti ulanmagan "
                                      "(login.bat)."}, status=409)
        # fon rejimida ishga tushiramiz, natija foydalanuvchining chatiga boradi
        import asyncio
        asyncio.create_task(do_scan(bot, chat_id, None, notify_chat_id=uid))
        return web.json_response({"started": True})

    async def h_scan_action(request):
        """Web App orqali topilgan botlarni bloklash yoki bekor qilish."""
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        try:
            chat_id = int(body.get("chat_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "chat_id"}, status=400)
        if not may_manage(db, uid, owner, chat_id):
            return web.json_response({"error": "forbidden"}, status=403)

        action = body.get("action")
        if action == "apply":
            if not apply_scan_fn:
                return web.json_response({"error": "apply_not_configured"}, status=500)
            import asyncio
            asyncio.create_task(apply_scan_fn(bot, chat_id, None))
            return web.json_response({"ok": True, "action": "apply"})
        elif action == "cancel":
            if pending_dict and chat_id in pending_dict:
                pending_dict.pop(chat_id, None)
            return web.json_response({"ok": True, "action": "cancel"})
        return web.json_response({"error": "unknown_action"}, status=400)

    async def h_logs(request):
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        chat_id = body.get("chat_id")
        if chat_id is not None:
            try:
                chat_id = int(chat_id)
            except (TypeError, ValueError):
                chat_id = None

        if chat_id:
            if not may_manage(db, uid, owner, chat_id):
                return web.json_response({"error": "forbidden"}, status=403)
            raw_events = db.last_events(chat_id=chat_id, limit=40)
        else:
            channels = _user_channels(db, uid, owner)
            cids = [c["id"] for c in channels]
            if not cids:
                return web.json_response({"ok": True, "events": []})
            raw_events = db.last_events(limit=40) if owner else db.last_events(chat_ids=cids, limit=40)

        out_events = []
        for e in raw_events:
            reasons = e["reasons"]
            if isinstance(reasons, str):
                try:
                    reasons = json.loads(reasons)
                except Exception:
                    reasons = [reasons]
            out_events.append({
                "id": e["id"],
                "chat_id": e["chat_id"],
                "user_id": e["user_id"],
                "name": e.get("name") or "",
                "username": e.get("username") or "",
                "score": e["score"],
                "reasons": reasons,
                "action": e["action"],
                "ts": e["ts"],
                "time_str": time.strftime("%d.%m %H:%M", time.localtime(e["ts"])),
            })
        return web.json_response({"ok": True, "events": out_events})

    async def h_whitelist(request):
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        try:
            chat_id = int(body.get("chat_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "chat_id"}, status=400)
        if not may_manage(db, uid, owner, chat_id):
            return web.json_response({"error": "forbidden"}, status=403)
        return web.json_response({"ok": True, "whitelist": db.whitelist_list(chat_id)})

    async def h_whitelist_add(request):
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        try:
            chat_id = int(body.get("chat_id"))
            target_id = int(body.get("user_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_ids"}, status=400)
        if not may_manage(db, uid, owner, chat_id):
            return web.json_response({"error": "forbidden"}, status=403)
        db.whitelist_add(chat_id, target_id)
        return web.json_response({"ok": True, "whitelist": db.whitelist_list(chat_id)})

    async def h_whitelist_remove(request):
        user, body = await with_auth(request)
        if not user:
            return web.json_response({"error": "auth"}, status=401)
        uid = int(user["id"])
        owner = is_owner(uid)
        try:
            chat_id = int(body.get("chat_id"))
            target_id = int(body.get("user_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_ids"}, status=400)
        if not may_manage(db, uid, owner, chat_id):
            return web.json_response({"error": "forbidden"}, status=403)
        db.whitelist_remove(chat_id, target_id)
        return web.json_response({"ok": True, "whitelist": db.whitelist_list(chat_id)})

    # ---- 2) MAXSUS ADMIN WEB APP ROUTES (FAQAT ADMIN UCHUN) ----
    async def h_admin_index(request):
        if not INDEX_ADMIN.exists():
            return web.Response(text="admin.html topilmadi", status=404)
        return web.FileResponse(INDEX_ADMIN)

    async def h_admin_state(request):
        """Barcha ma'lumotlar, barcha kanallar va mijozlar (faqat admin ko'radi)."""
        user, _, err = await with_admin(request)
        if err is not None:
            return err
        uid = int(user["id"])
        counts = db.block_counts()
        all_chats_raw = db.all_chats(present_only=False)
        chat_list = []
        for c in all_chats_raw:
            cid = c["chat_id"]
            st = db.settings(cid)
            chat_list.append({
                "id": cid,
                "title": c.get("title") or str(cid),
                "type": c.get("type") or "",
                "present": bool(c.get("present", 1)),
                "enabled": bool(st["enabled"]),
                "mode": st["mode"],
                "threshold": st["threshold"],
                "strict": st["strict"],
                "blocked": counts.get(cid, 0),
                "added_by": c.get("added_by"),
                "added_by_name": c.get("added_by_name") or "",
                "added_at": c.get("added_at") or 0,
                "added_at_str": time.strftime("%d.%m.%Y", time.localtime(c["added_at"])) if c.get("added_at") else "",
                "whitelist_count": len(db.whitelist_list(cid)),
            })

        customers_raw = db.customers()
        cust_list = []
        for cust_id, cust_name in customers_raw:
            ch_count = sum(1 for c in all_chats_raw if c.get("added_by") == cust_id)
            cust_list.append({
                "id": cust_id,
                "name": cust_name or str(cust_id),
                "channels_count": ch_count,
            })

        scan_ready = bool(scan_core.ACCOUNT.get("id"))
        return web.json_response({
            "admin": {
                "id": uid,
                "first_name": user.get("first_name", ""),
                "username": user.get("username", ""),
                "photo_url": user.get("photo_url", ""),
            },
            "stats": db.stats(),
            "chats": chat_list,
            "customers": cust_list,
            "scan": {
                "ready": scan_ready,
                "account": scan_core.account_label() if scan_ready else "",
            },
            "config": {
                "mode": config.MODE,
                "threshold": config.SCORE_THRESHOLD,
                "strict": config.STRICT_LEVEL,
                "burst_window": config.BURST_WINDOW,
                "burst_limit": config.BURST_LIMIT,
                "auto_scan_hours": config.AUTO_SCAN_HOURS,
                "protect_premium": config.PROTECT_PREMIUM,
                "auto_rotate_link": config.AUTO_ROTATE_LINK,
                "port": config.WEBAPP_PORT,
                "admin_ids": config.ADMIN_IDS,
            },
            "mode_labels": MODE_LABELS,
            "presets": PRESETS,
        })

    async def h_admin_chat_settings(request):
        """Admin istalgan kanalning sozlamasini o'zgartira oladi."""
        user, body, err = await with_admin(request)
        if err is not None:
            return err
        try:
            chat_id = int(body.get("chat_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "chat_id"}, status=400)
        key = body.get("key")
        value = body.get("value")
        if key == "enabled":
            db.set_setting(chat_id, "enabled", 1 if value else 0)
        elif key == "mode" and value in MODE_LABELS:
            db.set_setting(chat_id, "mode", value)
        elif key == "threshold":
            db.set_setting(chat_id, "threshold", max(20, min(90, int(value))))
        elif key == "strict":
            db.set_setting(chat_id, "strict", max(0, min(3, int(value))))
        elif key == "preset" and value in PRESETS:
            p = PRESETS[value]
            db.set_setting(chat_id, "threshold", p["thr"])
            db.set_setting(chat_id, "strict", p["strict"])
        else:
            return web.json_response({"error": "key"}, status=400)
        return web.json_response({"ok": True, "settings": db.settings(chat_id)})

    async def h_admin_remove_chat(request):
        """Admin kanalni bazadan to'liq o'chiradi."""
        user, body, err = await with_admin(request)
        if err is not None:
            return err
        try:
            chat_id = int(body.get("chat_id"))
        except (TypeError, ValueError):
            return web.json_response({"error": "chat_id"}, status=400)
        db.remove_chat(chat_id)
        return web.json_response({"ok": True, "removed": chat_id})

    async def h_admin_broadcast(request):
        """Admin barcha mijozlarga xabarnoma yuboradi."""
        user, body, err = await with_admin(request)
        if err is not None:
            return err
        text = (body.get("text") or "").strip()
        if not text:
            return web.json_response({"error": "empty_text"}, status=400)
        import asyncio
        customers = db.customers()
        sent = failed = 0
        for cust_id, _ in customers:
            try:
                if bot:
                    await bot.send_message(cust_id, text)
                    sent += 1
                    await asyncio.sleep(0.08)
                else:
                    sent += 1
            except Exception:
                failed += 1
        return web.json_response({"ok": True, "sent": sent, "failed": failed})

    async def h_admin_logs(request):
        """Butun tizim bo'yicha global loglar."""
        user, body, err = await with_admin(request)
        if err is not None:
            return err
        raw_events = db.last_events(limit=60)
        all_chats = {c["chat_id"]: (c.get("title") or str(c["chat_id"])) for c in db.all_chats(present_only=False)}
        out_events = []
        for e in raw_events:
            reasons = e["reasons"]
            if isinstance(reasons, str):
                try:
                    reasons = json.loads(reasons)
                except Exception:
                    reasons = [reasons]
            out_events.append({
                "id": e["id"],
                "chat_id": e["chat_id"],
                "chat_title": all_chats.get(e["chat_id"], str(e["chat_id"])),
                "user_id": e["user_id"],
                "name": e.get("name") or "",
                "username": e.get("username") or "",
                "score": e["score"],
                "reasons": reasons,
                "action": e["action"],
                "ts": e["ts"],
                "time_str": time.strftime("%d.%m %H:%M", time.localtime(e["ts"])),
            })
        return web.json_response({"ok": True, "events": out_events})

    app = web.Application()

    # Oddiy Web App
    app.router.add_get("/", h_index)
    app.router.add_get("/index.html", h_index)
    app.router.add_post("/api/state", h_state)
    app.router.add_post("/api/settings", h_settings)
    app.router.add_post("/api/scan", h_scan)
    app.router.add_post("/api/scan_action", h_scan_action)
    app.router.add_post("/api/logs", h_logs)
    app.router.add_post("/api/whitelist", h_whitelist)
    app.router.add_post("/api/whitelist/add", h_whitelist_add)
    app.router.add_post("/api/whitelist/remove", h_whitelist_remove)

    # Maxsus Admin Web App
    app.router.add_get("/admin", h_admin_index)
    app.router.add_get("/admin.html", h_admin_index)
    app.router.add_post("/api/admin/state", h_admin_state)
    app.router.add_post("/api/admin/chat_settings", h_admin_chat_settings)
    app.router.add_post("/api/admin/remove_chat", h_admin_remove_chat)
    app.router.add_post("/api/admin/broadcast", h_admin_broadcast)
    app.router.add_post("/api/admin/logs", h_admin_logs)

    # Statik fayllar
    assets = BASE_DIR / "webapp"
    if assets.exists():
        app.router.add_static("/static/", assets)

    return app


async def start_server(bot, db, config, scan_core, do_scan,
                       pending_dict: dict | None = None,
                       apply_scan_fn=None):
    """Serverni ishga tushiradi. Qaytaradi: runner (keyin tozalash uchun) yoki None."""
    if not AIOHTTP_OK:
        log.warning("aiohttp yo'q — web app o'chirilgan")
        return None
    app = build_app(bot, db, config, scan_core, do_scan,
                    pending_dict=pending_dict, apply_scan_fn=apply_scan_fn)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.WEBAPP_PORT)
    await site.start()
    log.info("Web app serveri ishga tushdi: port %s", config.WEBAPP_PORT)
    return runner


if __name__ == "__main__":
    # Mustaqil test qilish uchun
    import asyncio
    import config as cfg
    from database import DB
    import scan_core as sc

    async def dummy_scan(*a, **kw):
        pass

    db_inst = DB(cfg.DB_PATH)

    async def run():
        runner = await start_server(None, db_inst, cfg, sc, dummy_scan)
        if runner:
            print(f"Web server ishlamoqda: http://localhost:{cfg.WEBAPP_PORT} (To'xtatish uchun Ctrl+C)")
            try:
                while True:
                    await asyncio.sleep(3600)
            except (KeyboardInterrupt, asyncio.CancelledError):
                await runner.cleanup()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
