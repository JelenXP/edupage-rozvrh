"""Jadro pro stahovani rozvrhu z EduPage.

Bez print vystupu, aby slo znovu pouzit i pro beh na pozadi (faze 2).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from edupage_api import Edupage
from edupage_api.login import TwoFactorLogin

# Kolik dni dopredu stahovat (3 tydny).
DAYS_AHEAD = 21

# Lokalni control server (tlacitko Aktualizovat v rozvrhu). Zkousi se porty
# od BASE (kdyby jeden drzel druhy ucet). Vaze se jen na 127.0.0.1.
CONTROL_PORT_BASE = 8766
CONTROL_PORT_COUNT = 5

# SDILENA cache pro oba uzivatele: C:\Users\Public\edupage_schedule\schedule.json
# Public je systemove misto pristupne vsem uzivatelum (cti i zapis). Diky tomu
# fetch z jednoho uctu vidi druhy ucet (napr. skolni ucet ve skole offline).
_cache_base = os.environ.get("PUBLIC") or os.environ.get("LOCALAPPDATA") or "."
CACHE_DIR = Path(_cache_base) / "edupage_schedule"
CACHE_FILE = CACHE_DIR / "schedule.json"

# Fronta poznamek ulozenych offline (odesle se, az bude pripojeni). Sdilena,
# aby ji mohl odeslat i daemon druheho uctu (stejny EduPage ucet).
NOTE_QUEUE_FILE = CACHE_DIR / "note_queue.json"

# Config: nejdriv per-user (v profilu uctu), jinak vedle skriptu (sdilena slozka).
# Diky tomu muze z JEDNE sdilene slozky s kodem bezet vic Windows uctu, kazdy se
# svym configem - napr. skolni ucet s open_folders=true ma config ve svem profilu
# (%LOCALAPPDATA%\edupage\config.json), domaci ucet pouziva config vedle skriptu.
FOLDER_CONFIG_FILE = Path(__file__).with_name("config.json")
USER_APP_DIR = Path(os.environ.get("LOCALAPPDATA") or ".") / "edupage"
USER_CONFIG_FILE = USER_APP_DIR / "config.json"

# Zpetna kompatibilita (nekde se muze importovat CONFIG_FILE).
CONFIG_FILE = FOLDER_CONFIG_FILE


def config_path() -> Path:
    """Aktivni cesta ke config.json: per-user profil ma prednost pred slozkou."""
    return USER_CONFIG_FILE if USER_CONFIG_FILE.exists() else FOLDER_CONFIG_FILE


class ConfigError(Exception):
    """Chyba v config.json (chybi soubor nebo nevyplnene hodnoty)."""


class TwoFactorRequired(Exception):
    """Ucet vyzaduje dvoufazove overeni (2FA)."""


@dataclass
class LessonEntry:
    """Jedna hodina, zjednodusena pro ulozeni a vypis."""

    date: str          # YYYY-MM-DD
    weekday: str       # cesky nazev dne
    period: Optional[int]
    start_time: Optional[str]  # HH:MM
    end_time: Optional[str]    # HH:MM
    subject: Optional[str]
    teachers: list[str]
    classrooms: list[str]
    is_cancelled: bool   # slot se tu nekona (odpadlo nebo presunuto pryc)
    is_event: bool
    note: Optional[str]  # nazev skolni udalosti / poznamka (u udalosti misto predmetu)
    changes: list[str]   # zmenena pole (suplovani): "subject"/"teacher"/"room"/"moved"
    strike_label: Optional[str] = None  # text u preskrtnute hodiny: "odpadá"/"přesunuto"
    all_day: bool = False  # celodenni udalost (svatek/volno) - v mrizce pres cely den
    my_note: Optional[str] = None  # osobni poznamka k hodine ("Moje poznámka" v EduPage)


@dataclass
class AssignmentEntry:
    """Domaci ukol nebo test navazany na den + predmet."""

    date: str            # YYYY-MM-DD (na kdy je zadano)
    subject: Optional[str]
    kind: str            # "DU" nebo "Test"
    title: str


_WEEKDAYS_CZ = ["Pondeli", "Utery", "Streda", "Ctvrtek", "Patek", "Sobota", "Nedele"]

# Typy timeline udalosti = domaci ukoly / testy.
_ASSIGN_HOMEWORK = {"homework", "etesthw"}
_ASSIGN_EXAM = {"bexam", "sexam", "oexam", "rexam", "pexam", "testing"}


def load_config(path: Optional[Path] = None) -> dict:
    """Nacte a overi config.json. Vyhodi ConfigError se srozumitelnou hlaskou.

    Kdyz `path` neni zadana, pouzije se per-user config (profil uctu), jinak
    config vedle skriptu (sdilena slozka).
    """
    if path is None:
        path = config_path()
    if not path.exists():
        raise ConfigError(
            f"Chybi konfiguracni soubor.\n"
            f"Hledal jsem (v tomto poradi):\n"
            f"  1) per-user: {USER_CONFIG_FILE}\n"
            f"  2) slozka:   {FOLDER_CONFIG_FILE}\n"
            f"Zkopiruj config.example.json na jedno z techto mist a vypln udaje\n"
            f"(pro sdilenou slozku s vic ucty pouzij tu per-user cestu)."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json neni platny JSON: {e}") from e

    missing = [k for k in ("username", "password", "subdomain") if not data.get(k)]
    if missing:
        raise ConfigError(
            "V config.json chybi nebo jsou prazdne polozky: " + ", ".join(missing)
        )

    # Ochrana proti nechtene ponechanym vzorovym hodnotam.
    if data["username"] == "tve_uzivatelske_jmeno" or data["password"] == "tveHeslo":
        raise ConfigError(
            "config.json obsahuje vzorove hodnoty. Vypln prosim skutecne udaje."
        )

    return data


def login(config: dict) -> Edupage:
    """Prihlasi se do EduPage. Vyhodi TwoFactorRequired pri 2FA."""
    edupage = Edupage()
    result = edupage.login(
        config["username"], config["password"], config["subdomain"]
    )
    if isinstance(result, TwoFactorLogin):
        raise TwoFactorRequired(
            "Ucet vyzaduje dvoufazove overeni (2FA). Napis to a doladime to."
        )
    return edupage


# --- Znovupouzitelna prihlasena session ---------------------------------------
# Dlouho bezici daemon si drzi jeden prihlaseny Edupage v pameti a znovupouziva
# ho pro vsechny operace (fetch, ukladani poznamek, on-demand aktualizace). Tim
# odpadne opakovany login (~1-2 s) u kazdeho ukladani poznamky i u kazdeho
# prolistovani na dalsi tyden.
_CACHED_SESSION: Optional[Edupage] = None


def get_session(force_new: bool = False) -> Edupage:
    """Vrati prihlaseny Edupage - znovupouzije session z pameti, pokud je.

    `force_new=True` zahodi drzenou session a prihlasi se znovu (kdyz predchozi
    vyprsela). Vola `login()`, takze pri 2FA vyhodi `TwoFactorRequired` a pri
    offline propaguje vyjimku - stejne jako doted.
    """
    global _CACHED_SESSION
    if force_new or _CACHED_SESSION is None:
        _CACHED_SESSION = login(load_config())
    return _CACHED_SESSION


def _time_str(t) -> Optional[str]:
    return t.strftime("%H:%M") if t is not None else None


def _to_int(value) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _build_id_maps(edupage: Edupage) -> tuple[dict, dict, dict]:
    """Mapy id -> nazev pro predmety, ucitele a ucebny (jednou za fetch)."""
    subjects, teachers, rooms = {}, {}, {}
    try:
        for s in (edupage.get_subjects() or []):
            subjects[s.subject_id] = s.name
    except Exception:  # noqa: BLE001
        pass
    try:
        for t in (edupage.get_teachers() or []):
            teachers[t.person_id] = t.name
    except Exception:  # noqa: BLE001
        pass
    try:
        for r in (edupage.get_classrooms() or []):
            rooms[r.classroom_id] = r.name
    except Exception:  # noqa: BLE001
        pass
    return subjects, teachers, rooms


def _extract_my_note(l: dict) -> Optional[str]:
    """Vytahne osobni poznamku k hodine z pole 'fields' (label 'Moje poznámka').

    Poznamka ma fieldid tvaru 'snote:<userid>:<datum>:<perioda>'. Vraci text,
    nebo None, kdyz je prazdny / neni.
    """
    for f in l.get("fields") or []:
        if not isinstance(f, dict):
            continue
        fid = str(f.get("fieldid") or "")
        if fid.startswith("snote:") or f.get("label") == "Moje poznámka":
            text = (f.get("text") or "").strip()
            return text or None
    return None


def _parse_plan(plan: list, day: date, maps: tuple[dict, dict, dict]) -> list[LessonEntry]:
    """Rozparsuje syrovy denni plan vcetne zmen (suplovani) a odpadlych hodin."""
    subj_map, teach_map, room_map = maps
    out: list[LessonEntry] = []

    for l in plan:
        header = l.get("header")
        # Preskocit prazdne periody / "pridat hodinu" radky.
        if header is not None and (
            not header
            or (isinstance(header[0], dict) and header[0].get("cmd") == "addlesson_t")
        ):
            continue

        uni = l.get("uniperiod")
        period = int(uni) if uni and str(uni).isdigit() else None
        typ = l.get("type")
        flags = l.get("flags") or {}
        dp0 = flags.get("dp0") or {}

        hdr_item = {}
        header_text = None
        if header and isinstance(header[0], dict):
            hdr_item = header[0].get("item") or {}
            header_text = header[0].get("text")

        # Celodenni udalost (svatek / volno) - v mrizce pres cely den.
        if l.get("allday") or uni == "ad":
            title = header_text or (flags.get("event") or {}).get("name")
            out.append(
                LessonEntry(
                    date=day.strftime("%Y-%m-%d"),
                    weekday=_WEEKDAYS_CZ[day.weekday()],
                    period=None,
                    start_time=None,
                    end_time=None,
                    subject=None,
                    teachers=[],
                    classrooms=[],
                    is_cancelled=False,
                    is_event=True,
                    note=title,
                    changes=[],
                    strike_label=None,
                    all_day=True,
                )
            )
            continue

        # Texty a zmeny z "infos".
        infos_texts: list[str] = []
        info_teacher_ids: list = []
        info_room_ids: list = []
        teacher_changed = room_changed = False
        for info in l.get("infos") or []:
            for t in info.get("texts") or []:
                infos_texts.append(t.get("text", ""))
                item = t.get("item") or {}
                if "teacherids" in item:
                    info_teacher_ids = list(item.get("teacherids") or [])
                    teacher_changed = bool(item.get("changes"))
                if "classroomids" in item:
                    info_room_ids = list(item.get("classroomids") or [])
                    room_changed = bool(item.get("changes"))

        is_odpadlo = any("Odpad" in x for x in infos_texts)
        is_presun = any("Přesun" in x for x in infos_texts)
        is_placeholder = bool(l.get("removed")) or typ == ""

        changes: set[str] = set()
        strike_label: Optional[str] = None

        if is_placeholder:
            # Hodina, ktera se tu nekona (odpadla nebo se presunula pryc).
            is_cancelled = True
            strike_label = "přesunuto" if is_presun else "odpadá"
            subj_id = l.get("subjectid") or hdr_item.get("subjectid")
            teacher_ids = list(l.get("teacherids") or [])
            room_ids = list(l.get("classroomids") or [])
            start = (l.get("starttime") or "").replace("24:00", "23:59") or None
            end = (l.get("endtime") or "").replace("24:00", "23:59") or None
        else:
            # Realna hodina - efektivni data z dp0 (jinak z horni urovne).
            is_cancelled = bool(dp0.get("cancelled")) or is_odpadlo
            if is_cancelled:
                strike_label = "odpadá"
            subj_id = dp0.get("subjectid") or l.get("subjectid") or hdr_item.get("subjectid")
            teacher_ids = list(dp0.get("teacherids") or l.get("teacherids") or info_teacher_ids)
            room_ids = list(dp0.get("classroomids") or l.get("classroomids") or info_room_ids)
            start = (dp0.get("starttime") or l.get("starttime") or "").replace("24:00", "23:59") or None
            end = (dp0.get("endtime") or l.get("endtime") or "").replace("24:00", "23:59") or None

            # Zmeny jednotlivych poli (suplovani).
            if any(isinstance(c, dict) and c.get("new") for c in (hdr_item.get("changes") or [])):
                changes.add("subject")
            if teacher_changed:
                changes.add("teacher")
            if room_changed:
                changes.add("room")
            # Presun hodiny sem (nahrada).
            if is_presun or dp0.get("substids") or dp0.get("orig") is not None:
                changes.add("moved")

        subject = subj_map.get(_to_int(subj_id)) if subj_id else None
        teachers = [teach_map[i] for i in map(_to_int, teacher_ids) if i in teach_map]
        rooms = [room_map[i] for i in map(_to_int, room_ids) if i in room_map]

        is_event = typ in ("event", "out") or bool(l.get("main"))
        try:
            note = (flags.get("dp0") or {}).get("note_wd") or (
                flags.get("event") or {}
            ).get("name")
        except AttributeError:
            note = None

        my_note = _extract_my_note(l)

        # Vynechat prazdne placeholdery bez obsahu.
        if period is None and not is_event and not is_cancelled and not subject:
            continue

        out.append(
            LessonEntry(
                date=day.strftime("%Y-%m-%d"),
                weekday=_WEEKDAYS_CZ[day.weekday()],
                period=period,
                start_time=start,
                end_time=end,
                subject=subject,
                teachers=teachers,
                classrooms=rooms,
                is_cancelled=is_cancelled,
                is_event=is_event,
                note=note,
                changes=sorted(changes),
                strike_label=strike_label,
                my_note=my_note,
            )
        )

    return out


def _load_date_plans(edupage: Edupage, start: date, end: date) -> dict:
    """Stahne syrove denni plany pro rozsah [start, end] na MALO requestu.

    Endpoint tridni knihy (`/gcall` action=loadData) vraci VZDY jen 3 dny okolo
    zadaneho `date` (date-1 .. date+1) a parametr `dateto` ignoruje. Rozsah proto
    pokryjeme 3dennimi okny (stred = start+1, +4, +7, ...), ale CSRF token
    (gpid/gsh) resime jen JEDNOU pro vsechny pozadavky.

    Vraci `{'YYYY-MM-DD': plan_list}`. Puvodne se stahoval kazdy den zvlast
    (GET CSRF + POST na den) = 2 requesty/den; tohle je ~4x mene requestu a bez
    opakovaneho CSRF GETu. Poznamky (`fields` snote) jsou v odpovedi zachovane.
    """
    from edupage_api.utils import RequestUtil

    base_url = f"https://{edupage.subdomain}.edupage.org"
    # CSRF token jednou pro vsechny pozadavky (jinak GET na kazdy den).
    page = edupage.session.get(f"{base_url}/dashboard/eb.php?mode=ttday").text
    gpid = str(int(page.split("gpid=")[1].split("&")[0]) + 1)  # +1 = gadget tridni knihy
    gsh = page.split("gsh=")[1].split('"')[0]

    uid = edupage.get_user_id()
    resp_start = uid + '",'
    resp_end = ",["

    out: dict = {}
    center = start + timedelta(days=1)  # stred 1. okna: pokryje start .. start+2
    while center - timedelta(days=1) <= end:
        body = RequestUtil.encode_form_data(
            {
                "gpid": gpid,
                "gsh": gsh,
                "action": "loadData",
                "user": uid,
                "changes": "{}",
                "date": center.strftime("%Y-%m-%d"),
                "dateto": center.strftime("%Y-%m-%d"),
                "_LJSL": "4096",
            }
        )
        try:
            resp = edupage.session.post(
                f"{base_url}/gcall",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            payload = resp.text.split(resp_start)[1].rsplit(resp_end, 1)[0]
            dates = json.loads(payload).get("dates") or {}
        except Exception:  # noqa: BLE001 - vypadek jednoho okna nesmi shodit fetch
            dates = {}
        for dstr, dp in dates.items():
            if isinstance(dp, dict) and dp.get("plan") is not None:
                out[dstr] = dp.get("plan")
        center += timedelta(days=3)
    return out


def fetch_schedule(
    edupage: Edupage,
    start: Optional[date] = None,
    days_ahead: Optional[int] = None,
    on_error=None,
) -> list[LessonEntry]:
    """Stahne rozvrh od `start` na `days_ahead` dni dopredu.

    Vychozi rozsah (kdyz start/days_ahead nejsou zadane) je zarovnany na cele
    tydny - viz `_week_aligned_range` (proto se neztraci pondeli tohoto tydne ani
    patek posledniho tydne). Parsuje syrovy denni plan (vcetne suplovani a
    odpadlych hodin). Vikendy se preskakuji. Chyba dne -> on_error(day, exc).
    """
    if start is None:
        start, _end = _week_aligned_range()
        if days_ahead is None:
            days_ahead = (_end - start).days
    if days_ahead is None:
        days_ahead = DAYS_AHEAD
    end = start + timedelta(days=days_ahead)

    maps = _build_id_maps(edupage)

    try:
        plans = _load_date_plans(edupage, start, end)
    except Exception as e:  # noqa: BLE001 - offline / vyprsela session apod.
        if on_error is not None:
            on_error(start, e)
        return []

    entries: list[LessonEntry] = []
    for offset in range(days_ahead + 1):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:  # 5 = sobota, 6 = nedele
            continue
        plan = plans.get(day.strftime("%Y-%m-%d"))
        if plan is None:  # den se nepodarilo stahnout (vynechame, cache se nesmaze)
            continue
        entries.extend(_parse_plan(plan, day, maps))

    return entries


def fetch_assignments(edupage: Edupage, on_error=None) -> list[AssignmentEntry]:
    """Stahne domaci ukoly a testy z timeline a navaze je na den + predmet."""
    out: list[AssignmentEntry] = []
    try:
        notifs = edupage.get_notifications()
    except Exception as e:  # noqa: BLE001 - vypadek DU/testu nesmi shodit fetch
        if on_error is not None:
            on_error(e)
        return out

    # Mapa id predmetu -> nazev (jednou).
    subj_map: dict[int, str] = {}
    try:
        for s in (edupage.get_subjects() or []):
            subj_map[s.subject_id] = s.name
    except Exception:  # noqa: BLE001
        pass

    for n in notifs:
        et = n.event_type.value if n.event_type else None
        if et in _ASSIGN_HOMEWORK:
            kind = "DU"
        elif et in _ASSIGN_EXAM:
            kind = "Test"
        else:
            continue

        ad = n.additional_data if isinstance(n.additional_data, dict) else {}
        day = ad.get("date")
        if not day:
            continue

        subject = None
        pid = ad.get("predmetid")
        if pid is not None:
            try:
                subject = subj_map.get(int(pid))
            except (ValueError, TypeError):
                subject = None

        title = ad.get("nazov") or n.text or ""
        out.append(AssignmentEntry(date=day, subject=subject, kind=kind, title=title))

    return out


def refresh_cache() -> bool:
    """Stahne rozvrh + DU/testy a ulozi do cache. Vrati True pri uspechu.

    Tise (bez logovani) - pro pouziti na vyzadani (napr. pri otevreni rozvrhu).
    Pri neuspechu cache neprepisuje.
    """
    try:
        edupage = get_session()
    except Exception:  # noqa: BLE001 - config/2FA/offline; tise se vratime
        return False

    flush_note_queue(edupage)  # nejdriv odeslat poznamky ulozene offline
    entries = fetch_schedule(edupage)
    if not entries:
        # Mozna vyprsela drzena session -> jeden pokus s cerstvym prihlasenim.
        try:
            edupage = get_session(force_new=True)
        except Exception:  # noqa: BLE001 - offline / config / 2FA
            return False
        flush_note_queue(edupage)
        entries = fetch_schedule(edupage)
        if not entries:
            return False

    assignments = fetch_assignments(edupage)
    try:
        persist_cache(entries, assignments)
    except OSError:
        return False
    return True


def _base_key(weekday: str, period: Optional[int]) -> str:
    return f"{weekday}|{period}"


def build_base(entries: list[LessonEntry], old_base: Optional[dict] = None) -> dict:
    """Posklada 'staly rozvrh' (den+hodina -> predmet/ucitel/ucebna) z cistych hodin.

    Vychazi z drive ulozeneho `old_base` (pretrvani slotu bez ciste ukazky) a
    prepisuje ho aktualnimi cistymi hodinami (self-healing pri trvale zmene rozvrhu).
    Ciste = nezrusene, neudalost, bez zmeny/presunu, s predmetem.
    """
    base = dict(old_base or {})
    for e in entries:
        if (
            e.is_cancelled
            or e.is_event
            or e.period is None
            or not e.subject
            or e.changes  # neni ciste (ma zmenu/presun)
        ):
            continue
        base[_base_key(e.weekday, e.period)] = {
            "subject": e.subject,
            "teachers": e.teachers,
            "rooms": e.classrooms,
        }
    return base


def annotate_changes(entries: list[LessonEntry], base: dict) -> None:
    """Nastavi u kazde hodiny `changes` porovnanim proti stalemu rozvrhu.

    Kazde pole se porovnava nezavisle - zvyrazni se vsechna, ktera se lisi od
    staleho rozvrhu (predmet i ucitel i ucebna zaroven, kdyz je to potreba).
    Kde staly rozvrh chybi, ponecha jen puvodni priznaky (bez interniho "moved").
    """
    for e in entries:
        if e.is_cancelled or e.is_event or e.period is None:
            continue
        b = base.get(_base_key(e.weekday, e.period))
        if b is None:
            e.changes = [c for c in e.changes if c != "moved"]
            continue

        ch = set()
        if e.subject and e.subject != b.get("subject"):
            ch.add("subject")
        if e.teachers and set(e.teachers) != set(b.get("teachers") or []):
            ch.add("teacher")
        if e.classrooms and set(e.classrooms) != set(b.get("rooms") or []):
            ch.add("room")
        e.changes = sorted(ch)


def _write_payload(
    lessons: list[dict],
    assignments: list[dict],
    base: dict,
    fetched_weeks: list[str],
    path: Path,
) -> Path:
    """Atomicky zapise cache (temp soubor + prejmenovani)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "lessons": lessons,
        "assignments": assignments,
        "base": base,
        "fetched_weeks": fetched_weeks,
    }
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, path)  # atomicka nahrada na stejnem svazku
    return path


