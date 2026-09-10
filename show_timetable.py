"""Zobrazi cely rozvrh jako klasickou mrizku v prohlizeci.

Vygeneruje samostatny HTML soubor z cache (funguje offline) a otevre ho.
Dny jsou v radcich (vlevo), hodiny ve sloupcich (nahore).
Prepinani tydnu (tento / dalsi / prespristi) je primo ve strance.

Pouziti:
    python show_timetable.py
"""

from __future__ import annotations

import json
import os
import time
import webbrowser
from pathlib import Path

import edupage_fetch as core

OUTPUT_FILE = core.CACHE_DIR / "rozvrh.html"

_TEMPLATE = r"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>Rozvrh</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: "Segoe UI", system-ui, sans-serif; margin: 0; padding: 24px;
         background: #f4f4f7; color: #1e1e2e; }
  @media (prefers-color-scheme: dark) {
    body { background: #14141c; color: #e8e8ef; }
    table { background: #1e1e2e; }
    th, td { border-color: #34344a !important; }
    .day { background: #26263a !important; }
    .cell.has { background: #232338 !important; }
    tr.today .day { background: #2a2a44 !important; }
  }
  header { display: flex; align-items: center; gap: 16px; margin-bottom: 18px;
           flex-wrap: wrap; }
  h1 { font-size: 20px; margin: 0; }
  .range { font-size: 15px; opacity: .8; }
  button { font: inherit; padding: 6px 14px; border-radius: 8px; border: 1px solid #89b4fa;
           background: transparent; color: inherit; cursor: pointer; }
  button:disabled { opacity: .35; cursor: default; }
  .wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; background: #fff; border-radius: 10px;
          overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,.08); }
  th, td { border: 1px solid #e2e2ea; padding: 8px 10px; vertical-align: top;
           text-align: left; }
  th { background: #89b4fa; color: #14141c; font-size: 14px; white-space: nowrap; }
  th small { display: block; font-weight: normal; opacity: .8; }
  .day { background: #eef0f6; white-space: nowrap; font-weight: 600; width: 110px; }
  .day small { display: block; opacity: .7; font-weight: normal; }
  .cell { min-width: 120px; height: 56px; }
  .cell.has { background: #f7f8fc; }
  .subject { font-weight: 600; }
  .meta { font-size: 12px; opacity: .8; margin-top: 2px; }
  .cancelled .subject { text-decoration: line-through; opacity: .55; }
  .cancelled .meta { opacity: .7; }
  .asg { color: #d97706; font-weight: 600; }
  @media (prefers-color-scheme: dark) { .asg { color: #f0a94b; } }
  .note { color: #1f9d57; font-weight: 600; white-space: pre-wrap; }
  @media (prefers-color-scheme: dark) { .note { color: #4ecb83; } }
  .note.noteedit { cursor: pointer; }
  .note.noteedit:hover { text-decoration: underline; }
  .noteadd { font-size: 12px; color: #8a8a9a; cursor: pointer; opacity: .55;
             margin-top: 2px; }
  .noteadd:hover { opacity: 1; }
  .noteeditor { margin-top: 4px; }
  .noteeditor textarea { width: 100%; box-sizing: border-box; font: inherit;
             font-size: 12px; resize: vertical; border: 1px solid #89b4fa;
             border-radius: 6px; padding: 4px; background: #fff; color: #1e1e2e; }
  @media (prefers-color-scheme: dark) {
    .noteeditor textarea { background: #14141c; color: #e8e8ef; }
  }
  .notebtns { margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap; }
  .notebtns button { padding: 2px 8px; font-size: 12px; }
  .notebtns .del { border-color: #e06c75; color: #e06c75; }
  .notepending { font-size: 11px; color: #b58900; opacity: .95; margin-top: 1px; }
  @media (prefers-color-scheme: dark) { .notepending { color: #d9b038; } }
  .chg { background: #ffe08a; color: #7a4d00; border-radius: 4px; padding: 0 4px;
         font-weight: 700; }
  @media (prefers-color-scheme: dark) { .chg { background: #6b5310; color: #ffe9b0; } }
  .subject.chg { display: inline-block; }
  .allday { text-align: center; font-weight: 600; font-style: italic; }
  .allday.holiday { background: #e7f0e7; color: #2f5d2f; }   /* svatek / prazdniny */
  .allday.event   { background: #ece4fb; color: #5b3a99; }   /* skolni / celodenni akce */
  @media (prefers-color-scheme: dark) {
    .allday.holiday { background: #223322; color: #b6e0b6; }
    .allday.event   { background: #312046; color: #cbb4f2; }
  }
  tr.today .day { background: #eaf1ff; }
  .newfeat { display: none; margin: 0 0 12px; padding: 10px 14px; border-radius: 10px;
             background: #eef4ff; color: #1f4e8c; border: 1px solid #cddcfa; font-size: 14px; }
  .newfeat.show { display: flex; align-items: center; gap: 10px; }
  .newfeat code { background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 4px; }
  .newfeat .x { margin-left: auto; border: none; background: transparent; color: inherit;
                font-size: 20px; cursor: pointer; line-height: 1; padding: 0 4px; }
  @media (prefers-color-scheme: dark) {
    .newfeat { background: #1b2a44; color: #a9c8f0; border-color: #2b3f5f; }
    .newfeat code { background: rgba(255,255,255,.1); }
  }
</style>
</head>
<body>
<div id="newfeat" class="newfeat">
  <span>✨ <b>Nová funkce:</b> notifikace na nové známky (vpravo nahoře). Zapni v
  <code>config.json</code>: <code>"notify_grades": true</code> a restartuj daemon
  (ikona v liště → Restart).</span>
  <button class="x" id="newfeatClose" title="Zavřít" aria-label="Zavřít">&times;</button>
</div>
<header>
  <h1>Rozvrh</h1>
  <button id="prev">&#9664; Předchozí</button>
  <button id="today">Dnes</button>
  <button id="next">Další &#9654;</button>
  <button id="refresh" title="Aktualizuje všechny týdny od tohoto týdne po zobrazený">⟳ Aktualizovat</button>
  <span class="range" id="range"></span>
  <span class="range" id="updated"></span>
</header>
<div class="wrap"><div id="grid"></div></div>

<script>
const LESSONS = __LESSONS__;
const ASSIGNMENTS = __ASSIGNMENTS__;
const DAYS_AHEAD = __DAYS_AHEAD__;
const FETCHED_AT = "__FETCHED_AT__";
const PENDING = __PENDING__;  // probiha stahovani aktualnich dat na pozadi
const PORTS = __PORTS__;      // porty lokalniho control serveru (tlacitko Aktualizovat)
const FETCHED_WEEKS = __FETCHED_WEEKS__;  // pondelky uz stazenych tydnu

let weekFetching = false;
let editing = null;  // "datum#perioda" hodiny, u ktere je otevreny editor poznamky

// Najde prvni port, jehoz daemon umi poznamky (novy kod). Kdyby druhy Windows
// ucet bezel na stare verzi, nepřebere nam obsluhu a nepřepíše rozvrh starou
// šablonou. Kdyz zadny "notes" daemon neodpovi, vrati vsechny porty (fallback).
async function noteCapablePorts() {
  const good = [];
  for (const p of PORTS) {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/ping`, { mode: "cors" });
      if (!r.ok) continue;
      const j = await r.json().catch(() => ({}));
      if (j.notes) good.push(p);
    } catch (e) { /* dalsi port */ }
  }
  return good.length ? good : PORTS.slice();
}

function editNote(d, p) {
  editing = d + "#" + p;
  render();
  const t = document.getElementById("noteInput");
  if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); }
}
function cancelNote() { editing = null; render(); }
function saveNote(d, p) {
  const t = document.getElementById("noteInput");
  postNote(d, p, t ? t.value : "");
}
function deleteNote(d, p) { postNote(d, p, ""); }

async function postNote(d, p, text) {
  const el = document.getElementById("updated");
  if (el) el.textContent = "· ukládám poznámku…";
  for (const port of await noteCapablePorts()) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/save_note`,
        { method: "POST", body: JSON.stringify({ date: d, period: p, text }) });
      if (r.ok) {
        const j = await r.json().catch(() => ({ ok: false }));
        const val = text.trim() ? text : null;
        if (j.ok) {
          // Uloženo online.
          (byKey[d + "#" + p] || []).forEach(x => { x.my_note = val; x.note_pending = false; });
          editing = null;
          if (el) el.textContent = "· poznámka uložena";
          render();
          return;
        }
        if (j.queued) {
          // Offline: uloženo do fronty, odešle se, až bude připojení.
          (byKey[d + "#" + p] || []).forEach(x => { x.my_note = val; x.note_pending = true; });
          editing = null;
          if (el) el.textContent = "· offline – uloženo, odešle se po připojení";
          render();
          return;
        }
      }
    } catch (e) { /* zkus dalsi port */ }
  }
  if (el) el.textContent = "· uložení selhalo (běží aplikace na pozadí?)";
}

async function ensureWeekFetched(mondayStr) {
  // Kdyz tyden jeste nemame stazeny, dotahne ho na vyzadani a prenacte stranku.
  if (FETCHED_WEEKS.includes(mondayStr) || weekFetching) return;
  weekFetching = true;
  const el = document.getElementById("updated");
  if (el) el.textContent = "· načítám týden…";
  for (const p of await noteCapablePorts()) {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/fetch_week?monday=${mondayStr}`,
                            { mode: "cors" });
      if (!r.ok) continue;
      const j = await r.json().catch(() => ({}));
      if (j.ok) { location.reload(); return; }  // stazeno -> prenacti; jinak (offline) neopakuj
    } catch (e) { /* zkus dalsi port */ }
  }
  weekFetching = false;
  if (el) el.textContent = "· týden nelze načíst (jsi offline?)";
}

async function doRefresh() {
  const el = document.getElementById("updated");
  const btn = document.getElementById("refresh");
  el.textContent = "· aktualizuji…";
  btn.disabled = true;
  // Spustit progresivni refresh: obnovi vsechny tydny od tohoto tydne az po
  // zobrazeny (zobrazeny prvni). Vysledky pribyvaji postupne (viz pollRefresh).
  const until = fmt(current);
  for (const p of await noteCapablePorts()) {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/refresh?until=${until}`, { mode: "cors" });
      if (!r.ok) continue;
      const j = await r.json().catch(() => ({}));
      if (j.ok) {
        try {
          sessionStorage.setItem("refPort", p);
          sessionStorage.setItem("refDone", "0");
        } catch (e) {}
        pollRefresh(p);
        return;
      }
    } catch (e) { /* zkus dalsi port */ }
  }
  btn.disabled = false;
  el.textContent = "· aktualizace se nezdařila (jsi offline?)";
}

// Sleduje stav progresivniho refreshe a po kazdem dokoncenem tydnu prenacte
// stranku (nove stazene tydny se tak objevuji postupne). Stav prezije reload
// v sessionStorage (refPort/refDone), takze polling po prenacteni pokracuje.
async function pollRefresh(p) {
  const el = document.getElementById("updated");
  const btn = document.getElementById("refresh");
  if (btn) btn.disabled = true;
  let lastDone = 0;
  try { lastDone = +(sessionStorage.getItem("refDone") || 0); } catch (e) {}
  try {
    const r = await fetch(`http://127.0.0.1:${p}/refresh_status`, { mode: "cors" });
    const st = await r.json();
    if (el && st.total) {
      el.textContent = st.active
        ? `· aktualizuji… (${st.done}/${st.total} týdnů)`
        : `· aktualizováno (${st.done}/${st.total} týdnů)`;
    }
    if (st.done > lastDone || !st.active) {
      // Novy tyden hotovy (nebo konec) -> ukazat ho (prenacist).
      try { sessionStorage.setItem("refDone", st.done); } catch (e) {}
      if (!st.active) {
        try { sessionStorage.removeItem("refPort"); sessionStorage.removeItem("refDone"); } catch (e) {}
      }
      location.reload();
      return;
    }
  } catch (e) {
    // Server nedostupny -> ukoncit sledovani.
    try { sessionStorage.removeItem("refPort"); sessionStorage.removeItem("refDone"); } catch (e) {}
    if (btn) btn.disabled = false;
    if (el) el.textContent = "· aktualizace se nezdařila (jsi offline?)";
    return;
  }
  setTimeout(() => pollRefresh(p), 800);
}

function initStatus() {
  const el = document.getElementById("updated");
  const btn = document.getElementById("refresh");
  if (!el) return;

  // Behem probihajici aktualizace je tlacitko nedostupne.
  if (btn) btn.disabled = PENDING;

  if (PENDING) {
    // Zobrazit hned z cache; pockat na dokonceni fetche a prenacist.
    el.textContent = "· aktualizuji…";
    let n = 0;
    try { n = +(sessionStorage.getItem("rr") || 0); } catch (e) {}
    if (n < 8) {
      try { sessionStorage.setItem("rr", n + 1); } catch (e) {}
      setTimeout(() => location.reload(), n === 0 ? 9000 : 3000);
    } else {
      el.textContent = "· aktualizace se nezdařila (poslední známý rozvrh)";
    }
    return;
  }

  try { sessionStorage.removeItem("rr"); } catch (e) {}
  if (FETCHED_AT) {
    const d = new Date(FETCHED_AT);
    if (!isNaN(d)) {
      const pad = x => String(x).padStart(2, "0");
      el.textContent = `· aktualizováno ${d.getDate()}. ${d.getMonth() + 1}. ` +
                       `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }
  }
}
const DAYNAMES = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek"];

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Index DU/testu: datum#predmet -> [{kind, title}]
const asgByKey = {};
ASSIGNMENTS.forEach(a => {
  if (!a.subject) return;
  const k = a.date + "#" + a.subject;
  (asgByKey[k] = asgByKey[k] || []).push(a);
});

function fmt(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function human(d) { return `${d.getDate()}. ${d.getMonth() + 1}.`; }
function monday(d) {
  const x = new Date(d);
  const wd = (x.getDay() + 6) % 7;  // 0 = pondeli
  x.setDate(x.getDate() - wd);
  x.setHours(0, 0, 0, 0);
  return x;
}
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

// Casy period - bereme prvni NEPRAZDNY cas (zrusena hodina byva bez casu).
const ptime = {};
LESSONS.forEach(l => {
  if (l.period != null && l.start_time && !ptime[l.period])
    ptime[l.period] = {s: l.start_time, e: l.end_time};
});

// Periody serazene podle casu; precislovane od 1 (EduPage cisluje jinak).
const periods = [...new Set(LESSONS.filter(l => l.period != null).map(l => l.period))];
periods.sort((a, b) => {
  const sa = ptime[a] ? ptime[a].s : "99:99";
  const sb = ptime[b] ? ptime[b].s : "99:99";
  return sa < sb ? -1 : sa > sb ? 1 : a - b;
});
const dispNum = {};
periods.forEach((p, i) => dispNum[p] = i + 1);

// Index: datum#perioda -> [lekce]
const byKey = {};
LESSONS.forEach(l => {
  if (l.period == null) return;
  const k = l.date + "#" + l.period;
  (byKey[k] = byKey[k] || []).push(l);
});

// Celodenni udalosti (svatky / volno) podle data.
// Druh celodenni udalosti (kvuli barve). Pouzije pole z backendu, jinak (starsi
// cache bez pole) odvodi z textu: Svátek/Prázdniny/Volno = svatek, jinak akce.
function allDayKind(l) {
  if (l.all_day_kind) return l.all_day_kind;
  const t = l.note || "";
  return (t.startsWith("Svátek") || t.startsWith("Prázdniny") ||
          t.startsWith("Volno") || t.startsWith("Ředitelské")) ? "holiday" : "event";
}

const allDayByDate = {};
LESSONS.forEach(l => {
  if (l.all_day) (allDayByDate[l.date] = allDayByDate[l.date] || []).push(
    { label: l.note || "Volno", kind: allDayKind(l) });
});

const todayMon = monday(new Date());
const todayStr = fmt(new Date());
// Dozadu lze listovat az k nejstarsimu dni, ktery mame v datech (minule dny se
// v cache uchovavaji).
let minMon = new Date(todayMon);
(function () {
  const dates = LESSONS.map(l => l.date).filter(Boolean).sort();
  if (dates.length) {
    const em = monday(new Date(dates[0] + "T00:00:00"));
    if (em < minMon) minMon = em;
  }
})();

// O vikendu (so/ne) rovnou dalsi tyden.
const wd = new Date().getDay();  // 0 = ne, 6 = so
let current = (wd === 0 || wd === 6) ? addDays(todayMon, 7) : new Date(todayMon);

function cellHtml(items) {
  return items.map(l => {
    const room = (l.classrooms || []).join(", ");
    const teacher = (l.teachers || []).join(", ");
    const ch = l.changes || [];

    if (l.is_cancelled) {
      // Preskrtnuty predmet + pod nim "odpadá"/"přesunuto".
      const label = l.strike_label || "odpadá";
      if (l.subject)
        return `<div class='cancelled'><div class='subject'>${esc(l.subject)}</div>` +
               `<div class='meta'>${esc(label)}</div></div>`;
      return `<div class='cancelled'><div class='subject'>${esc(label)}</div></div>`;
    }

    // Skolni udalost (nema predmet, ale ma nazev v note).
    const title = l.subject || l.note;
    if (!title) return "";

    // Meta radek: ucebna a ucitel; zmenene pole (proti stalemu rozvrhu) zvyraznime.
    const roomHtml = room
      ? `<span class='${ch.includes("room") ? "chg" : ""}'>uč. ${esc(room)}</span>` : "";
    const teacherHtml = teacher
      ? `<span class='${ch.includes("teacher") ? "chg" : ""}'>${esc(teacher)}</span>` : "";
    const meta = [roomHtml, teacherHtml].filter(Boolean).join(" · ");

    let extra = "";

    // DU / testy zadane na tento den a predmet.
    if (l.subject) {
      (asgByKey[l.date + "#" + l.subject] || []).forEach(a => {
        const label = a.kind === "DU" ? "DÚ" : a.kind;
        extra += `<div class='meta asg'>${label}: ${esc(a.title)}</div>`;
      });
    }

    // Osobni poznamka k hodine (zelene) - klikem lze upravit/pridat/smazat.
    // Editovat lze jen realne hodiny s predmetem (ne udalosti).
    let noteBlock = "";
    if (l.subject && l.period != null) {
      const editKey = l.date + "#" + l.period;
      if (editing === editKey) {
        const cur = l.my_note || "";
        noteBlock =
          `<div class='noteeditor' onclick='event.stopPropagation()'>` +
          `<textarea id='noteInput' rows='2' placeholder='Poznámka k hodině…'>${esc(cur)}</textarea>` +
          `<div class='notebtns'>` +
          `<button onclick="saveNote('${l.date}',${l.period})">Uložit</button>` +
          `<button onclick="cancelNote()">Zrušit</button>` +
          (l.my_note ? `<button class='del' onclick="deleteNote('${l.date}',${l.period})">Smazat</button>` : "") +
          `</div></div>`;
      } else {
        const pend = l.note_pending
          ? `<div class='notepending'>⏳ čeká na odeslání</div>` : "";
        if (l.my_note) {
          noteBlock = `<div class='meta note noteedit' onclick="editNote('${l.date}',${l.period})">${esc(l.my_note)}</div>` + pend;
        } else {
          noteBlock = `<div class='noteadd' onclick="editNote('${l.date}',${l.period})">＋ poznámka</div>` + pend;
        }
      }
    }

    const subjClass = ch.includes("subject") ? "subject chg" : "subject";
    return `<div><div class='${subjClass}'>${esc(title)}</div>` +
           (meta ? `<div class='meta'>${meta}</div>` : "") + extra + noteBlock + "</div>";
  }).join("");
}

function render() {
  const days = [0, 1, 2, 3, 4].map(i => addDays(current, i));
  document.getElementById("range").textContent =
    `Týden ${human(days[0])} – ${human(days[4])}${days[4].getFullYear()}`;

  let html = "<table><thead><tr><th class='day'>Den</th>";
  periods.forEach(p => {
    const t = ptime[p] || {};
    html += `<th>${dispNum[p]}.<small>${t.s || ""}–${t.e || ""}</small></th>`;
  });
  html += "</tr></thead><tbody>";

  days.forEach((d, i) => {
    const isToday = fmt(d) === todayStr;
    html += `<tr class='${isToday ? "today" : ""}'>` +
            `<td class='day'>${DAYNAMES[i]}<small>${human(d)}</small></td>`;

    const events = allDayByDate[fmt(d)];
    if (events && events.length) {
      // Celodenni udalost pres vsechny hodiny daneho dne. Svatky/prazdniny zelene,
      // skolni akce fialove; kdyz jsou v jednom dni obe, prevazi barva akce.
      const uniq = [...new Map(events.map(e => [e.label, e])).values()];
      const label = uniq.map(e => esc(e.label)).join(" · ");
      const kind = uniq.some(e => e.kind === "event") ? "event" : "holiday";
      html += `<td class='allday ${kind}' colspan='${periods.length}'>${label}</td>`;
    } else {
      periods.forEach(p => {
        const items = byKey[fmt(d) + "#" + p] || [];
        if (items.length === 0) html += "<td class='cell'></td>";
        else html += `<td class='cell has'>${cellHtml(items)}</td>`;
      });
    }
    html += "</tr>";
  });
  html += "</tbody></table>";
  document.getElementById("grid").innerHTML = html;

  document.getElementById("prev").disabled = current <= minMon;
  document.getElementById("next").disabled = false;  // dopredu bez omezeni

  // Kdyz tenhle tyden jeste nemame stazeny, dotahni ho na vyzadani.
  ensureWeekFetched(fmt(current));
}

// Zachovat zobrazeny tyden pres reload (v adrese #w=<offset tydnu>).
(function () {
  const m = /w=(-?\d+)/.exec(location.hash);
  if (m) current = addDays(todayMon, parseInt(m[1], 10) * 7);
})();
function setHash() {
  location.hash = "w=" + Math.round((current - todayMon) / 604800000);
}

document.getElementById("prev").onclick = () => { current = addDays(current, -7); setHash(); render(); };
document.getElementById("next").onclick = () => { current = addDays(current, 7); setHash(); render(); };
document.getElementById("today").onclick = () => {
  current = (new Date().getDay() % 6 === 0) ? addDays(todayMon, 7) : new Date(todayMon);
  setHash();
  render();
};
document.getElementById("refresh").onclick = doRefresh;
render();
initStatus();

// Kdyz probihal progresivni refresh, po prenacteni pokracuj ve sledovani.
(function () {
  try {
    const rp = sessionStorage.getItem("refPort");
    if (rp !== null) pollRefresh(+rp);
  } catch (e) {}
})();

// Upozorneni na novou funkci - ukaz, dokud ho uzivatel nezavre (pamatuje se).
(function () {
  const FEAT = "feat_notify_grades_v1";
  try { if (localStorage.getItem(FEAT)) return; } catch (e) {}
  const bar = document.getElementById("newfeat");
  if (!bar) return;
  bar.classList.add("show");
  const btn = document.getElementById("newfeatClose");
  if (btn) btn.onclick = () => {
    bar.classList.remove("show");
    try { localStorage.setItem(FEAT, "1"); } catch (e) {}
  };
})();
</script>
</body>
</html>
"""


def generate_html(
    lessons: list[dict],
    assignments: list[dict] | None = None,
    fetched_at: str | None = None,
    pending: bool = False,
) -> str:
    return (
        _TEMPLATE
        .replace("__LESSONS__", json.dumps(lessons, ensure_ascii=False))
        .replace("__ASSIGNMENTS__", json.dumps(assignments or [], ensure_ascii=False))
        .replace("__DAYS_AHEAD__", str(core.DAYS_AHEAD))
        .replace("__FETCHED_AT__", fetched_at or "")
        .replace("__PENDING__", "true" if pending else "false")
        .replace("__FETCHED_WEEKS__", json.dumps(core.load_fetched_weeks()))
        .replace("__PORTS__", json.dumps(
            list(range(core.CONTROL_PORT_BASE,
                       core.CONTROL_PORT_BASE + core.CONTROL_PORT_COUNT))))
    )


def _write_html(pending: bool) -> None:
    """Vygeneruje HTML z aktualni cache a atomicky ho zapise do OUTPUT_FILE."""
    html = generate_html(
        core.load_cache(), core.load_assignments(), core.load_fetched_at(), pending
    )
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_FILE.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, OUTPUT_FILE)  # atomicky, aby reload necetl rozepsany soubor


def open_timetable(refresh: bool = False) -> Path:
    """Zobrazi rozvrh hned z cache a (pri refresh) na pozadi stahne aktualni.

    Faze 1: okamzite vykresli posledni cache a otevre prohlizec (zadne cekani).
    Faze 2: pri refresh stahne aktualni rozvrh a prepise HTML; otevrena stranka
    se sama prenacte na aktualni data (a zachova zobrazeny tyden).
    """
    # Faze 1 - okamzite.
    _write_html(pending=refresh)
    url = OUTPUT_FILE.as_uri() + "?v=" + str(int(time.time()))
    webbrowser.open(url)

    # Faze 2 - stazeni na pozadi (blokuje tuto funkci, ne prohlizec).
    if refresh:
        core.refresh_cache()
        _write_html(pending=False)

    return OUTPUT_FILE


if __name__ == "__main__":
    path = open_timetable(refresh=True)
    print(f"Rozvrh otevren: {path}")
