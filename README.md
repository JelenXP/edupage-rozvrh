# EduPage rozvrh – automatické stahování + otevírání složek

Tiše běžící program na pozadí (Windows), který:

1. **Stahuje rozvrh** na 3 týdny dopředu z EduPage (každou hodinu) do sdílené cache.
2. **Otevírá složku předmětu** v Průzkumníku při začátku (nebo v průběhu) každé
   hodiny – jen na účtu, kde to zapneš.
3. **Zobrazuje toast notifikaci** na konci každé hodiny s údaji o další hodině
   (vlastní okno vpravo nahoře, **mimo** notifikační centrum Windows). Zůstane
   **1 minutu**, **zvýrazní změny** (předmět/učitel/učebna – stejně jako rozvrh)
   a ukáže i **osobní poznámku** k hodině (zeleně).

## Architektura

- **Sdílená cache:** `C:\Users\Public\edupage_schedule\schedule.json` – vidí ji
  oba uživatelé. Fetch z domácího účtu tak drží rozvrh čerstvý i pro školní účet,
  který může být ve škole offline.
- **Jeden daemon, dva režimy** – řídí `config.json`:
  - `"open_folders": false` → jen stahuje (domácí/programovací účet).
  - `"open_folders": true` + `"folders_base"` → stahuje **a** otevírá složky (školní účet).
  - `"notify_next_lesson": true` → na konci hodiny ukáže toast s další hodinou (školní účet).
- Když stažení selže (offline), cache se **nepřepíše** → otevírání jede z posledního
  dostupného rozvrhu. Neúspěšný pokus se navíc zopakuje už za 5 minut (ne až za hodinu).
- **Rychlé stahování:** rozvrh se stahuje po 3denních oknech na málo requestů
  (endpoint EduPage vrací max 3 dny na dotaz), CSRF token se řeší jen jednou.
  Daemon si navíc **drží přihlášení** v paměti a znovupoužívá ho – aktualizace,
  dotažení dalšího týdne i ukládání poznámek tak nečekají na opakované přihlašování.
- **Ikona v liště** (tray): pravým klikem *Zobrazit rozvrh / Stáhnout teď /
  Restart / Otevřít log / Ukončit*. **Restart** spustí novou instanci daemonu
  (načte aktuální kód) a starou ukončí – hodí se po úpravě kódu.
- Běží vždy **jen jedna instance** (pojistka proti dvojímu spuštění).

## Soubory