def _week_aligned_range(today: Optional[date] = None) -> tuple[date, date]:
    """Rozsah pro bezny fetch zarovnany na CELE tydny (Po-Pa).

    Zacina pondelim tohoto tydne (aby byly kompletni i dnesni tyden vcetne dnu
    pred dneskem) a konci patkem tydne, ktery obsahuje dnesek+DAYS_AHEAD (aby
    nebyl posledni tyden okna oriznuty uprostred). Diky tomu je KAZDY tyden v
    rozsahu stazeny cely a FETCHED_WEEKS spravne oznacuje jen kompletni tydny.
    """
    if today is None:
        today = date.today()
    start = today - timedelta(days=today.weekday())            # pondeli tohoto tydne
    end_target = today + timedelta(days=DAYS_AHEAD)
    end = end_target - timedelta(days=end_target.weekday()) + timedelta(days=4)  # patek
    return start, end


def _mondays_in_range(start: date, end: date) -> list[str]:
    """Pondelky (YYYY-MM-DD) vsech tydnu, ktere zasahuji do [start, end]."""
    d = start - timedelta(days=start.weekday())  # pondeli tydne se startem
    out = []
    while d <= end:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=7)
    return out


def persist_cache(
    entries: list[LessonEntry],
    assignments: Optional[list[AssignmentEntry]] = None,
    refresh_start: Optional[date] = None,
    refresh_end: Optional[date] = None,
    path: Path = CACHE_FILE,
) -> Path:
    """Slozi/aktualizuje staly rozvrh, zvyrazni zmeny a SLUCUJE do cache.

    Obnovi jen okno [refresh_start, refresh_end] (default dnesek..+DAYS_AHEAD);
    data mimo okno se ponechavaji - takze fetch v utery nesmaze pondeli a
    tydny stazene dopredu zustanou, dokud je bezne okno nedozene.
    """
    if refresh_start is None or refresh_end is None:
        ws, we = _week_aligned_range()
        if refresh_start is None:
            refresh_start = ws
        if refresh_end is None:
            refresh_end = we

    base = build_base(entries, load_base(path))
    annotate_changes(entries, base)

    s, e = refresh_start.strftime("%Y-%m-%d"), refresh_end.strftime("%Y-%m-%d")

    def in_window(dstr: str) -> bool:
        return s <= dstr <= e

    kept = [l for l in load_cache(path) if not in_window(l.get("date", ""))]
    merged = kept + [asdict(x) for x in entries]
    merged.sort(key=lambda l: (l.get("date", ""), l.get("period") or 0))

    # fetch_assignments vraci VZDY vsechny DU/testy (nezavisle na okne), takze
    # ruzna okna (napr. fetch_week na vzdaleny tyden) by jinak duplikovala
    # polozky mimo dane okno. Slucujeme a de-duplikujeme podle obsahu.
    kept_a = [a for a in load_assignments(path) if not in_window(a.get("date", ""))]
    merged_a = []
    seen_a = set()
    for a in kept_a + [asdict(a) for a in (assignments or [])]:
        key = (a.get("date"), a.get("subject"), a.get("kind"), a.get("title"))
        if key in seen_a:
            continue
        seen_a.add(key)
        merged_a.append(a)

    weeks = sorted(
        set(load_fetched_weeks(path)) | set(_mondays_in_range(refresh_start, refresh_end))
    )
    return _write_payload(merged, merged_a, base, weeks, path)


