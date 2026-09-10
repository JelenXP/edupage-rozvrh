"""Zaregistruje daemon do spousteni po prihlaseni (slozka Startup).

Pouziva slozku Startup aktualniho uzivatele - nevyzaduje administratora.
Vytvori zastupce (.lnk) na pythonw.exe (bez okna).

Pouziti:
    python install_autostart.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "EduPageRozvrh.lnk"
DAEMON_SCRIPT = Path(__file__).with_name("edupage_daemon.py")


def _pythonw_path() -> Path:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


def _startup_dir() -> Path:
    return (
        Path(os.environ["APPDATA"])
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )


def main() -> int:
    pythonw = _pythonw_path()
    lnk = _startup_dir() / SHORTCUT_NAME

    # PowerShell vytvori zastupce. Jednoduche uvozovky = zpetna lomitka doslovne.
    ps = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        f"$s.TargetPath='{pythonw}';"
        f"$s.Arguments='\"{DAEMON_SCRIPT}\"';"
        f"$s.WorkingDirectory='{DAEMON_SCRIPT.parent}';"
        f"$s.Save()"
    )

    print(f"Vytvarim zastupce ve slozce Startup:\n  {lnk}")
    print(f"  spusti: {pythonw} \"{DAEMON_SCRIPT}\"")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )

    if result.returncode != 0 or not lnk.exists():
        print("CHYBA pri vytvareni zastupce:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return 1

    print("Hotovo. Daemon se spusti automaticky pri pristim prihlaseni do Windows.")
    print("Rucni okamzity start (bez odhlaseni):")
    print(f'  start "" "{pythonw}" "{DAEMON_SCRIPT}"')
    print("Zruseni autostartu:  python uninstall_autostart.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
