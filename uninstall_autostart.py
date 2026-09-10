"""Odebere daemon ze spousteni po prihlaseni (smaze zastupce ze slozky Startup).

Pouziti:
    python uninstall_autostart.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SHORTCUT_NAME = "EduPageRozvrh.lnk"


def _startup_dir() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def main() -> int:
    lnk = _startup_dir() / SHORTCUT_NAME
    if not lnk.exists():
        print("Zastupce nenalezen (autostart uz nejspis neni nastaven).")
        return 0

    try:
        lnk.unlink()
    except OSError as e:
        print(f"CHYBA pri mazani zastupce: {e}", file=sys.stderr)
        return 1

    print("Hotovo. Autostart zrusen.")
    print("Pozn.: uz bezici daemon dobehne az do odhlaseni/restartu. "
          "Muzes ho ukoncit ve Spravci uloh (pythonw.exe).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
