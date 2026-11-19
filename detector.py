"""Nakrutka (fake/bot akkaunt) aniqlash algoritmi.

Hech bir belgi yakka holda "bu fake" degani emas — shuning uchun
ball tizimi ishlatiladi: har bir shubhali belgi ball qo'shadi,
har bir "tirik odam" belgisi ball ayiradi. Yig'indi chegaradan
oshsa — nakrutka deb hisoblanadi.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- ballar
W = {
    "deleted": 45,          # o'chirilgan akkaunt (ism bo'sh)
    "no_photo": 18,         # profil rasmi yo'q
    "no_username": 10,      # username yo'q
    "random_username": 16,  # username tasodifiy harflar to'plami
    "random_name": 18,      # ism tasodifiy harflar to'plami
    "digit_name": 12,       # ism oxirida 3+ raqam (Ali12345)
    "short_name": 10,       # ism 1-2 belgidan iborat
    "no_language": 8,       # til kodi yo'q (odatda emulyator/API akkaunt)
    "spam_name": 25,        # ismda reklama/havola/spam so'z
    "homoglyph": 14,        # bitta so'zda lotin+kirill aralash
    "very_new": 30,         # juda yangi akkaunt
    "new": 20,              # yangi akkaunt
    "is_bot": 50,           # bot akkaunt
    "burst": 25,            # bir vaqtda to'da bo'lib kirish
    "same_link_burst": 20,  # bitta havoladan to'da bo'lib kirish
    "no_name_parts": 6,     # familiya ham, username ham yo'q
    "long_inactive": 15,    # 1 yildan ortiq onlayn bo'lmagan (skaner)
    "very_long_inactive": 25,  # 2 yildan ortiq tashlab ketilgan akkaunt
    "scam_flag": 60,        # Telegram "scam/fake" deb belgilagan (skaner)
    "restricted": 25,       # cheklangan akkaunt (skaner)
    # --- "tirik odam" belgilari (minus ball) ---
    "premium": -25,
    "has_bio": -10,
    "old_account": -20,
    "has_photo_and_username": -8,
}

SPAM_WORDS = (
    "t.me/", "http", "www.", "@", "bit.ly", "casino", "kazino", "bet", "1xbet",
    "melbet", "porn", "xxx", "18+", "sex", "invest", "crypto", "kripto", "bitcoin",
    "usdt", "forex", "zarab", "pul ishla", "oson pul", "qarz", "kredit", "stavka",
    "subscriber", "obunachi", "nakrutka", "arzon obuna", "live", "ставк", "казино",
    "заработ", "подпис", "накрут",
)

VOWELS = set("aeiouаеёиоуыэюяoʻuʻ")
_RE_DIGIT_TAIL = re.compile(r"\d{3,}$")
_RE_ONLY_DIGITS = re.compile(r"^[\W\d_]+$", re.UNICODE)
_RE_LATIN = re.compile(r"[a-zA-Z]")
_RE_CYR = re.compile(r"[Ѐ-ӿ]")
_RE_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _norm(value: str | None) -> str:
    return (value or "").strip()


def _entropy(s: str) -> float:
    """Satrdagi belgilar tarqoqligi (tasodifiylik o'lchovi)."""
    s = s.lower()
    if len(s) < 2:
        return 0.0
    freq: dict[str, int] = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    total = len(s)
    return -sum((c / total) * math.log2(c / total) for c in freq.values())


def _max_consonant_run(s: str) -> int:
    run = best = 0
    for ch in s.lower():
        if ch.isalpha() and ch not in VOWELS:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def looks_random(s: str) -> bool:
    """Tasodifiy generatsiya qilingan matnga o'xshaydimi?"""
    s = _norm(s)
    core = re.sub(r"[\W_]+", "", s, flags=re.UNICODE)
    if len(core) < 5:
        return False
    letters = [c for c in core if c.isalpha()]
    if not letters:
        return True
    vowel_ratio = sum(1 for c in core.lower() if c in VOWELS) / max(len(letters), 1)
    # unli harf deyarli yo'q yoki juda ko'p undosh ketma-ket
    if vowel_ratio < 0.18 or _max_consonant_run(core) >= 5:
        return True
    # harf va raqam aralash + yuqori entropiya (masalan "k8xj2qm")
    has_digit = any(c.isdigit() for c in core)
    if has_digit and _entropy(core) > 2.9 and len(core) >= 7:
        return True
    # tasodifiy katta-kichik harf aralashmasi: aBcDeF
    switches = sum(
        1 for a, b in zip(core, core[1:])
        if a.isalpha() and b.isalpha() and a.isupper() != b.isupper()
    )
    if len(core) >= 7 and switches >= len(core) * 0.5:
        return True
    return False


def has_spam_words(text: str) -> bool:
    low = _norm(text).lower()
    return any(word in low for word in SPAM_WORDS)


def has_homoglyph_mix(text: str) -> bool:
    """Bitta so'z ichida lotin va kirill harflari aralashgan (soxta ism belgisi)."""
    for word in _RE_WORD.findall(_norm(text)):
        if len(word) >= 3 and _RE_LATIN.search(word) and _RE_CYR.search(word):
            return True
    return False


# ---------------------------------------------------------------- natija
@dataclass
class Verdict:
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    threshold: int = 50
    hard: bool = False   # inkor etilmaydigan belgi (bot, scam, o'chirilgan...)

    @property
    def is_fake(self) -> bool:
        return self.score >= self.threshold

    @property
    def level(self) -> str:
        if self.score >= self.threshold:
            return "fake"
        if self.score >= self.threshold - 10:
            return "suspicious"
        return "clean"

    @property
    def emoji(self) -> str:
        return {"fake": "🚫", "suspicious": "⚠️", "clean": "✅"}[self.level]

    def add(self, key: str, reason: str) -> None:
        weight = W.get(key, 0)
        if weight == 0:
            return
        self.score += weight
        sign = "+" if weight > 0 else ""
        self.reasons.append(f"{reason} ({sign}{weight})")

    def report(self) -> str:
        if not self.reasons:
            return "— belgilar topilmadi"
        return "\n".join(f"• {r}" for r in self.reasons)


@dataclass
class Candidate:
    """Tekshiriladigan akkaunt haqidagi ma'lumot (Bot API yoki Telethon'dan)."""
    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_bot: bool = False
    is_premium: bool = False
    is_deleted: bool = False
    has_photo: bool | None = None     # None = aniqlanmadi
    bio: str | None = None
    is_scam: bool = False
    is_fake_flag: bool = False
    is_restricted: bool = False
    days_since_online: int | None = None   # faqat skanerda
    check_language: bool = True            # Telethon'da til ko'rinmaydi -> False
    # kontekst
    burst_count: int = 0
    same_link_count: int = 0

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (_norm(self.first_name), _norm(self.last_name)) if p)


