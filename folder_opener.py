"""Otevirani slozek predmetu v Pruzkumniku (faze 3).

Cte lekce ze sdilene cache, mapuje nazev predmetu na nazev slozky a pri zacatku
(nebo v prubehu) hodiny otevre prislusnou slozku v Pruzkumniku.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

# Mapovaci soubor predmet -> slozka. Stejne jako config: nejdriv per-user profil
# (%LOCALAPPDATA%\edupage\subject_folders.json), jinak vedle skriptu (sdilena slozka).
FOLDER_SUBJECT_MAP_FILE = Path(__file__).with_name("subject_folders.json")
USER_SUBJECT_MAP_FILE = (
    Path(os.environ.get("LOCALAPPDATA") or ".") / "edupage" / "subject_folders.json"
)
SUBJECT_MAP_FILE = FOLDER_SUBJECT_MAP_FILE  # zpetna kompatibilita


def subject_map_path() -> Path:
    """Aktivni cesta k subject_folders.json: per-user profil ma prednost."""
    return USER_SUBJECT_MAP_FILE if USER_SUBJECT_MAP_FILE.exists() else FOLDER_SUBJECT_MAP_FILE


def load_subject_map(path: Optional[Path] = None) -> dict[str, str]:
    """Nacte rucni mapovani {nazev predmetu: nazev slozky}. Chybi -> prazdne."""
    if path is None:
        path = subject_map_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    # Ignorujeme komentarove klice zacinajici "_".
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve_folder(
    subject: Optional[str], base: str, mapping: dict[str, str]
) -> Optional[Path]:
    """Vrati cestu ke slozce predmetu. Neexistujici predmet -> None.

    Nazev slozky = mapping[subject], jinak samotny nazev predmetu (1:1).
    """
    if not subject:
        return None
    folder_name = mapping.get(subject, subject)
    return Path(base) / folder_name


def _parse_hm(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def lessons_active_now(lessons: list[dict], now: Optional[datetime] = None) -> list[dict]:
    """Vrati dnesni nezrusene lekce, ktere prave probihaji (start <= ted <= konec).

    Diky rozsahu (start..konec) se otevre spravna slozka i kdyz se skolni pocitac
    zapne az v prubehu hodiny.
    """
    if now is None:
        now = datetime.now()
    today = now.date().strftime("%Y-%m-%d")
    now_t = now.time()

    active = []
    for lesson in lessons:
        if lesson.get("date") != today:
            continue
        if lesson.get("is_cancelled"):
            continue
        start = _parse_hm(lesson.get("start_time"))
        end = _parse_hm(lesson.get("end_time"))
        if start is None or end is None:
            continue
        if start <= now_t <= end:
            active.append(lesson)
    return active


def lesson_key(lesson: dict) -> str:
    """Jednoznacny klic lekce v ramci dne (aby se neotevirala opakovane)."""
    return f"{lesson.get('start_time')}|{lesson.get('subject')}"


def open_folder(path: Path) -> None:
    """Otevre slozku v Pruzkumniku (Windows)."""
    os.startfile(str(path))  # type: ignore[attr-defined]  # jen Windows
