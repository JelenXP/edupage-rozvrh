"""Logika notifikace o dalsi hodine.

Najde nasledujici nezrusenou hodinu a sestavi text zpravy.
Samotne zobrazeni resi show_toast.py (vlastni okno, mimo notifikacni centrum).
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional


def _parse_hm(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def next_lesson_after(lessons: list[dict], now: Optional[datetime] = None) -> Optional[dict]:
    """Vrati nejblizsi dnesni nezrusenou hodinu, ktera zacina po `now`. Jinak None."""
    if now is None:
        now = datetime.now()
    today = now.date().strftime("%Y-%m-%d")
    now_t = now.time()

    candidates = []
    for lesson in lessons:
        if lesson.get("date") != today:
            continue
        if lesson.get("is_cancelled"):
            continue
        start = _parse_hm(lesson.get("start_time"))
        if start is None or start <= now_t:
            continue
        candidates.append((start, lesson))

    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


def build_notification(lesson: Optional[dict]) -> dict:
    """Vrati strukturovana data pro toast (nadpis + pole + zmeny + poznamka).

    Kdyz `lesson` je None (uz zadna dalsi hodina dnes), vrati {"kind": "end"}.
    `changes` = seznam zmenenych poli ("subject"/"teacher"/"room") proti stalemu
    rozvrhu - toast je zvyrazni stejne jako mrizka rozvrhu.
    """
    if lesson is None:
        return {"kind": "end"}

    classrooms = lesson.get("classrooms") or []
    teachers = lesson.get("teachers") or []
    return {
        "kind": "next",
        "start": lesson.get("start_time") or "?",
        "subject": lesson.get("subject") or "?",
        "room": ", ".join(classrooms) if classrooms else "?",
        "teacher": ", ".join(teachers) if teachers else "?",
        "changes": lesson.get("changes") or [],
        "note": lesson.get("my_note"),
        "note_pending": bool(lesson.get("note_pending")),
    }
