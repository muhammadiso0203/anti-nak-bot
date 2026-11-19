"""Web server endpointlarini haqiqiy aiohttp bilan tekshirish (kompyuterda)."""
import asyncio, hashlib, hmac, json, os, sys, time
from urllib.parse import urlencode
os.environ.update({"BOT_TOKEN":"123456:TESTTOKEN_abc","ADMIN_IDS":"999"})
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import config, scan_core, webapp_server
from database import DB

BOT="123456:TESTTOKEN_abc"
def make_init(uid, name="Ali"):
    user=json.dumps({"id":uid,"first_name":name}, separators=(',',':'))
    f={"auth_date":str(int(time.time())),"user":user}
    dcs="\n".join(f"{k}={f[k]}" for k in sorted(f))
    secret=hmac.new(b"WebAppData", BOT.encode(), hashlib.sha256).digest()
    h=hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(dict(f, hash=h))

R=[]
def ck(t,ok,d=""): R.append(ok); print(("[OK  ] " if ok else "[XATO] ")+t+(f" -> {d}" if d else ""))

async def main():
    from aiohttp.test_utils import TestClient, TestServer
    db=DB("/tmp/webtest.db")
    for q in ["DELETE FROM chats","DELETE FROM events"]: db._exec(q)
    db.register_chat(-100111,"Mijoz kanali","channel"); db.set_added_by(-100111,555,"Mijoz")
    db.register_chat(-100222,"Boshqa kanal","channel"); db.set_added_by(-100222,777,"Boshqa")
    for i in range(3): db.log_event(-100111,8_900_000_000+i,"F",None,90,["x"],"ban")
    scan_core.ACCOUNT.update({"id":4242,"username":"Muhammadso","name":"M"})

    scan_calls=[]
    async def fake_do_scan(bot, chat_id, status, auto=False, notify_chat_id=None):
        scan_calls.append((chat_id, notify_chat_id))
    pending_scans = {}
    applied_calls = []
    async def fake_apply(bot, chat_id, cq=None):
        applied_calls.append(chat_id)

    app=webapp_server.build_app(
        bot=None, db=db, config=config, scan_core=scan_core,
        do_scan=fake_do_scan, pending_dict=pending_scans, apply_scan_fn=fake_apply
    )
    client=TestClient(TestServer(app)); await client.start_server()

    init555=make_init(555)  # mijoz (o'z kanali -100111)
    # 1) /api/state
    r=await client.post("/api/state", json={"initData":init555}); j=await r.json()
    ck("Mijoz state -> faqat o'z kanali", r.status==200 and len(j["channels"])==1 and j["channels"][0]["id"]==-100111, str([c["id"] for c in j["channels"]]))
    ck("Mijoz state -> bloklangan soni to'g'ri (3)", j["stats"]["blocked"]==3)
    ck("Skaner akkaunti ko'rinadi", j["scan_account"]=="@Muhammadso")

    # 2) auth yo'q -> 401
    r=await client.post("/api/state", json={"initData":"buzuq"})
    ck("Buzuq initData -> 401", r.status==401)

    # 3) /api/settings o'z kanalini o'zgartirish
    r=await client.post("/api/settings", json={"initData":init555,"chat_id":-100111,"key":"threshold","value":40})
    j=await r.json()
    ck("Mijoz o'z kanali chegarasini o'zgartirdi", r.status==200 and db.settings(-100111)["threshold"]==40)

    # 4) BOSHQANING kanalini o'zgartira olmaydi -> 403
    r=await client.post("/api/settings", json={"initData":init555,"chat_id":-100222,"key":"threshold","value":30})
    ck("Mijoz boshqaning kanalini o'zgartira olmaydi -> 403", r.status==403)

    # 5) /api/scan o'z kanalini
    r=await client.post("/api/scan", json={"initData":init555,"chat_id":-100111})
    j=await r.json()
    await asyncio.sleep(0.05)
    ck("Scan boshlandi va notify_chat_id=mijoz(555)", r.status==200 and scan_calls and scan_calls[-1]==(-100111,555), str(scan_calls))

    # 6) boshqaning kanalini scan -> 403
    r=await client.post("/api/scan", json={"initData":init555,"chat_id":-100222})
    ck("Boshqaning kanalini scan -> 403", r.status==403)

    # 7) index.html beriladi
    r=await client.get("/"); body=await r.text()
    ck("index.html yuklanadi (React bor)", r.status==200 and "react" in body.lower() and "Nakrutka" in body)

    # 8) EGA hamma kanalni ko'radi
    initOwner=make_init(999)
    r=await client.post("/api/state", json={"initData":initOwner}); j=await r.json()
    ck("Ega -> hamma kanal (2) va is_owner", j["is_owner"] and len(j["channels"])==2)

    # 9) preset o'rnatish
    r=await client.post("/api/settings", json={"initData":init555,"chat_id":-100111,"key":"preset","value":"hard"})
    st=db.settings(-100111)
    ck("Preset (hard) o'rnatildi", r.status==200 and st["threshold"]==42 and st["strict"]==1)

    # 10) /api/logs
    r=await client.post("/api/logs", json={"initData":init555,"chat_id":-100111})
    j=await r.json()
    ck("Logs o'qildi", r.status==200 and len(j["events"])==3)

    # 11) /api/whitelist add & remove
    r=await client.post("/api/whitelist/add", json={"initData":init555,"chat_id":-100111,"user_id":112233})
    ck("Whitelist qo'shildi", r.status==200 and 112233 in (await r.json())["whitelist"])
    r=await client.post("/api/whitelist/remove", json={"initData":init555,"chat_id":-100111,"user_id":112233})
    ck("Whitelist o'chirildi", r.status==200 and 112233 not in (await r.json())["whitelist"])

    # 12) pending scan va /api/scan_action apply
    pending_scans[-100111] = {"rows": [{"id": 1, "ism": "Bot1", "username": "b1", "ball": 90}], "ts": time.time(), "title": "Kanal"}
    r=await client.post("/api/state", json={"initData":init555}); j=await r.json()
    ck("Pending scan state'da ko'rindi", j["channels"][0]["pending"]["count"]==1)

    r=await client.post("/api/scan_action", json={"initData":init555,"chat_id":-100111,"action":"apply"})
    await asyncio.sleep(0.05)
    ck("Scan action apply chaqirildi", r.status==200 and -100111 in applied_calls)

    # 13) ADMIN TESTLARI
    # Oddiy mijoz (555) admin API ga kira olmaydi -> 403
    r=await client.post("/api/admin/state", json={"initData":init555})
    ck("Oddiy user /api/admin/state ga kira olmaydi -> 403", r.status==403)

    # Bot admini (999) admin API ga to'liq kira oladi -> 200
    r=await client.post("/api/admin/state", json={"initData":initOwner}); j=await r.json()
    ck("Admin /api/admin/state ga kirdi -> 200 va barcha kanallar bor", r.status==200 and len(j["chats"])==2 and len(j["customers"])==2)

    # Admin istalgan kanal sozlamasini o'zgartira oladi
    r=await client.post("/api/admin/chat_settings", json={"initData":initOwner,"chat_id":-100222,"key":"threshold","value":75})
    ck("Admin boshqa kanalni o'zgartirdi", r.status==200 and db.settings(-100222)["threshold"]==75)

    # Oddiy user admin orqali boshqa kanalni o'zgartira olmaydi -> 403
    r=await client.post("/api/admin/chat_settings", json={"initData":init555,"chat_id":-100222,"key":"threshold","value":80})
    ck("Oddiy user /api/admin/chat_settings ga kira olmaydi -> 403", r.status==403)

    # Admin xabarnoma (broadcast)
    r=await client.post("/api/admin/broadcast", json={"initData":initOwner,"text":"Salom hammaga!"})
    j=await r.json()
    ck("Admin broadcast yubordi", r.status==200 and j["sent"]==2)

    # admin.html fayli ochiladi
    r=await client.get("/admin.html"); body=await r.text()
    ck("admin.html yuklanadi", r.status==200 and "Bosh Admin Paneli" in body)

    await client.close()
    print(f"\nNATIJA: {sum(R)}/{len(R)}")
    return 0 if all(R) else 1

sys.exit(asyncio.run(main()))
