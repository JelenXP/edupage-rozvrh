"""Maly lokalni HTTP server (jen 127.0.0.1) pro tlacitko "Aktualizovat".

Stranka rozvrhu (file://) na nej zaklepe -> stahne se aktualni rozvrh a prepise
se HTML, stranka se pak prenacte. Bez tohoto serveru tlacitko jen ohlasi, ze
aplikace na pozadi nebezi.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

import edupage_fetch as core


# --- Progresivni refresh (tlacitko ⟳) ----------------------------------------
# Refresh bezi na pozadi a stahuje tyden po tydnu (zobrazeny prvni). Stav sleduje
# stranka pres /refresh_status a po kazdem dokoncenem tydnu se prenacte, takze
# vysledky pribyvaji postupne misto cekani na cely rozsah.
_refresh_lock = threading.Lock()
_refresh_state = {"active": False, "done": 0, "total": 0}


def _rewrite_html(logger) -> None:
    try:
        import show_timetable
        show_timetable._write_html(pending=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("Prepsani rozvrhu selhalo: %s", e)


def _start_progressive(target_monday, logger) -> None:
    """Spusti progresivni refresh na pozadi (pokud uz nebezi)."""
    with _refresh_lock:
        if _refresh_state["active"]:
            return  # uz bezi - stranka jen doceka pres /refresh_status
        weeks = core.refresh_weeks(target_monday)
        _refresh_state.update(active=True, done=0, total=len(weeks))

    def worker() -> None:
        try:
            try:
                edupage = core.get_session()
            except Exception as e:  # noqa: BLE001 - offline / 2FA
                logger.warning("Refresh: prihlaseni selhalo: %s", e)
                return
            try:
                core.flush_note_queue(edupage)
            except Exception:  # noqa: BLE001
                pass
            for w in weeks:
                try:
                    if not core.fetch_week_with(edupage, w):
                        # mozna vyprsela session -> jeden pokus s cerstvym prihlasenim
                        edupage = core.get_session(force_new=True)
                        core.fetch_week_with(edupage, w)
                except Exception as e:  # noqa: BLE001 - jeden tyden nesmi shodit refresh
                    logger.warning("Refresh tydne %s selhal: %s", w, e)
                with _refresh_lock:
                    _refresh_state["done"] += 1
                _rewrite_html(logger)  # po kazdem tydnu prepsat HTML (stranka se prenacte)
        finally:
            with _refresh_lock:
                _refresh_state["active"] = False

    threading.Thread(target=worker, daemon=True).start()


class _Server(ThreadingHTTPServer):
    # NEsdilet port: kdyz uz na nem nekdo naslouchá (napr. daemon druheho
    # Windows uctu), bind selze a zkusi se dalsi port. Diky tomu kazdy ucet
    # dostane vlastni port a nepresmerovavaji si navzajem requesty.
    allow_reuse_address = False


def _make_handler(logger, on_restart=None):
    import secrets

    # Token nacteme jednou pri startu serveru (stejny, jaky vkladame do HTML).
    # Sensitivni endpointy jim overuji volajiciho - cizi web v prohlizeci token
    # nezna, takze i kdyz na 127.0.0.1 dosahne, neprojde.
    token = core.get_control_token()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes = b"") -> None:
            self.send_response(code)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _token_ok(self, provided) -> bool:
            """Bezpecne porovnani tokenu (konstantni cas). Prazdny = neplatny."""
            return bool(provided) and secrets.compare_digest(str(provided), token)

        def _rewrite(self):
            _rewrite_html(logger)

        def do_GET(self):  # noqa: N802
            q = parse_qs(urlparse(self.path).query)
            # /ping a /refresh_status jsou neskodne (jen stav/schopnosti) - bez tokenu.
            # Vse ostatni (stahovani, config) vyzaduje platny token.
            if not (self.path.startswith("/ping")
                    or self.path.startswith("/refresh_status")):
                if not self._token_ok((q.get("token") or [None])[0]):
                    self._send(403, b'{"ok":false,"error":"forbidden"}')
                    return

            if self.path.startswith("/refresh_status"):
                # Stav progresivniho refreshe (stranka podle nej prenacita).
                with _refresh_lock:
                    st = dict(_refresh_state)
                self._send(200, json.dumps(st).encode())
            elif self.path.startswith("/refresh"):
                # ?until=YYYY-MM-DD -> progresivne obnovi vsechny tydny od tohoto
                # tydne az po zobrazeny (zobrazeny prvni). Bez parametru = bezne okno.
                until = (q.get("until") or [None])[0]
                if until:
                    try:
                        y, m, d = map(int, until.split("-"))
                        _start_progressive(date(y, m, d), logger)
                        self._send(200, b'{"ok":true,"async":true}')
                    except (ValueError, TypeError):
                        self._send(200, b'{"ok":false}')
                else:
                    ok = core.refresh_cache()
                    self._rewrite()
                    self._send(200, b'{"ok":true}' if ok else b'{"ok":false}')
            elif self.path.startswith("/fetch_week"):
                # ?monday=YYYY-MM-DD -> stahne dany tyden na vyzadani
                md = (q.get("monday") or [None])[0]
                ok = False
                if md:
                    try:
                        y, m, d = map(int, md.split("-"))
                        ok = core.fetch_week(date(y, m, d))
                    except (ValueError, TypeError):
                        ok = False
                self._rewrite()
                self._send(200, b'{"ok":true}' if ok else b'{"ok":false}')
            elif self.path.startswith("/config"):
                # Aktualni hodnoty nastavitelnych voleb (pro UI nastaveni).
                try:
                    vals = core.get_config_values()
                except Exception:  # noqa: BLE001
                    vals = {}
                self._send(200, json.dumps({"ok": True, "config": vals}).encode())
            elif self.path.startswith("/ping"):
                # "notes":true = tento daemon umi ukladat poznamky (novy kod).
                # "config":true = umi UI nastaveni (/config, /set_config).
                self._send(200, b'{"ok":true,"notes":true,"config":true}')
            else:
                self._send(404)

        def do_POST(self):  # noqa: N802
            if self.path.startswith("/save_note"):
                # Telo JSON: {date:"YYYY-MM-DD", period:int, text:str}
                # (text/plain => "simple request", bez CORS preflightu)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                status = "failed"
                try:
                    p = json.loads(raw.decode("utf-8"))
                    if not self._token_ok(p.get("token")):
                        self._send(403, b'{"ok":false,"error":"forbidden"}')
                        return
                    status = core.save_note(
                        str(p.get("date")), int(p.get("period")), str(p.get("text") or "")
                    )
                except (ValueError, TypeError, json.JSONDecodeError):
                    status = "failed"
                # "saved" i "queued" upravily cache -> prepsat HTML.
                if status in ("saved", "queued"):
                    self._rewrite()
                bodies = {
                    "saved": b'{"ok":true}',
                    "queued": b'{"ok":false,"queued":true}',
                    "failed": b'{"ok":false}',
                }
                self._send(200, bodies.get(status, b'{"ok":false}'))
            elif self.path.startswith("/set_config"):
                # Telo JSON: nastavitelne volby (open_folders, notify_*, auto_update,
                # folders_base). Ulozi do config.json a restartuje daemon, aby se
                # zmeny projevily. NIKDY nemeni username/password/subdomain.
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    changes = json.loads(raw.decode("utf-8"))
                    if not (isinstance(changes, dict) and self._token_ok(changes.get("token"))):
                        self._send(403, b'{"ok":false,"error":"forbidden"}')
                        return
                    vals = core.save_config_values(changes)
                    self._send(200, json.dumps({"ok": True, "config": vals}).encode())
                    # Po odeslani odpovedi restartovat (zmeny se ctou pri startu).
                    if on_restart is not None:
                        threading.Timer(0.8, on_restart).start()
                except (ValueError, TypeError, json.JSONDecodeError, OSError) as e:
                    logger.warning("Ulozeni nastaveni selhalo: %s", e)
                    self._send(200, b'{"ok":false}')
            else:
                self._send(404)

        def do_OPTIONS(self):  # noqa: N802 - CORS preflight (kdyby ho prohlizec poslal)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def log_message(self, *args):  # ticho (zadny stdout)
            pass

    return Handler


def start(logger, on_restart=None) -> Optional[int]:
    """Spusti server na prvnim volnem portu z rozsahu. Vrati port, nebo None.

    `on_restart` = callback pro restart daemonu po ulozeni nastaveni (/set_config).
    """
    handler = _make_handler(logger, on_restart)
    for port in range(core.CONTROL_PORT_BASE,
                       core.CONTROL_PORT_BASE + core.CONTROL_PORT_COUNT):
        try:
            srv = _Server(("127.0.0.1", port), handler)
        except OSError:
            continue
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        logger.info("Control server bezi na 127.0.0.1:%d", port)
        return port
    logger.warning("Control server se nepodarilo spustit (porty obsazeny).")
    return None