def fetch_week(monday: date) -> bool:
    """Stahne jeden tyden (Po-Pa daneho `monday`) a slouci do cache. Tise.

    Slouzi pro dotazeni tydnu na vyzadani (kdyz uzivatel prolistuje dopredu za
    bezne stahovane okno). Vrati True pri uspesnem prihlaseni a ulozeni.
    """
    monday = monday - timedelta(days=monday.weekday())  # zarovnat na pondeli
    friday = monday + timedelta(days=4)
    try:
        edupage = get_session()
    except Exception:  # noqa: BLE001 - offline / config / 2FA
        return False

    entries = fetch_schedule(edupage, start=monday, days_ahead=4)
    if not entries:
        # Mozna vyprsela drzena session -> jeden pokus s cerstvym prihlasenim.
        try:
            edupage = get_session(force_new=True)
        except Exception:  # noqa: BLE001 - offline / config / 2FA
            return False
        entries = fetch_schedule(edupage, start=monday, days_ahead=4)
        if not entries:
            return False
    assignments = fetch_assignments(edupage)
    try:
        persist_cache(entries, assignments, refresh_start=monday, refresh_end=friday, path=CACHE_FILE)
    except OSError:
        return False
    return True


def _person_id_str(user_id: str) -> str:
    """Z 'Student-170' udela '-170' (cislo osoby pouzite ve fieldid poznamky)."""
    p = user_id
    while p and p[0].isalpha():
        p = p[1:]
    return p