def strict_gate(c: Candidate, level: int, new_account_id: int) -> str | None:
    """QATTIQ QOIDALAR: ball yetmasa ham darhol bloklaydigan shartlar.

    0 — o'chiq (faqat ball tizimi)
    1 — rasm ham, username ham yo'q bo'lsa
    2 — profil rasmi yo'q bo'lsa
    3 — username yo'q yoki akkaunt yangi bo'lsa (eng qattiq)

    Premium akkauntlar bu qoidalardan ozod — nakrutka servislar
    pullik Premium bermaydi, lekin haqiqiy odamlarda u ko'p uchraydi.
    """
    if level <= 0 or c.is_premium:
        return None
    no_photo = c.has_photo is False          # None = aniqlanmadi, jazolanmaydi
    no_username = not _norm(c.username)
    is_new = c.user_id >= new_account_id

    if no_photo and no_username:
        return "Qattiq qoida: rasm ham, username ham yo'q"
    if level >= 2 and no_photo:
        return "Qattiq qoida: profil rasmi yo'q"
    if level >= 3 and no_username:
        return "Qattiq qoida: username yo'q"
    if level >= 3 and is_new:
        return "Qattiq qoida: akkaunt yangi"
    return None


def analyze(
    c: Candidate,
    *,
    threshold: int = 50,
    new_account_id: int = 8_200_000_000,
    very_new_account_id: int = 8_600_000_000,
    old_account_id: int = 1_500_000_000,
    burst_limit: int = 8,
    strict_level: int = 0,
) -> Verdict:
    """Akkauntni tahlil qilib, ball va sabablarni qaytaradi."""
    v = Verdict(threshold=threshold)
    name = c.full_name
    username = _norm(c.username)

    # --- eng kuchli (inkor etilmaydigan) belgilar ---
    # Bu belgilar bo'lsa, "tirik odam" bonuslari hisobga olinmaydi.
    if c.is_deleted or not name:
        v.add("deleted", "O'chirilgan / ismsiz akkaunt")
        v.hard = True
    if c.is_bot:
        v.add("is_bot", "Bot akkaunt")
        v.hard = True
    if c.is_scam:
        v.add("scam_flag", "Telegram «scam» deb belgilagan")
        v.hard = True
    if c.is_fake_flag:
        v.add("scam_flag", "Telegram «fake» deb belgilagan")
        v.hard = True
    if c.is_restricted:
        v.add("restricted", "Cheklangan akkaunt")

    # --- profil to'liqligi ---
    if c.has_photo is False:
        v.add("no_photo", "Profil rasmi yo'q")
    if not username:
        v.add("no_username", "Username yo'q")
    elif looks_random(username):
        v.add("random_username", f"Username tasodifiy: @{username}")

    if not username and not _norm(c.last_name):
        v.add("no_name_parts", "Familiya ham, username ham yo'q")

    # --- ism tahlili ---
    if name:
        if _RE_ONLY_DIGITS.match(name):
            v.add("random_name", "Ism faqat raqam/belgilardan iborat")
        elif looks_random(name):
            v.add("random_name", f"Ism tasodifiy harflar: «{name[:24]}»")
        if _RE_DIGIT_TAIL.search(name.replace(" ", "")):
            v.add("digit_name", "Ism oxirida ketma-ket raqamlar")
        if len(re.sub(r"\W", "", name, flags=re.UNICODE)) <= 2:
            v.add("short_name", "Ism juda qisqa (1-2 belgi)")
        if has_spam_words(name) or has_spam_words(username):
            v.add("spam_name", "Ism/username'da reklama yoki havola")
        if has_homoglyph_mix(name):
            v.add("homoglyph", "Ismda lotin+kirill harflari aralash")

    if c.check_language and not _norm(c.language_code):
        v.add("no_language", "Ilova tili aniqlanmagan")

    # --- faollik (faqat skanerda ko'rinadi) ---
    inactive = c.days_since_online
    abandoned = inactive is not None and inactive >= 365
    if inactive is not None and inactive >= 730:
        v.add("very_long_inactive", f"{inactive} kundan beri onlayn emas (tashlab ketilgan)")
    elif abandoned:
        v.add("long_inactive", f"{inactive} kundan beri onlayn emas")

    # --- akkaunt yoshi (ID bo'yicha taxminiy) ---
    if c.user_id >= very_new_account_id:
        v.add("very_new", "Akkaunt juda yangi (ID juda yuqori)")
    elif c.user_id >= new_account_id:
        v.add("new", "Akkaunt yangi")
    elif c.user_id <= old_account_id and not v.hard and not abandoned:
        # eski akkaunt — lekin tashlab ketilgan bo'lsa bu ijobiy belgi emas
        v.add("old_account", "Eski akkaunt (ko'p yillik)")

    # --- to'da bo'lib kirish ---
    if c.burst_count >= burst_limit:
        v.add("burst", f"{c.burst_count} kishi bir vaqtda kirdi (nakrutka to'lqini)")
    if c.same_link_count >= max(3, burst_limit // 2):
        v.add("same_link_burst", f"Bitta havoladan {c.same_link_count} kishi kirdi")

    # --- tirik odam belgilari (kuchli belgi bo'lmasa) ---
    if not v.hard:
        if c.is_premium:
            v.add("premium", "Telegram Premium")
        if _norm(c.bio):
            v.add("has_bio", "Bio (haqida) yozilgan")
        if c.has_photo and username:
            v.add("has_photo_and_username", "Rasm ham, username ham bor")
    elif c.is_premium:
        v.reasons.append("Premium (hisobga olinmadi — kuchli belgi bor)")

    v.score = max(0, min(100, v.score))

    # --- qattiq qoidalar: ball yetmasa ham bloklash ---
    gate = strict_gate(c, strict_level, new_account_id)
    if gate:
        v.hard = True
        if v.score < threshold:
            v.score = threshold
        v.reasons.append(f"{gate} → darhol blok")

    return v
