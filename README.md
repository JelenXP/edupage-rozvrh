# 📅 EduPage rozvrh

> Tiše běžící Windows program na pozadí, který drží tvůj EduPage rozvrh vždy po ruce – i offline – a přidává věci, které EduPage neumí.

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Postaveno na](https://img.shields.io/badge/postaveno%20na-edupage--api-orange)
![Údržba](https://img.shields.io/badge/auto--update-git-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

Daemon každou hodinu stáhne rozvrh do sdílené cache, umí otevírat složky předmětů
při začátku hodiny, ukazuje toast notifikaci s další hodinou, zobrazuje celý
rozvrh v prohlížeči (funguje i offline) a nechá tě přímo v něm **číst i psát
osobní poznámky k hodinám**. Nové verze kódu se rozdají všem uživatelům **samy
přes git**.

---

## ✨ Funkce

- 🕒 **Automatické stahování** rozvrhu na několik týdnů dopředu (každou hodinu) do
  sdílené cache. Funguje **offline** – když spadne připojení, jede se z poslední
  stažené verze a cache se nepřepíše.
- 🗂️ **Otevírání složek předmětů** v Průzkumníku na začátku (nebo v průběhu)
  hodiny – zapínatelné per účet.
- 🔔 **Toast notifikace** na konci hodiny s další hodinou (vlastní okno, **mimo**
  centrum oznámení Windows). Zůstane 1 minutu, **zvýrazní změny** a ukáže **poznámku**.
- 📊 **Notifikace na nové známky** (volitelné, `notify_grades`) – toast vpravo
  nahoře při nové známce (předmět, hodnota, název, váha).
- 📝 **Osobní poznámky k hodinám** – čtení i **zápis/úprava/mazání** přímo v
  rozvrhu (ukládají se zpět do EduPage). Offline se zařadí do fronty a odešlou se,
  až bude připojení.
- 🟧 **DÚ a testy**, **suplování**, odpadlé/přesunuté hodiny a **celodenní události**
  (svátky/volno) přímo v mřížce rozvrhu.
- 🔍 **Detekce změn** proti „stálému" rozvrhu – zvýrazní se jen to, co se liší.
- ⚡ **Rychlé stahování** – po 3denních oknech na málo requestů + znovupoužitá
  přihlášená session (aktualizace i ukládání poznámek nečekají na login).
- 🔄 **Auto-update z GitHubu** – daemon si sám stáhne novou verzi kódu a restartuje se.
- 🖱️ **Ikona v liště** – *Zobrazit rozvrh / Nastavení / Stáhnout teď / Restart / Otevřít log / Ukončit*.
- ⚙ **Nastavení klikáním** – přepínače funkcí přímo v rozvrhu i v samostatném okně
  z lišty (bez ručního editování `config.json`).

---

## 🚀 Instalace

**Požadavky:** Windows, [Python 3.10+](https://www.python.org/downloads/) a
[Git](https://git-scm.com/download/win).

```bash
git clone https://github.com/JelenXP/edupage-rozvrh.git
cd edupage-rozvrh
python -m pip install edupage-api pystray pillow
```

> `pystray` + `pillow` jsou jen pro ikonu v liště – bez nich daemon poběží taky,
> jen bez ikony.

Vytvoř si konfiguraci (uloží se mimo repo, do tvého profilu – hesla se nikdy
necommitují):

```bash
python setup_user_config.py
```

Zapni autostart:

```bash
python install_autostart.py
```

Hotovo – program teď běží po přihlášení do Windows a rozvrh máš vždy aktuální.

> **Při prvním spuštění** se automaticky otevře rozvrh s panelem **⚙ Nastavení**,
> kde si klikáním zapneš notifikace, otevírání složek a další funkce – nemusíš
> editovat žádný soubor.

---

## ⚙️ Konfigurace

Nastavení změníš klikáním – **nemusíš editovat JSON ručně:**
- v rozvrhu tlačítkem **⚙ Nastavení** (přepínače + cesta ke složkám),
- nebo přes **ikonu v liště → Nastavení** (samostatné okno).

Uložením se změny zapíšou do configu (hesla se nikdy nemění) a daemon se sám
restartuje, aby se projevily.

<details>
<summary>Ruční editace configu (pokročilé)</summary>

Soubor `%LOCALAPPDATA%\edupage\config.json` (vzor je `config.example.json`):

```json
{
  "username": "tve_uzivatelske_jmeno",
  "password": "tveHeslo",
  "subdomain": "gymxy",
  "open_folders": false,
  "folders_base": "C:\\cesta\\ke\\slozkam\\predmetu",
  "notify_next_lesson": false,
  "notify_grades": false,
  "auto_update": true
}
```

| Klíč | Popis |
|------|-------|
| `username`, `password` | Přihlašovací údaje do EduPage. |
| `subdomain` | Poddoména školy (`https://<subdomain>.edupage.org`). |
| `open_folders` | `true` → otevírá složku předmětu při hodině. |
| `folders_base` | Kořenová složka s podsložkami předmětů (jen když `open_folders`). |
| `notify_next_lesson` | `true` → toast s další hodinou na konci hodiny. |
| `notify_grades` | `true` → toast při nové známce (vpravo nahoře, 1 min / po odkliknutí). |
| `auto_update` | `true` → daemon se sám aktualizuje z gitu (doporučeno). |

> **Nové klíče se doplní samy.** Chybějící volitelné klíče (např. `notify_grades`
> po updatu) se při startu automaticky přidají do `config.json` s výchozí hodnotou
> `false` – existující hodnoty ani pořadí se nemění, starý config se nerozbije.

</details>

Volitelně `%LOCALAPPDATA%\edupage\subject_folders.json` – ruční mapování jen těch
předmětů, jejichž složka se **nejmenuje stejně** jako předmět (zbytek se páruje 1:1).

---

## 🖥️ Použití

- **Celý rozvrh:** `python show_timetable.py` (nebo v liště *Zobrazit rozvrh*,
  případně dvojklik na ikonu). Mřížka s přepínáním týdnů, funguje offline. Otevře
  se hned z cache a na pozadí se sám přenačte na aktuální data. Listovat dopředu
  jde bez omezení – nestažený týden se **sám dotáhne**.
- **Poznámky:** klikni na „＋ poznámka" (nebo na existující zelený text) u hodiny,
  napiš text a **Ulož**. Uloží se zpět do EduPage; offline se zařadí do fronty a
  ukáže s odznakem „⏳ čeká na odeslání".
- **Ruční stažení:** tlačítko *⟳ Aktualizovat* v rozvrhu nebo *Stáhnout teď* v liště.
- **Jednorázový test:** `python edupage_daemon.py --once`
- **Log:** `C:\Users\Public\edupage_schedule\daemon.log`
- **Zrušení autostartu:** `python uninstall_autostart.py`

Běžící daemon je ve Správci úloh jako `pythonw.exe`.

---

## 🔄 Auto-update

Daemon si při startu a jednou za hodinu udělá `git pull`; když přišly změny,
**sám se restartuje** na nový kód. Stačí tedy vydat novou verzi a všem se sama
nasadí (do hodiny, nebo hned po restartu jejich daemonu):

```bash
git commit -am "popis změny"
git push
```

- **Bezpečné pro vývoj:** update proběhne jen když je pracovní strom **čistý** a
  remote je **napřed** (fast-forward). Rozdělané nebo nepushnuté změny se
  nepřepíšou – auto-update se přeskočí.
- **Vypnutí:** `"auto_update": false` v configu.

---

## 🏫 Sdílená složka / dva účty na jednom PC

Projekt umí běžet z **jedné složky s kódem pro víc Windows účtů** (např. domácí +
školní účet). Kód je společný, každý účet má **vlastní config** ve svém profilu
(`%LOCALAPPDATA%\edupage\`), takže se nic nekopíruje.

<details>
<summary>Nastavení druhého (např. školního) účtu</summary>

1. Knihovny pro Python daného účtu: `python -m pip install edupage-api pystray pillow`
2. `python C:\Programování\edupage\setup_user_config.py`
3. Uprav `%LOCALAPPDATA%\edupage\config.json` (typicky `open_folders: true`,
   `folders_base`, `notify_next_lesson: true`) a případně `subject_folders.json`.
4. `python C:\Programování\edupage\install_autostart.py`
5. Ukonči starý daemon (Správce úloh → `pythonw.exe`) nebo restartuj PC.

**Sdílená cache:** `C:\Users\Public\edupage_schedule\schedule.json` vidí oba účty –
fetch z jednoho účtu tak drží rozvrh čerstvý i pro druhý (i když je zrovna offline).
</details>

---

## 📁 Struktura projektu

| Soubor | Popis |
|--------|-------|
| `edupage_daemon.py` | Trvalý běh: fetch, otevírání složek, notifikace, ikona v liště. |
| `edupage_fetch.py` | Jádro: config, přihlášení, stažení, cache, poznámky. |
| `control_server.py` | Lokální server (127.0.0.1) pro *Aktualizovat*, dotažení týdnů a ukládání poznámek. |
| `show_timetable.py` | Vygeneruje a otevře rozvrh jako mřížku v prohlížeči (offline). |
| `show_toast.py` | Vlastní toast okno mimo centrum oznámení. |
| `notifier.py` | Logika „další hodina" + obsah notifikace. |
| `folder_opener.py` | Mapování předmět→složka a otevření probíhající hodiny. |
| `tray_icon.py` | Ikona v systémové liště (volitelné, `pystray` + `pillow`). |
| `self_update.py` | Auto-aktualizace kódu z gitu. |
| `settings_window.py` | Nativní okno nastavení (z lišty → Nastavení). |
| `setup_user_config.py` | Připraví per-user config v `%LOCALAPPDATA%\edupage\`. |
| `install_autostart.py` / `uninstall_autostart.py` | (Od)registrace autostartu. |
| `config.example.json`, `subject_folders.example.json` | Vzory konfigurace. |

---

## 🛠️ Řešení potíží

- **Mizí poznámky / „＋ poznámka"?** Nejspíš běží daemon jiného účtu na **staré
  verzi kódu** a přepisuje sdílenou cache. Restartuj jeho daemon (Správce úloh →
  `pythonw.exe`, nebo restart PC). Ukládání poznámek stránka posílá jen na daemon,
  který je umí (podle `/ping`).
- **Rozvrh se neaktualizuje:** mrkni do logu
  `C:\Users\Public\edupage_schedule\daemon.log`. Neúspěšné stažení (offline) se
  automaticky zopakuje za 5 minut.
- **Daemon neběží:** ověř `pythonw.exe` ve Správci úloh; jinak spusť ručně
  `pythonw edupage_daemon.py` nebo znovu `python install_autostart.py`.
- **Dvojfázové ověření (2FA):** účty s 2FA zatím nejsou podporované.

---

## 📄 Licence

Vydáno pod licencí **MIT** – viz [LICENSE](LICENSE). Volně k použití a úpravám.

Postaveno na knihovně [edupage-api](https://github.com/EduPage-API/edupage-api).
Neoficiální nástroj, nijak nesouvisí s provozovatelem EduPage.
