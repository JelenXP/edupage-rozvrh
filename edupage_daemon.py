"""Tichy daemon: drzi sdilenou cache rozvrhu aktualni a (volitelne) otevira
slozky predmetu pri zacatku hodiny.

Chovani ridi config.json:
  - vzdy: fetch rozvrhu kazdou hodinu do sdilene cache (C:\\Users\\Public\\...)
  - "open_folders": true  -> navic kazdou minutu kouka do cache a otevira
                             v Pruzkumniku slozku prave probihajici hodiny
                             (jen na skolnim uctu, kde jsou slozky)

Bezi trvale na pozadi. Cache je zdroj pravdy - kdyz stazeni selze (offline),
cache se NEPREPISUJE a otevirani slozek jede z posledniho dostupneho rozvrhu.

Pouziti:
    python edupage_daemon.py          # trvala smycka
    python edupage_daemon.py --once   # jen jeden fetch a konec (na test)
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, time as dtime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import edupage_fetch as core
import folder_opener
import notifier
import self_update

# Jak casto stahovat rozvrh (sekundy). 1 hodina.
FETCH_INTERVAL_SECONDS = 60 * 60
# Po neuspesnem stazeni zkusit znovu drive (s). 5 minut.
RETRY_INTERVAL_SECONDS = 5 * 60
# Jak casto tikat (kontrola zacatku hodiny / konce hodiny). 60 s.
TICK_SECONDS = 60
# Okno po konci hodiny, ve kterem se jeste smi notifikovat (s). Brani spamu
# starych hodin pri pozdnim startu daemonu.
NOTIFY_GRACE_SECONDS = 90
# Jak dlouho zustane toast s dalsi hodinou videt (s). 1 minuta.
NOTIFY_DURATION_S = 60
# Nazev mutexu pro pojistku proti dvojimu behu (v ramci relace uzivatele).
_MUTEX_NAME = "edupage_rozvrh_daemon"

LOG_FILE = core.CACHE_DIR / "daemon.log"
_SHOW_TOAST = Path(__file__).with_name("show_toast.py")


def _pythonw_path() -> Path:
    """Vrati pythonw.exe (bez okna) - i kdyz daemon bezi pod python.exe."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


_PYTHONW = _pythonw_path()


def acquire_single_instance(retries: int = 0, delay: float = 0.5) -> bool:
    """Zajisti, ze bezi jen jedna instance daemonu. Vrati False pokud uz bezi.

    `retries` > 0 = pockej (opakovanym pokusem), az predchozi instance uvolni
    mutex - pouziva se pri restartu z tray, kdy nova instance startuje driv,
    nez stara stihne skoncit.
    """
    ERROR_ALREADY_EXISTS = 183
    try:
        kernel32 = ctypes.windll.kernel32
        for attempt in range(retries + 1):
            handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
            if kernel32.GetLastError() != ERROR_ALREADY_EXISTS:
                # Handle si drzime v atributu funkce, aby ho nesebral GC.
                acquire_single_instance._mutex = handle
                return True
            # Uz existuje - zavri handle (at mutex neudrzujeme nazivu) a zkus znovu.
            kernel32.CloseHandle(handle)
            if attempt < retries:
                time.sleep(delay)
        return False
    except (AttributeError, OSError):
        return True  # kdyz mutex nejde vytvorit, radeji bezet nez nebezet


def _setup_logging() -> logging.Logger:
    core.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("edupage_daemon")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if sys.stdout is not None:  # pod pythonw je stdout None
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # cestina v konzoli
        except (AttributeError, ValueError):
            pass
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        logger.addHandler(console)

    return logger


