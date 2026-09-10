"""Nativni okno nastaveni (tkinter) - pro uzivatele, kteri nechteji rucne
upravovat config.json.

Spousti se z ikony v liste (tray -> Nastaveni) jako samostatny proces. Mluvi s
lokalnim serverem daemonu (127.0.0.1) - nacte aktualni nastaveni z /config a
ulozi pres /set_config (server pak daemon restartuje, aby se zmeny projevily).
Nikdy nesaha na username/password (ty server menit neumi).
"""

from __future__ import annotations

import json
import sys
import urllib.request
import tkinter as tk
from tkinter import messagebox

import edupage_fetch as core

_PORTS = list(range(core.CONTROL_PORT_BASE,
                    core.CONTROL_PORT_BASE + core.CONTROL_PORT_COUNT))


def _get_json(url: str, timeout: float = 3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_json(url: str, data: dict, timeout: float = 8):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _find_port():
    """Najde port daemonu, ktery umi nastaveni (/ping -> config:true)."""
    for p in _PORTS:
        try:
            j = _get_json(f"http://127.0.0.1:{p}/ping", timeout=1.5)
            if j.get("config"):
                return p
        except Exception:  # noqa: BLE001
            continue
    return None


def main() -> int:
    root = tk.Tk()
    root.title("Nastavení – EduPage rozvrh")
    root.resizable(False, False)

    port = _find_port()
    if port is None:
        messagebox.showerror(
            "Nastavení",
            "Aplikace na pozadí (daemon) neběží, nebo je na staré verzi.\n"
            "Spusť ji a zkus to znovu.",
        )
        root.destroy()
        return 1

    try:
        cfg = _get_json(f"http://127.0.0.1:{port}/config").get("config", {})
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Nastavení", f"Nepodařilo se načíst nastavení:\n{e}")
        root.destroy()
        return 1

    pad = {"padx": 14, "pady": 4}
    tk.Label(root, text="Nastavení", font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 6))

    v_next = tk.BooleanVar(value=bool(cfg.get("notify_next_lesson")))
    v_grades = tk.BooleanVar(value=bool(cfg.get("notify_grades")))
    v_folders = tk.BooleanVar(value=bool(cfg.get("open_folders")))
    v_auto = tk.BooleanVar(value=bool(cfg.get("auto_update")))

    tk.Checkbutton(root, text="Notifikace další hodiny (na konci hodiny)",
                   variable=v_next).grid(row=1, column=0, columnspan=2, sticky="w", **pad)
    tk.Checkbutton(root, text="Notifikace nových známek",
                   variable=v_grades).grid(row=2, column=0, columnspan=2, sticky="w", **pad)
    tk.Checkbutton(root, text="Otevírat složky předmětů (při začátku hodiny)",
                   variable=v_folders).grid(row=3, column=0, columnspan=2, sticky="w", **pad)

    tk.Label(root, text="Cesta ke složkám předmětů:").grid(
        row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 0))
    e_base = tk.Entry(root, width=46)
    e_base.insert(0, cfg.get("folders_base") or "")
    e_base.grid(row=5, column=0, columnspan=2, sticky="we", padx=14, pady=(0, 4))

    tk.Checkbutton(root, text="Automatické aktualizace programu (doporučeno)",
                   variable=v_auto).grid(row=6, column=0, columnspan=2, sticky="w", **pad)

    status = tk.Label(root, text="", fg="#2f7d32")
    status.grid(row=7, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 0))

    def do_save():
        payload = {
            "notify_next_lesson": v_next.get(),
            "notify_grades": v_grades.get(),
            "open_folders": v_folders.get(),
            "auto_update": v_auto.get(),
            "folders_base": e_base.get().strip(),
        }
        status.config(text="Ukládám…")
        root.update_idletasks()
        try:
            j = _post_json(f"http://127.0.0.1:{port}/set_config", payload)
        except Exception as e:  # noqa: BLE001
            status.config(text=f"Uložení selhalo: {e}", fg="#c62828")
            return
        if j.get("ok"):
            status.config(text="Uloženo – aplikace se restartuje.", fg="#2f7d32")
            root.after(1400, root.destroy)
        else:
            status.config(text="Uložení selhalo.", fg="#c62828")

    btns = tk.Frame(root)
    btns.grid(row=8, column=0, columnspan=2, sticky="e", padx=14, pady=12)
    tk.Button(btns, text="Zrušit", command=root.destroy, width=10).pack(side="left", padx=(0, 8))
    tk.Button(btns, text="Uložit", command=do_save, width=12,
              default="active").pack(side="left")

    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"+{x}+{y}")
    root.attributes("-topmost", True)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
