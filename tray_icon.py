"""Ikona v systemove liste (tray) pro ovladani daemonu.

Volitelne - pokud neni nainstalovano pystray/Pillow, daemon bezi bez ikony.
Nabidka: Stahnout ted / Otevrit log / Ukoncit.
"""

from __future__ import annotations

from typing import Callable


def create_image():
    """Jednoducha ikona: modry kruh s 'E'."""
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, size - 6, size - 6), fill="#89b4fa")
    d.text((size // 2, size // 2), "E", fill="#1e1e2e", anchor="mm")
    return img


def run_tray(
    on_fetch_now: Callable[[], None],
    on_quit: Callable[[], None],
    on_open_log: Callable[[], None],
    on_show_timetable: Callable[[], None],
    on_restart: Callable[[], None],
) -> None:
    """Zobrazi ikonu a blokuje az do 'Ukoncit'. Musi bezet na hlavnim vlakne."""
    import pystray
    from pystray import Menu, MenuItem

    def _timetable(icon, _item):
        on_show_timetable()

    def _fetch(icon, _item):
        on_fetch_now()

    def _log(icon, _item):
        on_open_log()

    def _restart(icon, _item):
        icon.visible = False
        icon.stop()  # ukonci run() -> main dobehne a proces skonci (uvolni mutex)
        on_restart()

    def _quit(icon, _item):
        icon.visible = False
        icon.stop()
        on_quit()

    icon = pystray.Icon(
        "edupage_rozvrh",
        create_image(),
        "EduPage rozvrh",
        menu=Menu(
            MenuItem("Zobrazit rozvrh", _timetable, default=True),
            MenuItem("Stáhnout teď", _fetch),
            MenuItem("Restart", _restart),
            MenuItem("Otevřít log", _log),
            MenuItem("Ukončit", _quit),
        ),
    )
    icon.run()