| Soubor | Popis |
|--------|-------|
| `edupage_fetch.py` | Jádro: config, přihlášení, stažení, cache. |
| `folder_opener.py` | Mapování předmět→složka, výběr probíhající hodiny, otevření. |
| `notifier.py` | Logika „další hodina" + text zprávy. |
| `show_toast.py` | Vlastní toast okno (mimo notifikační centrum). |
| `tray_icon.py` | Ikona v systémové liště (volitelné, potřebuje `pystray`+`pillow`). |
| `show_timetable.py` | Vygeneruje a otevře celý rozvrh jako mřížku v prohlížeči (offline, přepínání týdnů). |
| `control_server.py` | Lokální server (127.0.0.1) pro *Aktualizovat*, dotažení týdnů a ukládání poznámek. |
| `edupage_daemon.py` | Trvalý běh: fetch (ve vlákně) + kontrola složek a notifikace po minutě, ikona v liště. |
| `install_autostart.py` / `uninstall_autostart.py` | (Od)registrace autostartu. |
| `setup_user_config.py` | Připraví per-user config (`%LOCALAPPDATA%\edupage\`) pro běh ze sdílené složky. |
| `config.json` | Tvoje údaje (vytvoříš z `config.example.json`). Necommituje se. |
| `subject_folders.json` | Ruční mapování výjimek (z `subject_folders.example.json`). |

## Nastavení – domácí (tento) účet

Jen stahování, ať je rozvrh vždy čerstvý.

1. `config.json` už máš. Zkontroluj, že obsahuje `"open_folders": false`.
2. (Volitelně) ikona v liště: `python -m pip install pystray pillow`
3. Autostart:
   ```
   python install_autostart.py
   ```

## Nastavení – školní účet (otevírání složek)

**Žádné kopírování kódu.** Školní účet spouští daemon přímo ze **sdílené složky**
`C:\Programování\edupage` (má na ni práva pro čtení). Každý účet má vlastní config
ve svém profilu (`%LOCALAPPDATA%\edupage\`), takže z jedné složky s kódem běží oba
účty. **Změníš kód jednou → mají ho oba účty** (jen restart daemonů).

Na **školním účtu** (přihlaš se do Windows jako `Škola`) proveď:

1. **Nainstaluj knihovny** (pro Python školního účtu):
   ```
   python -m pip install edupage-api pystray pillow
   ```
   (`pystray` + `pillow` jsou pro ikonu v liště; bez nich daemon poběží bez ikony.)

2. **Vytvoř per-user config** – jedním příkazem ze sdílené složky:
   ```
   python C:\Programování\edupage\setup_user_config.py
   ```
   Vytvoří `%LOCALAPPDATA%\edupage\config.json` a `subject_folders.json` ze vzorů.

3. **Uprav** `%LOCALAPPDATA%\edupage\config.json`:
   ```json
   {
     "username": "...",
     "password": "...",
     "subdomain": "...",
     "open_folders": true,
     "folders_base": "C:\\cesta\\ke\\slozkam\\predmetu",
     "notify_next_lesson": true
   }
   ```
   a případně `%LOCALAPPDATA%\edupage\subject_folders.json` (jen předměty, jejichž
   složka se **nejmenuje stejně** jako předmět; zbytek 1:1).

4. **Autostart ze sdílené složky:**
   ```
   python C:\Programování\edupage\install_autostart.py
   ```
   (Zástupce ve Startup bude ukazovat na `C:\Programování\edupage\edupage_daemon.py`.)

5. **Ukonči starý daemon** (pokud běžel ze staré vlastní složky): Správce úloh →
   ukončit `pythonw.exe`, nebo prostě **restartuj PC**. Po přihlášení se spustí nový
   daemon ze sdílené složky. Starou složku s kódem už můžeš smazat.

## Ověření a ovládání

- **Zobrazit celý rozvrh:** `python show_timetable.py` (nebo v liště *Zobrazit rozvrh*,
  případně dvojklik na ikonu) – mřížka (dny vlevo, hodiny nahoře), přepínání týdnů,
  funguje offline. Otevře se **okamžitě** z cache (badge „aktualizuji…"), na pozadí
  stáhne aktuální rozvrh a stránka se pak **sama přenačte** na aktuální data (zachová
  zobrazený týden). Tlačítko **⟳ Aktualizovat** stáhne rozvrh na vyžádání (klepne na
  lokální server daemonu na `127.0.0.1`). **Listovat dopředu jde bez omezení** – když
  klikneš na týden, který ještě není stažený, **sám se dotáhne** (a v cache zůstane,
  dokud ho běžné okno nedožene). Zobrazuje **DÚ/testy** (oranžově), **suplování**,
  **celodenní události** (svátky/volno) roztažené přes celý den (např. „Svátek: Den
  české státnosti") a **osobní poznámky k hodině** („Moje poznámka" z EduPage) –
  **zeleně**, bez zvýraznění. Poznámku lze **přidat/upravit/smazat** přímo v rozvrhu:
  klikni na „＋ poznámka" (nebo na existující zelený text) u dané hodiny, napiš text a
  **Ulož** – uloží se zpět do EduPage (přes lokální server daemonu na `127.0.0.1`).
  **Offline:** když zrovna není připojení, poznámka se uloží do **fronty**
  (`note_queue.json`) a ukáže se zeleně s odznakem **„⏳ čeká na odeslání"**; daemon
  ji sám odešle při nejbližším úspěšném přihlášení (hodinový fetch nebo *Aktualizovat*).
- **Detekce změn:** z „čistých" (nezměněných) dnů se skládá **stálý rozvrh** (uloží se
  do cache jako `base` a přetrvává). Efektivní rozvrh se proti němu porovnává a
  **zvýrazní se jen to, co se liší** – jiný předmět → předmět, jiný učitel/učebna →
  jen ten údaj. Odpadlé hodiny: přeškrtnutý předmět + „odpadá", přesunuté + „přesunuto".
  Sudý/lichý týden (hodina/nic) nedělá falešná zvýraznění.
- **Mizí poznámky / „＋ poznámka"?** Nejspíš běží daemon druhého Windows účtu na
  **staré verzi kódu** (bez poznámek) a drží první control-port – přepisuje sdílenou
  cache i HTML rozvrhu starou šablonou. Řešení: **zkopíruj aktuální soubory i na druhý
  účet a jeho daemon restartuj** (Správce úloh → ukončit `pythonw.exe`, nebo restart
  PC). Stránka sama posílá *Aktualizovat*/ukládání poznámek jen na daemon, který
  poznámky umí (podle `/ping`), ale hodinový fetch starého daemonu umí cache dočasně
  přepsat, dokud ho nedoženeš.
- **Log:** `C:\Users\Public\edupage_schedule\daemon.log`
- **Test jednoho stažení:** `python edupage_daemon.py --once`
- **Autostart:** zástupce ve složce Startup (`shell:startup`), spouští se po přihlášení.
- **Zrušení autostartu:** `python uninstall_autostart.py`
- Běžící daemon je ve Správci úloh jako `pythonw.exe`.
