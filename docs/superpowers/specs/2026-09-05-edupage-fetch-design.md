# EduPage rozvrh – fetch (fáze 1)

**Datum:** 2026-09-05
**Stav:** schváleno uživatelem

## Cíl

Spustitelný Python skript, který se přihlásí do EduPage, stáhne rozvrh přihlášeného
uživatele na 3 týdny dopředu, přehledně ho vypíše do konzole a uloží do dočasné
cache. Kód je strukturovaný tak, aby na něj šlo později navázat:

- **Fáze 2 (později):** tichý běh na pozadí ve Windows, stahování každou hodinu
  (Task Scheduler / spuštění po startu).
- **Fáze 3 (později):** při začátku každé hodiny otevřít v Průzkumníku složku
  s daným předmětem.

Tento spec pokrývá **jen fázi 1**.

## Knihovna

`edupage-api` 0.12.5 (nainstalováno, funguje na Pythonu 3.14).

Klíčové API:
- `Edupage().login(username, password, subdomain)` – přihlášení; vrací `None`,
  nebo `TwoFactorLogin` když účet vyžaduje 2FA.
- `edupage.get_my_timetable(date)` – rozvrh přihlášeného uživatele pro **jeden den**.
  Pro 3 týdny se iteruje den po dni.
- `Lesson`: `period`, `start_time`, `end_time`, `subject` (`.name`), `teachers`,
  `classrooms`, `is_cancelled`.

## Soubory

| Soubor | Účel |
|--------|------|
| `config.json` | Uživatelem vyplněné `username`, `password`, `subdomain`. Negituje se. |
| `config.example.json` | Vzor pro `config.json`. |
| `edupage_fetch.py` | Jádro: načtení configu, přihlášení, smyčka přes dny (dnešek → +21 dní), sběr lekcí, uložení cache. Bez print výstupu (znovupoužitelné pro fázi 2). |
| `fetch_schedule.py` | Entry point: zavolá jádro, vypíše rozvrh po dnech, uloží cache. |
| `.gitignore` | Ignoruje `config.json` a cache. |

## Datový tok

1. `fetch_schedule.py` načte `config.json` (chybějící/nevyplněný → jasná hláška, konec).
2. Přihlášení přes `edupage-api`.
3. Pro každý den v rozsahu dnešek..+21 dní (přeskoč soboty/neděle):
   - `get_my_timetable(date)`; prázdný den se tiše přeskočí.
   - Lekce se serializují do jednoduchého dictu (den, čas, předmět, učebna, učitel, zrušeno).
4. Výsledek se uloží jako JSON do cache a vypíše se do konzole seskupený po dnech.

## Cache

`%LOCALAPPDATA%\Temp\edupage_schedule\schedule.json` – „dočasně stažený" rozvrh.
Přepisuje se při každém běhu. Obsahuje `fetched_at` a seznam lekcí.

## Ošetření chyb

- Chybějící / nevyplněný `config.json` → srozumitelná instrukce co doplnit.
- Selhání přihlášení → čitelná chyba, ne traceback.
- 2FA: pokud `login` vrátí `TwoFactorLogin`, skript to oznámí (doladíme dle potřeby).
- Chyba stažení jednoho dne se zaloguje a pokračuje se dál.

## Mimo rozsah (fáze 1)

Běh na pozadí, plánování, otevírání složek předmětů.
