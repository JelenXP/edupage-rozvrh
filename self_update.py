"""Auto-aktualizace kodu z gitu.

Daemon si periodicky (a pri startu) stahne novou verzi kodu z gitu a kdyz prisly
zmeny, restartuje se, aby je nacetl. Diky tomu staci pushnout novou verzi na
GitHub a vsem, kdo projekt pouzivaji, se sama stahne a aktivuje.

Aktualizace se provede JEN kdyz:
  - slozka s kodem je git repo (`.git` existuje),
  - pracovni strom je CISTY (zadne rozdelane lokalni zmeny),
  - upstream (origin) je NAPRED a jde o fast-forward (lokalni HEAD je jeho
    predchudce) - tim je vyvojarsky stroj prirozene chraneny: kdyz mas lokalni
    (i necommitnute nebo jeste nepushnute) zmeny, auto-update se preskoci.

Pri jakekoli chybe (offline, git chybi, konflikt) se tise nic nestane a daemon
bezi dal na stavajicim kodu.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent

# Na Windows daemon bezi pod pythonw.exe (bez konzole). Kdyz z nej spustime
# git.exe, na okamzik problikne cerne okno cmd. CREATE_NO_WINDOW to potlaci.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_DIR), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


def is_git_repo() -> bool:
    return (REPO_DIR / ".git").exists()


def check_and_update(logger=None) -> bool:
    """Stahne novou verzi kodu, pokud je k dispozici (fast-forward).

    Vrati True, kdyz se kod zmenil (volajici ma daemon restartovat), jinak False.
    Vsechny chyby polyka (vraci False) - auto-update nikdy nesmi shodit daemon.
    """
    def _log(level: str, msg: str, *a) -> None:
        if logger is not None:
            getattr(logger, level)(msg, *a)

    if not is_git_repo():
        return False

    try:
        # 1) Nerozbijet rozdelanou lokalni praci (typicky vyvojarsky stroj).
        if _git("status", "--porcelain").stdout.strip():
            return False

        # 2) Zjistit stav upstreamu (offline -> fetch selze -> tise konec).
        if _git("fetch", "--quiet").returncode != 0:
            return False

        local = _git("rev-parse", "HEAD").stdout.strip()
        remote = _git("rev-parse", "@{u}").stdout.strip()
        if not remote or local == remote:
            return False

        # 3) Updatovat jen kdyz je remote NAPRED (mozny fast-forward).
        #    Kdyz je lokalni napred / divergovane (vyvojar), nedelat nic.
        if _git("merge-base", "--is-ancestor", "HEAD", "@{u}").returncode != 0:
            return False

        pull = _git("pull", "--ff-only", "--quiet")
        if pull.returncode != 0:
            _log("warning", "Auto-update: git pull selhal: %s", pull.stderr.strip())
            return False

        _log("info", "Auto-update: stazena nova verze kodu (%s -> %s).",
             local[:7], remote[:7])
        return True
    except FileNotFoundError:
        return False  # git neni nainstalovany
    except Exception as e:  # noqa: BLE001 - auto-update nikdy nesmi shodit daemon
        _log("warning", "Auto-update: chyba: %s", e)
        return False
