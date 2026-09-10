"""Vlastni toast okno (vpravo nahore, samo zmizi) - MIMO notifikacni centrum.

Neni to systemova notifikace: je to nase bezrameckove okno vzdy navrchu.

Pouziti:
    pythonw show_toast.py <cesta_k_textovemu_souboru> [trvani_s]

Textovy soubor (UTF-8): prvni radek = nadpis, zbytek = telo.
Soubor se po precteni smaze.
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path

WIDTH = 480
MARGIN = 20
PAD = 20
RADIUS = 20
DEFAULT_DURATION_S = 60  # notifikace zustane 1 minutu

# Cilova viditelnost (0.9 = 90 % viditelne, mirne pruhledne).
TARGET_ALPHA = 0.9
# Animace fade-in/out (pocet kroku * interval = delka animace v ms).
FADE_STEPS = 25
FADE_INTERVAL_MS = 20

BG = "#1e1e2e"
FG = "#f2f2f7"
ACCENT = "#89b4fa"
# Zvyraznene zmeny (stejne jako mrizka rozvrhu: zluta s tmavym textem).
HIGHLIGHT_BG = "#ffe08a"
HIGHLIGHT_FG = "#7a4d00"
# Osobni poznamka - zelene.
NOTE_FG = "#4ecb83"
LABEL_FG = "#b8b8c8"  # popisky poli (tlumene)
# Barva, ktera bude pruhledna (nesmi se vyskytovat v panelu/textu).
TRANSPARENT = "#ff00ff"


def _read_data(path: Path) -> dict:
    """Nacte strukturovana data (JSON) pro toast; soubor po precteni smaze."""
    text = path.read_text(encoding="utf-8")
    try:
        path.unlink()
    except OSError:
        pass
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"kind": "end"}
    except (json.JSONDecodeError, ValueError):
        # Zpetna kompatibilita: prosty text (prvni radek = nadpis).
        lines = text.splitlines()
        return {"kind": "text", "header": lines[0] if lines else "",
                "body": "\n".join(lines[1:])}


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw):
    """Nakresli zaobleny obdelnik (vyhlazeny polygon)."""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kw)


def _set_alpha(root: tk.Tk, value: float) -> None:
    try:
        root.attributes("-alpha", max(0.0, min(1.0, value)))
    except tk.TclError:
        pass


def _fade(root: tk.Tk, start: float, end: float, done=None) -> None:
    """Plynule zmeni pruhlednost z `start` na `end`, pak zavola `done`."""
    delta = (end - start) / FADE_STEPS

    def step(i: int) -> None:
        if not root.winfo_exists():
            return
        _set_alpha(root, start + delta * i)
        if i < FADE_STEPS:
            root.after(FADE_INTERVAL_MS, lambda: step(i + 1))
        elif done is not None:
            done()

    step(0)


def _build_header(data: dict) -> str:
    kind = data.get("kind")
    if kind == "end":
        return "Konec vyučování"
    if kind == "text":
        return data.get("header", "")
    if kind == "grade":
        return "📊 Nová známka"
    return f"Další hodina začíná v {data.get('start', '?')}"


def show(data: dict, duration_s: int) -> None:
    root = tk.Tk()
    root.overrideredirect(True)        # bez ramecku/titulku
    root.attributes("-topmost", True)  # vzdy navrchu
    try:
        # Pruhledne pozadi okna -> viditelny zustane jen zaobleny panel.
        root.attributes("-transparentcolor", TRANSPARENT)
    except tk.TclError:
        pass
    root.config(bg=TRANSPARENT)
    _set_alpha(root, 0.0)  # start neviditelny (fade-in)

    canvas = tk.Canvas(root, width=WIDTH, bg=TRANSPARENT, highlightthickness=0)
    canvas.pack()

    font = ("Segoe UI", 11)
    font_bold = ("Segoe UI", 11, "bold")
    text_w = WIDTH - 2 * PAD
    y = PAD

    header = _build_header(data)
    if header:
        h_item = canvas.create_text(
            PAD, y, text=header, fill=ACCENT, font=("Segoe UI", 12, "bold"),
            width=text_w, anchor="nw", justify="left",
        )
        y = canvas.bbox(h_item)[3]

    def row(label: str, value: str, highlight: bool) -> None:
        """Radek 'popisek: hodnota'; zmenenou hodnotu zvyrazni jako v rozvrhu."""
        nonlocal y
        y += 8
        lbl = canvas.create_text(PAD, y, text=label, fill=LABEL_FG, font=font,
                                 anchor="nw")
        vx = canvas.bbox(lbl)[2] + 6
        val = canvas.create_text(
            vx, y, text=value,
            fill=HIGHLIGHT_FG if highlight else FG,
            font=font_bold if highlight else font,
            anchor="nw", width=text_w - (vx - PAD),
        )
        bx = canvas.bbox(val)
        if highlight:
            rect = canvas.create_rectangle(
                bx[0] - 4, bx[1] - 1, bx[2] + 4, bx[3] + 1,
                fill=HIGHLIGHT_BG, outline="",
            )
            canvas.tag_lower(rect, val)  # zvyrazneni za text, text navrch
        y = bx[3]

    if data.get("kind") == "text":
        body = data.get("body", "")
        if body:
            y += 8
            b_item = canvas.create_text(PAD, y, text=body, fill=FG, font=font,
                                        width=text_w, anchor="nw", justify="left")
            y = canvas.bbox(b_item)[3]
    elif data.get("kind") == "grade":
        row("Předmět:", data.get("subject") or "?", False)
        row("Známka:", data.get("value") or "?", True)  # zvyraznene (vypichnout)
        title = data.get("title")
        if title:
            row("Za:", title, False)
        weight = data.get("weight")
        try:
            w = float(weight)
            if w and w != 1.0:  # vahu ukaz jen kdyz neni bezna (1)
                row("Váha:", str(int(w)) if w.is_integer() else str(w), False)
        except (TypeError, ValueError):
            pass
    elif data.get("kind") != "end":
        changes = set(data.get("changes") or [])
        row("Předmět:", data.get("subject", "?"), "subject" in changes)
        row("Učebna:", data.get("room", "?"), "room" in changes)
        row("Vyučující:", data.get("teacher", "?"), "teacher" in changes)

        note = data.get("note")
        if note:
            y += 8
            prefix = "⏳ " if data.get("note_pending") else ""
            n_item = canvas.create_text(
                PAD, y, text=f"{prefix}📝 {note}", fill=NOTE_FG, font=font_bold,
                width=text_w, anchor="nw", justify="left",
            )
            y = canvas.bbox(n_item)[3]

    height = y + PAD

    # Zaobleny panel pod text.
    panel = _round_rect(canvas, 1, 1, WIDTH - 1, height - 1, RADIUS,
                        fill=BG, outline=ACCENT, width=1)
    canvas.tag_lower(panel)  # panel uplne dozadu (text i zvyrazneni navrch)
    canvas.config(height=height)

    # Umisteni vpravo nahore.
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    x = screen_w - WIDTH - MARGIN
    root.geometry(f"{WIDTH}x{height}+{x}+{MARGIN}")

    # Vynutit prvni vykresleni jeste neviditelne (alfa 0), aby byl fade-in videt.
    _set_alpha(root, 0.0)
    root.update()

    # Fade-in pri zobrazeni.
    _fade(root, 0.0, TARGET_ALPHA)

    def close() -> None:
        if root.winfo_exists():
            _fade(root, TARGET_ALPHA, 0.0, done=root.destroy)

    # Zavreni: klik (okamzity fade-out) nebo po uplynuti casu.
    root.bind("<Button-1>", lambda _e: close())
    canvas.bind("<Button-1>", lambda _e: close())
    # Po uplynuti doby spustit fade-out (odectena delka animace).
    fade_ms = FADE_STEPS * FADE_INTERVAL_MS
    root.after(max(1, duration_s * 1000 - fade_ms), close)

    root.mainloop()


def main(argv: list[str]) -> int:
    if not argv:
        return 1
    path = Path(argv[0])
    if not path.exists():
        return 1
    duration = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else DEFAULT_DURATION_S
    data = _read_data(path)
    show(data, duration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