def run_once(logger: logging.Logger) -> bool:
    """Jeden fetch cyklus. Pri neuspechu cache NEPREPISUJE. Vrati True pri uspechu."""
    try:
        config = core.load_config()
    except core.ConfigError as e:
        logger.error("Chyba konfigurace: %s", e)
        return False

    try:
        edupage = core.get_session()  # znovupouzije drzenou session (uspora loginu)
    except core.TwoFactorRequired as e:
        logger.error("2FA: %s", e)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning("Prihlaseni selhalo (cache ponechana): %s", e)
        return False

    def _flush_and_fetch(ep):
        # Odeslat poznamky ulozene offline (kdyz predtim nebylo pripojeni).
        try:
            core.flush_note_queue(ep, logger)
        except Exception as e:  # noqa: BLE001 - fronta nesmi shodit fetch
            logger.warning("Odeslani fronty poznamek selhalo: %s", e)
        errs: list[tuple] = []
        got = core.fetch_schedule(ep, on_error=lambda day, exc: errs.append((day, exc)))
        return got, errs

    entries, day_errors = _flush_and_fetch(edupage)

    if not entries:
        # Mozna vyprsela drzena session -> jeden pokus s cerstvym prihlasenim.
        try:
            edupage = core.get_session(force_new=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("Prihlaseni selhalo (cache ponechana): %s", e)
            return False
        entries, day_errors = _flush_and_fetch(edupage)

    if not entries:
        logger.warning(
            "Stazeno 0 hodin (%d dnu selhalo) - cache PONECHANA (posledni dostupna).",
            len(day_errors),
        )
        return False

    assignments = core.fetch_assignments(
        edupage,
        on_error=lambda exc: logger.warning("Nepodarilo se stahnout DU/testy: %s", exc),
    )

    try:
        path = core.persist_cache(entries, assignments)
    except OSError as e:
        # Napr. chyba opravneni na sdilene cache nebo plny disk. Nesmi shodit daemon.
        logger.warning("Ulozeni cache selhalo (ponechana stara): %s", e)
        return False

    logger.info(
        "Stazeno %d hodin, %d DU/testu%s. Cache: %s",
        len(entries),
        len(assignments),
        f" ({len(day_errors)} dnu selhalo)" if day_errors else "",
        path,
    )
    return True


def check_and_open_folders(logger: logging.Logger, opened: dict[str, set]) -> None:
    """Otevre slozku prave probihajici hodiny (pokud jeste nebyla otevrena dnes)."""
    config = core.load_config()
    base = config.get("folders_base")
    if not base:
        logger.error("open_folders je zapnute, ale chybi 'folders_base' v config.json.")
        return

    mapping = folder_opener.load_subject_map()
    lessons = core.load_cache()

    now = datetime.now()
    today = now.date().strftime("%Y-%m-%d")

    # Udrzba: pamet si drzime jen pro dnesek.
    for d in list(opened):
        if d != today:
            del opened[d]
    day_opened = opened.setdefault(today, set())

    for lesson in folder_opener.lessons_active_now(lessons, now):
        key = folder_opener.lesson_key(lesson)
        if key in day_opened:
            continue

        folder = folder_opener.resolve_folder(lesson.get("subject"), base, mapping)
        if folder is not None and folder.exists():
            try:
                folder_opener.open_folder(folder)
                logger.info("Otevrena slozka pro '%s': %s",
                            lesson.get("subject"), folder)
            except OSError as e:
                logger.warning("Nepodarilo se otevrit slozku %s: %s", folder, e)
        else:
            logger.warning("Slozka pro predmet '%s' neexistuje: %s",
                           lesson.get("subject"), folder)

        # Oznacime jako vyrizene at netikame porad dokola.
        day_opened.add(key)


def _parse_hm(value):
    try:
        h, m = value.split(":")
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def _show_toast(data: dict, logger: logging.Logger) -> None:
    """Spusti vlastni toast okno (mimo notifikacni centrum) jako samostatny proces.

    Predava strukturovana data (JSON) - toast pak zvyrazni zmeny a ukaze poznamku.
    Notifikace zustane NOTIFY_DURATION_S sekund.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    try:
        json.dump(data, tmp, ensure_ascii=False)
        tmp.close()
        subprocess.Popen(
            [str(_PYTHONW), str(_SHOW_TOAST), tmp.name, str(NOTIFY_DURATION_S)]
        )
    except OSError as e:
        logger.warning("Nepodarilo se zobrazit notifikaci: %s", e)


def check_and_notify(logger: logging.Logger, notified: dict[str, set]) -> None:
    """Na konci hodiny ukaze toast s dalsi hodinou (nebo 'Konec vyucovani')."""
    lessons = core.load_cache()
    now = datetime.now()
    today = now.date().strftime("%Y-%m-%d")

    for d in list(notified):
        if d != today:
            del notified[d]
    day_notified = notified.setdefault(today, set())

    now_t = now.time()
    now_secs = now_t.hour * 3600 + now_t.minute * 60 + now_t.second

    for lesson in lessons:
        if lesson.get("date") != today or lesson.get("is_cancelled"):
            continue
        end = _parse_hm(lesson.get("end_time"))
        if end is None:
            continue

        end_secs = end.hour * 3600 + end.minute * 60
        # Notifikuj jen tesne po konci hodiny (0..GRACE sekund po end_time).
        if not (0 <= now_secs - end_secs <= NOTIFY_GRACE_SECONDS):
            continue

        key = f"{lesson.get('end_time')}|{lesson.get('subject')}"
        if key in day_notified:
            continue

        nxt = notifier.next_lesson_after(lessons, now)
        data = notifier.build_notification(nxt)
        _show_toast(data, logger)
        nxt_label = "konec vyučování" if data.get("kind") == "end" else data.get("subject")
        logger.info("Notifikace po hodine '%s' -> dalsi: %s", lesson.get("subject"), nxt_label)
        day_notified.add(key)


def run_loop(
    logger: logging.Logger,
    open_folders: bool,
    notify: bool,
    stop_event: threading.Event,
    fetch_now_event: threading.Event,
    auto_update: bool = False,
    on_code_update=None,
) -> None:
    """Hlavni smycka. Fetch bezi v samostatnem vlakne (neblokuje kontroly).

    - Neuspesny fetch se zopakuje uz za RETRY_INTERVAL_SECONDS (ne az za hodinu).
    - `fetch_now_event` vynuti okamzite stazeni (z tray 'Stahnout ted').
    - `stop_event` smycku ukonci.
    - `auto_update` = pri startu a pak pred kazdym fetchem zkusit stahnout novou
      verzi kodu z gitu; kdyz prisla, zavolat `on_code_update` (= restart daemonu).
    """
    opened: dict[str, set] = {}
    notified: dict[str, set] = {}

    fetch_result: dict[str, bool] = {}
    fetch_thread: threading.Thread | None = None
    next_fetch_at = 0.0  # hned pri startu

    def _do_fetch() -> None:
        try:
            fetch_result["ok"] = run_once(logger)
        except Exception as e:  # noqa: BLE001 - fetch nesmi shodit daemon
            logger.warning("Fetch selhal necekane: %s", e)
            fetch_result["ok"] = False

    while not stop_event.is_set():
        # Sklidit dokonceny fetch a naplanovat dalsi (kratsi interval pri neuspechu).
        if fetch_thread is not None and not fetch_thread.is_alive():
            ok = fetch_result.get("ok", False)
            delay = FETCH_INTERVAL_SECONDS if ok else RETRY_INTERVAL_SECONDS
            next_fetch_at = time.monotonic() + delay
            if not ok:
                logger.info("Dalsi pokus o stazeni za %d min.", delay // 60)
            fetch_thread = None

        if fetch_now_event.is_set():
            fetch_now_event.clear()
            next_fetch_at = 0.0
            logger.info("Rucni stazeni (z tray).")

        if fetch_thread is None and time.monotonic() >= next_fetch_at:
            # Pred fetchem zkusit auto-update kodu (stejna kadence = start + hodinove).
            if auto_update and on_code_update is not None:
                try:
                    if self_update.check_and_update(logger):
                        logger.info("Nova verze kodu - restartuji daemon.")
                        on_code_update()
                        break
                except Exception as e:  # noqa: BLE001 - update nesmi shodit daemon
                    logger.warning("Auto-update selhal: %s", e)

            fetch_result.clear()
            fetch_thread = threading.Thread(target=_do_fetch, daemon=True)
            fetch_thread.start()

        if open_folders:
            try:
                check_and_open_folders(logger, opened)
            except Exception as e:  # noqa: BLE001 - watcher nesmi shodit daemon
                logger.warning("Chyba pri kontrole slozek: %s", e)

        if notify:
            try:
                check_and_notify(logger, notified)
            except Exception as e:  # noqa: BLE001 - watcher nesmi shodit daemon
                logger.warning("Chyba pri notifikaci: %s", e)

        stop_event.wait(TICK_SECONDS)

    logger.info("Smycka ukoncena.")


def main(argv: list[str]) -> int:
    logger = _setup_logging()

    if "--once" in argv:
        logger.info("Jednorazovy fetch (--once).")
        return 0 if run_once(logger) else 1

    # Pri restartu z tray startujeme driv, nez stara instance stihne skoncit -
    # pockame chvili na uvolneni mutexu.
    restarted = "--restarted" in argv
    if not acquire_single_instance(retries=20 if restarted else 0):
        logger.info("Daemon uz bezi (jina instance) - koncim.")
        return 0
    if restarted:
        logger.info("Daemon restartovan (z tray).")

    # Lokalni server pro tlacitko "Aktualizovat" v rozvrhu.
    try:
        import control_server
        control_server.start(logger)
    except Exception as e:  # noqa: BLE001 - server je volitelny
        logger.warning("Control server nespusten: %s", e)

    try:
        config = core.load_config()
        open_folders = bool(config.get("open_folders"))
        notify = bool(config.get("notify_next_lesson"))
        auto_update = bool(config.get("auto_update", True))
    except core.ConfigError as e:
        logger.error("Chyba konfigurace: %s", e)
        return 1

    logger.info(
        "Daemon spusten. Fetch kazdych %d min, otevirani slozek: %s, notifikace: %s, auto-update: %s.",
        FETCH_INTERVAL_SECONDS // 60,
        "ANO" if open_folders else "NE",
        "ANO" if notify else "NE",
        "ANO" if auto_update else "NE",
    )

    stop_event = threading.Event()
    fetch_now_event = threading.Event()

    def _restart() -> None:
        # Spusti novou instanci (pocka na uvolneni mutexu) a tuhle ukonci.
        # Pouziva ho jak tray "Restart", tak auto-update po stazeni nove verze.
        logger.info("Restart daemonu.")
        try:
            subprocess.Popen([str(_PYTHONW), str(Path(__file__)), "--restarted"])
        except OSError as e:
            logger.warning("Restart selhal (novou instanci nelze spustit): %s", e)
            return
        stop_event.set()  # ukonci smycku; tray se zastavi v _restart handleru

    # Smycka bezi ve vlakne; hlavni vlakno drzi ikonu v liste (tray).
    loop_thread = threading.Thread(
        target=run_loop,
        args=(logger, open_folders, notify, stop_event, fetch_now_event,
              auto_update, _restart),
        daemon=True,
    )
    loop_thread.start()

    try:
        import tray_icon
    except ImportError:
        logger.info("pystray/Pillow neni k dispozici - bezim bez ikony v liste.")
        try:
            while not stop_event.wait(1):
                pass
        except KeyboardInterrupt:
            stop_event.set()
        loop_thread.join(timeout=5)
        return 0

    def _open_log() -> None:
        try:
            os.startfile(str(LOG_FILE))  # type: ignore[attr-defined]
        except OSError as e:
            logger.warning("Nepodarilo se otevrit log: %s", e)

    def _show_timetable() -> None:
        # Ve vlakne, aby stazeni nejaktualnejsiho rozvrhu neblokovalo ikonu.
        def worker() -> None:
            try:
                import show_timetable
                show_timetable.open_timetable(refresh=True)
            except Exception as e:  # noqa: BLE001 - z tray nesmi nic shodit
                logger.warning("Nepodarilo se otevrit rozvrh: %s", e)

        threading.Thread(target=worker, daemon=True).start()

    try:
        tray_icon.run_tray(
            on_fetch_now=fetch_now_event.set,
            on_quit=stop_event.set,
            on_open_log=_open_log,
            on_show_timetable=_show_timetable,
            on_restart=_restart,
        )
    except KeyboardInterrupt:
        stop_event.set()

    stop_event.set()
    loop_thread.join(timeout=5)
    logger.info("Daemon ukoncen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
