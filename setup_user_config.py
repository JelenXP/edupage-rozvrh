"""Pripravi per-user config pro beh ze SDILENE slozky s kodem.

Spust jednou na kazdem uctu, ktery ma bezet z jedne sdilene slozky
(napr. skolni ucet). Vytvori %LOCALAPPDATA%\\edupage\\ a nakopiruje tam
vzorovy config.json a subject_folders.json (pokud tam jeste nejsou).
Existujici soubory NEPREPISUJE.

Pouziti:
    python setup_user_config.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import edupage_fetch as core
import folder_opener


def _copy_if_missing(src: Path, dst: Path) -> str:
    if dst.exists():
        return f"  ponechano (uz existuje): {dst}"
    if not src.exists():
        return f"  CHYBI vzor: {src}"
    shutil.copyfile(src, dst)
    return f"  vytvoreno: {dst}"


def main() -> int:
    app_dir = core.USER_APP_DIR
    app_dir.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).parent

    print(f"Per-user slozka: {app_dir}\n")
    print(_copy_if_missing(here / "config.example.json", core.USER_CONFIG_FILE))
    print(_copy_if_missing(
        here / "subject_folders.example.json", folder_opener.USER_SUBJECT_MAP_FILE
    ))

    print("\nDalsi kroky:")
    print(f"  1) Uprav:  {core.USER_CONFIG_FILE}")
    print("     (username, password, subdomain; pro skolni ucet open_folders=true,")
    print("      folders_base a notify_next_lesson=true)")
    print(f"  2) Uprav (volitelne): {folder_opener.USER_SUBJECT_MAP_FILE}")
    print("  3) Autostart z teto sdilene slozky:  python install_autostart.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
