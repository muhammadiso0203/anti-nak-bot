"""Algoritmni tekshirish: python test_detector.py

Internet va token kerak emas — faqat aniqlash mantig'ini sinaydi.
"""
from __future__ import annotations

from detector import Candidate, analyze

NEW = 8_200_000_000
VNEW = 8_600_000_000
OLD = 1_500_000_000

CASES: list[tuple[str, Candidate, str]] = [
    (
        "Tipik nakrutka: yangi ID, rasm yo'q, username yo'q, tasodifiy ism",
        Candidate(user_id=8_700_000_001, first_name="Qwrtbnm", has_photo=False,
                  username=None, language_code=None),
        "fake",
    ),
    (
        "Nakrutka to'lqini ichida kirgan akkaunt",
        Candidate(user_id=8_300_000_000, first_name="Dilshod", has_photo=False,
                  username=None, language_code="en", burst_count=25,
                  same_link_count=20),
        "fake",
    ),
    (
        "O'chirilgan akkaunt",
        Candidate(user_id=8_000_000_000, first_name=None, has_photo=False,
                  is_deleted=True),
        "fake",
    ),
    (
        "Reklama botи: ismda havola",
        Candidate(user_id=8_900_000_000, first_name="Kazino 1xbet t.me/spam",
                  has_photo=False, username="x9k2mqz7"),
        "fake",
    ),
    (
        "Haqiqiy odam: eski akkaunt, rasm, username, bio, premium",
        Candidate(user_id=350_000_000, first_name="Aziz", last_name="Karimov",
                  username="azizkarimov", language_code="uz", has_photo=True,
                  bio="Frontend dasturchi", is_premium=True),
        "clean",
    ),
    (
        "Haqiqiy odam: yangi akkaunt, lekin rasm/username/bio bor",
        Candidate(user_id=8_400_000_000, first_name="Malika", last_name="Yusupova",
                  username="malika_y", language_code="uz", has_photo=True,
                  bio="Student"),
        "clean",
    ),
    (
        "Shubhali: yangi akkaunt, rasm bor, username yo'q",
        Candidate(user_id=8_300_000_000, first_name="Nodira", has_photo=True,
                  language_code="ru"),
        "clean",
    ),
    (
        "Eski, lekin 2 yildan beri tashlab ketilgan akkaunt (skaner)",
        Candidate(user_id=900_000_000, first_name="Vasya", has_photo=False,
                  username=None, check_language=False, days_since_online=800),
        "fake",
    ),
    (
        "Eski, faol, lekin rasmi yo'q odam (skaner) — bloklanmasligi kerak",
        Candidate(user_id=900_000_000, first_name="Oybek", last_name="Tursunov",
                  username="oybek_t", has_photo=False, check_language=False,
                  days_since_online=3),
        "clean",
    ),
    (
        "Telegram scam deb belgilagan",
        Candidate(user_id=700_000_000, first_name="Support Admin", has_photo=True,
                  username="support_help", is_scam=True, check_language=False),
        "fake",
    ),
]


def main() -> None:
    ok = 0
    print("=" * 72)
    for title, cand, expected in CASES:
        v = analyze(cand, threshold=50, new_account_id=NEW,
                    very_new_account_id=VNEW, old_account_id=OLD, burst_limit=8)
        passed = v.level == expected
        ok += passed
        mark = "OK  " if passed else "XATO"
        print(f"[{mark}] {v.score:>3} ball -> {v.level:<10} (kutilgan: {expected})")
        print(f"        {title}")
        for r in v.reasons:
            print(f"          - {r}")
        print("-" * 72)
    print(f"Natija: {ok}/{len(CASES)} test o'tdi")


if __name__ == "__main__":
    main()
