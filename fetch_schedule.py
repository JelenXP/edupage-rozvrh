"""Spustitelny skript: stahne rozvrh na 3 tydny dopredu, vypise ho a ulozi do cache.

Pouziti:
    python fetch_schedule.py
"""

from __future__ import annotations

import sys
from itertools import groupby

import edupage_fetch as core


def _print_schedule(entries: list[core.LessonEntry]) -> None:
    if not entries:
        print("Rozvrh je prazdny (zadne hodiny v danem obdobi).")
        return

    # Lekce jsou uz serazene po dnech; seskupime je pro vypis.
    for day, day_lessons in groupby(entries, key=lambda e: e.date):
        day_lessons = list(day_lessons)
        weekday = day_lessons[0].weekday
        print(f"\n=== {weekday} {day} ===")

        for lesson in sorted(day_lessons, key=lambda e: e.start_time or ""):
            cas = f"{lesson.start_time or '??'}-{lesson.end_time or '??'}"
            predmet = lesson.subject or "(bez predmetu)"
            ucebna = ", ".join(lesson.classrooms) if lesson.classrooms else "-"
            ucitel = ", ".join(lesson.teachers) if lesson.teachers else "-"
            zruseno = "  [ZRUSENO]" if lesson.is_cancelled else ""
            print(f"  {cas:>13}  {predmet:<25} ucebna: {ucebna:<10} {ucitel}{zruseno}")


def main() -> int:
    try:
        config = core.load_config()
    except core.ConfigError as e:
        print(f"CHYBA konfigurace:\n{e}", file=sys.stderr)
        return 1

    print(f"Prihlasuji se do {config['subdomain']}.edupage.org jako {config['username']} ...")
    try:
        edupage = core.login(config)
    except core.TwoFactorRequired as e:
        print(f"CHYBA: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - prihlaseni muze selhat ruzne
        print(f"CHYBA pri prihlaseni: {e}", file=sys.stderr)
        return 2

    print(f"Prihlaseno. Stahuji rozvrh na {core.DAYS_AHEAD} dni dopredu ...")

    errors: list[tuple] = []
    entries = core.fetch_schedule(
        edupage, on_error=lambda day, exc: errors.append((day, exc))
    )

    _print_schedule(entries)

    cache_path = core.save_cache(entries)
    print(f"\nStazeno {len(entries)} hodin. Ulozeno do: {cache_path}")

    if errors:
        print(f"\nUpozorneni: {len(errors)} dnu se nepodarilo stahnout:", file=sys.stderr)
        for day, exc in errors:
            print(f"  {day}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