def _post_note(edupage: Edupage, date_str: str, period: int, text: str) -> bool:
    """Odesle jednu poznamku na server (edupage uz musi byt prihlaseny)."""
    base_url = f"https://{edupage.subdomain}.edupage.org"
    try:
        page = edupage.session.get(f"{base_url}/dashboard/eb.php?mode=ttday").text
        gpid = str(int(page.split("gpid=")[1].split("&")[0]) + 1)  # +1 = gadget tridni knihy
        gsh = page.split("gsh=")[1].split('"')[0]
    except (IndexError, ValueError):
        return False

    uid = edupage.get_user_id()
    fieldid = f"snote:{_person_id_str(uid)}:{date_str}:{period}"
    changes = {fieldid: {"text": text}}

    from edupage_api.utils import RequestUtil

    body = RequestUtil.encode_form_data(
        {
            "gpid": gpid,
            "gsh": gsh,
            "action": "save",
            "user": uid,
            "date": date_str,
            "changes": json.dumps(changes, ensure_ascii=False),
            "_LJSL": "4096",
        }
    )
    try:
        resp = edupage.session.post(
            f"{base_url}/gcall",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    except Exception:  # noqa: BLE001
        return False
    return resp.status_code == 200 and "clearAfterSave" in resp.text


def save_note(date_str: str, period: int, text: str) -> str:
    """Ulozi/upravi/smaze osobni poznamku k hodine. Prazdny `text` = smazani.

    Vrati stav:
      "saved"  - ulozeno rovnou na server (online),
      "queued" - offline: dano do fronty (odesle se, az bude pripojeni),
      "failed" - nepovedlo se ani dat do fronty (napr. chyba disku).
    Vzdy upravi lokalni cache, aby se zmena hned projevila (u fronty s priznakem).
    """
    try:
        edupage = get_session()
    except Exception:  # noqa: BLE001 - offline / config / 2FA -> do fronty
        return "queued" if _enqueue_and_mark(date_str, period, text) else "failed"

    ok = _post_note(edupage, date_str, period, text)
    if not ok:
        # Mozna vyprsela drzena session -> jeden pokus s cerstvym prihlasenim.
        try:
            edupage = get_session(force_new=True)
            ok = _post_note(edupage, date_str, period, text)
        except Exception:  # noqa: BLE001 - offline / config / 2FA
            ok = False

    if ok:
        try:
            update_cached_note(date_str, period, text, pending=False)
        except OSError:
            pass  # server ulozeno; cache dozene pristi fetch
        dequeue_note(date_str, period)
        return "saved"

    # Prihlaseni proslo, ale ulozeni selhalo (nebo offline) -> zkusime frontu.
    return "queued" if _enqueue_and_mark(date_str, period, text) else "failed"


def _enqueue_and_mark(date_str: str, period: int, text: str) -> bool:
    """Da poznamku do fronty a optimisticky ji zapise do cache (s priznakem)."""
    try:
        enqueue_note(date_str, period, text)
        update_cached_note(date_str, period, text, pending=True)
        return True
    except OSError:
        return False


def update_cached_note(
    date_str: str, period: int, text: str, pending: bool = False, path: Path = CACHE_FILE
) -> None:
    """Upravi `my_note` u hodin daneho dne+periody primo v cache (bez fetche).

    `pending=True` navic oznaci hodinu jako "ceka na odeslani" (offline fronta).
    """
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    lessons = data.get("lessons", [])
    val = text.strip() or None
    changed = False
    for l in lessons:
        if l.get("date") == date_str and l.get("period") == period:
            l["my_note"] = val
            if pending:
                l["note_pending"] = True
            else:
                l.pop("note_pending", None)
            changed = True
    if changed:
        _write_payload(
            lessons,
            data.get("assignments", []),
            data.get("base", {}),
            data.get("fetched_weeks", []),
            path,
        )


# ---- Offline fronta poznamek -------------------------------------------------

def _queue_key(date_str: str, period: int) -> str:
    return f"{date_str}|{period}"


def load_note_queue(path: Path = NOTE_QUEUE_FILE) -> dict:
    """Nacte frontu offline poznamek. Vrati dict (klic 'datum|perioda')."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_note_queue(queue: dict, path: Path = NOTE_QUEUE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def enqueue_note(date_str: str, period: int, text: str, path: Path = NOTE_QUEUE_FILE) -> None:
    """Prida/prepise polozku ve fronte (posledni uprava slotu vyhrava)."""
    queue = load_note_queue(path)
    queue[_queue_key(date_str, period)] = {
        "date": date_str,
        "period": period,
        "text": text,
    }
    _write_note_queue(queue, path)


def dequeue_note(date_str: str, period: int, path: Path = NOTE_QUEUE_FILE) -> None:
    """Odstrani polozku z fronty (kdyz uz je odeslana)."""
    queue = load_note_queue(path)
    if queue.pop(_queue_key(date_str, period), None) is not None:
        _write_note_queue(queue, path)


def flush_note_queue(edupage: Edupage, logger=None) -> int:
    """Odesle vsechny poznamky z fronty (edupage uz musi byt prihlaseny).

    Vrati pocet uspesne odeslanych. Pri prvnim neuspechu (zase offline) prestane
    a zbytek nechá ve fronte na priste.
    """
    queue = load_note_queue()
    if not queue:
        return 0
    sent = 0
    for item in list(queue.values()):
        d, p, txt = item.get("date"), int(item.get("period")), item.get("text", "")
        if not d or not _post_note(edupage, d, p, txt):
            break  # nejspis znovu offline - zbytek nech na priste
        dequeue_note(d, p)
        try:
            update_cached_note(d, p, txt, pending=False)
        except OSError:
            pass
        sent += 1
    if logger and sent:
        logger.info("Odeslano %d poznamek z offline fronty.", sent)
    return sent


def save_cache(
    entries: list[LessonEntry],
    assignments: Optional[list[AssignmentEntry]] = None,
    base: Optional[dict] = None,
    path: Path = CACHE_FILE,
) -> Path:
    """Prepise cache (bez slucovani). Ponechano pro kompatibilitu."""
    return _write_payload(
        [asdict(e) for e in entries],
        [asdict(a) for a in (assignments or [])],
        base if base is not None else load_base(path),
        load_fetched_weeks(path),
        path,
    )


def load_cache(path: Path = CACHE_FILE) -> list[dict]:
    """Nacte lekce ze sdilene cache. Vrati seznam dictu (nebo [] kdyz neni)."""
    return _load_key(path, "lessons")


def load_assignments(path: Path = CACHE_FILE) -> list[dict]:
    """Nacte DU/testy ze sdilene cache. Vrati seznam dictu (nebo [] kdyz neni)."""
    return _load_key(path, "assignments")


def load_fetched_weeks(path: Path = CACHE_FILE) -> list[str]:
    """Nacte seznam pondelku (YYYY-MM-DD) uz stazenych tydnu."""
    return _load_key(path, "fetched_weeks")


def load_fetched_at(path: Path = CACHE_FILE) -> Optional[str]:
    """Vrati cas posledniho stazeni (ISO) z cache, nebo None."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("fetched_at")


def load_base(path: Path = CACHE_FILE) -> dict:
    """Nacte staly rozvrh ze sdilene cache. Vrati dict (nebo {} kdyz neni)."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    base = data.get("base")
    return base if isinstance(base, dict) else {}


def _load_key(path: Path, key: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get(key, [])
