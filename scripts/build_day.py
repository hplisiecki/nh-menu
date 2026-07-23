#!/usr/bin/env python3
"""
Build a single day's Nowe Horyzonty menu page.

Usage:
    python3 build_day.py 2026-07-25 [--include-morning] [--gap 45]

Pipeline:
  1. Fetch (or reuse a <5min-old cache of) the festival program API.
  2. Filter to real film screenings (rodzaj/film==true) on the given date.
  3. Cluster screenings into blocks by start-time gap (default 45min).
  4. Drop the first (morning) block unless --include-morning is passed.
  5. Look up each film's description in data/movies_db.json.
     Films missing a description are flagged — the page renders a
     "description pending" placeholder and the script prints/saves a
     todo list of {id, title, www} for research to be done separately,
     then movies_db.json updated, then this script re-run.
  6. Render <date>/index.html and refresh the landing index.html.
"""
import json
import os
import sys
import time
import html
import argparse
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_PATH = os.path.join(DATA_DIR, "nh_program_cache.json")
DB_PATH = os.path.join(DATA_DIR, "movies_db.json")
DAYS_REGISTRY_PATH = os.path.join(DATA_DIR, "days.json")
API_URL = "https://www.nowehoryzonty.pl/open-api/program"
EXPECTED_VERSION = "2.1"
CACHE_MAX_AGE_S = 5 * 60

BLOCK_LABELS = ["Block 1", "Block 2", "Block 3", "Block 4", "Block 5", "Block 6"]
BLOCK_TAGS = ["Early Afternoon", "Late Afternoon", "Evening", "Night", "Late Night", "After Hours"]


def fetch_program():
    """Refresh no more than every ~5min; keep last good response on failure."""
    if os.path.exists(CACHE_PATH):
        age = time.time() - os.path.getmtime(CACHE_PATH)
        if age < CACHE_MAX_AGE_S:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
    try:
        req = urllib.request.Request(API_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("version") != EXPECTED_VERSION:
            print(f"WARNING: API version {data.get('version')} != expected {EXPECTED_VERSION}", file=sys.stderr)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return data
    except Exception as exc:
        if os.path.exists(CACHE_PATH):
            print(f"WARNING: live fetch failed ({exc}); using stale cache", file=sys.stderr)
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        raise


def load_db():
    if os.path.exists(DB_PATH):
        with open(DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def compute_blocks(data, date_ddmmyyyy, gap_minutes, include_morning):
    FMT = "%d-%m-%Y %H:%M"
    events = []
    for t in data["tytuly"]:
        if not t.get("film", False):
            continue
        dur = t.get("czasTrwaniaZestawu") or t.get("czasTrwania") or 90
        for s in t.get("seanse", []):
            dc = s.get("dataCzas", "")
            if not dc.startswith(date_ddmmyyyy):
                continue
            start = datetime.strptime(dc, FMT)
            end = start + timedelta(minutes=dur)
            events.append({"start": start, "end": end, "title": t, "seance": s, "dur": dur})

    if not events:
        return []

    events.sort(key=lambda e: e["start"])
    blocks = []
    cur = [events[0]]
    for e in events[1:]:
        gap = (e["start"] - cur[-1]["start"]).total_seconds() / 60
        if gap >= gap_minutes:
            blocks.append(cur)
            cur = [e]
        else:
            cur.append(e)
    blocks.append(cur)

    if not include_morning and len(blocks) > 1:
        blocks = blocks[1:]

    out = []
    for block in blocks:
        block.sort(key=lambda e: e["start"])
        block_out = []
        for e in block:
            t = e["title"]
            block_out.append({
                "id": t["id"],
                "tytulPl": t["tytulPl"],
                "tytulEn": t.get("tytulEn"),
                "rezyser": t.get("rezyser"),
                "kraj": t.get("kraj"),
                "rok": t.get("rok"),
                "czasTrwania": e["dur"],
                "glownaSekcja": t.get("glownaSekcja"),
                "www": t.get("www"),
                "poster": (t.get("fotos") or {}).get("nazwaPliku"),
                "sala": e["seance"].get("sala"),
                "start": e["start"].strftime("%H:%M"),
                "end": e["end"].strftime("%H:%M"),
                "qa": e["seance"].get("qa", False),
                "zestaw": t.get("zestaw", False),
                "filmyWZestawie": t.get("filmyWZestawie"),
            })
        out.append(block_out)
    return out


def e(s):
    return html.escape(s or "", quote=True)


def fmt_dur(mins):
    m = int(round(mins))
    h, r = divmod(m, 60)
    if h and r:
        return f"{h}h {r:02d}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def film_card(film, block_idx, section_colors, db, missing):
    color = section_colors.get(film["glownaSekcja"], "#999999")
    dbrec = db.get(str(film["id"]))
    if dbrec and dbrec.get("one_liner"):
        one_liner = dbrec["one_liner"]
        long_desc = dbrec.get("long_desc") or ""
    else:
        missing.append({"id": film["id"], "tytulPl": film["tytulPl"], "www": film["www"]})
        one_liner = "Description pending — not yet researched."
        long_desc = ""

    en = film.get("tytulEn") or ""
    show_en = en and en != film["tytulPl"]
    qa = film.get("qa")
    short = film.get("filmyWZestawie")
    short_line = ""
    if film.get("zestaw") and short:
        s0 = short[0]
        short_line = (f'<p class="short-note">+ preceded by short: <em>{e(s0.get("tytulPl"))}</em>'
                      f' ({fmt_dur(s0.get("czasTrwania", 0))})</p>')

    qa_chip = '<span class="chip chip-qa">Q&amp;A after</span>' if qa else ""
    poster = film.get("poster")
    poster_html = f'<img class="poster" src="{e(poster)}" alt="" loading="lazy">' if poster else ""

    return f'''
    <details class="film" data-block="{block_idx}">
      <summary>
        <span class="dot" style="--dot:{color}" aria-hidden="true"></span>
        <span class="summary-main">
          <span class="row-top">
            <time class="time">{e(film["start"])}</time>
            <span class="title">{e(film["tytulPl"])}</span>
          </span>
          <span class="one-liner">{e(one_liner)}</span>
        </span>
        <span class="chev" aria-hidden="true"></span>
      </summary>
      <div class="film-body">
        {poster_html}
        <div class="detail-text">
          {f'<p class="title-en">{e(en)}</p>' if show_en else ''}
          <div class="meta-row">
            <span class="chip">{e(film["start"])}–{e(film["end"])}</span>
            <span class="chip">{e(film["sala"])}</span>
            <span class="chip">{fmt_dur(film["czasTrwania"])}</span>
            <span class="chip">{e(film.get("kraj",""))}, {e(str(film.get("rok","")))}</span>
            {qa_chip}
          </div>
          <p class="director">Dir. {e(film.get("rezyser",""))} &nbsp;·&nbsp; <span class="section-name" style="--dot:{color}">{e(film["glownaSekcja"])}</span></p>
          {f'<p class="long-desc">{e(long_desc)}</p>' if long_desc else ''}
          {short_line}
          <a class="site-link" href="{e(film["www"])}" target="_blank" rel="noopener">Festival page ↗</a>
        </div>
      </div>
    </details>'''


def render_day_page(date_iso, date_label, blocks, section_colors, db):
    missing = []
    nav_chips = "\n".join(
        f'<a href="#block-{i}" class="nav-chip"><span class="nav-time">{b[0]["start"]}</span>'
        f'<span class="nav-label">{BLOCK_LABELS[i]}</span></a>'
        for i, b in enumerate(blocks)
    )
    block_sections = []
    for i, block in enumerate(blocks):
        span = f'{block[0]["start"]}–{block[-1]["start"]}'
        cards = "\n".join(film_card(f, i, section_colors, db, missing) for f in block)
        tag = BLOCK_TAGS[i] if i < len(BLOCK_TAGS) else f"Slot {i+1}"
        block_sections.append(f'''
    <section class="block" id="block-{i}">
      <header class="block-header">
        <p class="block-eyebrow">{tag} &nbsp;·&nbsp; starts {span} &nbsp;·&nbsp; {len(block)} films &nbsp;·&nbsp; pick one</p>
        <h2 class="block-title">{BLOCK_LABELS[i]}</h2>
      </header>
      <div class="film-list">
        {cards}
      </div>
    </section>''')
    blocks_html = "\n".join(block_sections)
    total_films = sum(len(b) for b in blocks)

    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nowe Horyzonty — {date_label}</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="masthead">
  <a class="back-link" href="../index.html">← All days</a>
  <p class="eyebrow">Nowe Horyzonty · Wrocław</p>
  <h1>{date_label}</h1>
  <p class="sub">Morning block skipped. {total_films} films across {len(blocks)} blocks — one pick per block. Tap a film to expand.</p>
</div>

<nav class="navbar">
  {nav_chips}
</nav>

{blocks_html}

<footer>
  Data via the Nowe Horyzonty open API (v2.1) · descriptions compiled from festival programme pages · generated for personal use, not an official festival page.
</footer>

<script src="../assets/site.js"></script>
</body>
</html>
'''
    return page, missing, total_films


def update_landing_index(days_registry):
    days = sorted(days_registry.items(), key=lambda kv: kv[0], reverse=True)
    cards = "\n".join(
        f'<a class="day-card" href="{d}/index.html"><span class="day-name">{info["label"]}</span>'
        f'<span class="day-count">{info["films"]} films</span></a>'
        for d, info in days
    )
    page = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nowe Horyzonty — Menu</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<div class="masthead">
  <p class="eyebrow">Nowe Horyzonty · Wrocław</p>
  <h1>Festival Menu</h1>
  <p class="sub">Pick a day to see that day's blocks and films.</p>
</div>
<div class="day-list">
{cards}
</div>
<footer>
  Data via the Nowe Horyzonty open API (v2.1) · generated for personal use, not an official festival page.
</footer>
</body>
</html>
'''
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="Date in YYYY-MM-DD")
    ap.add_argument("--include-morning", action="store_true")
    ap.add_argument("--gap", type=int, default=45, help="Block-clustering gap threshold in minutes")
    args = ap.parse_args()

    date_obj = datetime.strptime(args.date, "%Y-%m-%d")
    date_ddmmyyyy = date_obj.strftime("%d-%m-%Y")
    date_label = date_obj.strftime("%A, %B %-d")

    data = fetch_program()
    section_colors = {s["nazwa"]: s["kolor"] for s in data["sekcje"]}
    db = load_db()

    blocks = compute_blocks(data, date_ddmmyyyy, args.gap, args.include_morning)
    if not blocks:
        print(f"No film screenings found on {args.date}.", file=sys.stderr)
        sys.exit(1)

    page, missing, total_films = render_day_page(args.date, date_label, blocks, section_colors, db)

    day_dir = os.path.join(ROOT, args.date)
    os.makedirs(day_dir, exist_ok=True)
    with open(os.path.join(day_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)

    registry = {}
    if os.path.exists(DAYS_REGISTRY_PATH):
        with open(DAYS_REGISTRY_PATH, encoding="utf-8") as f:
            registry = json.load(f)
    registry[args.date] = {"label": date_label, "films": total_films}
    with open(DAYS_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    update_landing_index(registry)

    print(f"Wrote {day_dir}/index.html ({total_films} films, {len(blocks)} blocks)")
    if missing:
        todo_path = os.path.join(DATA_DIR, f"pending_research_{args.date}.json")
        with open(todo_path, "w", encoding="utf-8") as f:
            json.dump(missing, f, ensure_ascii=False, indent=2)
        print(f"{len(missing)} films need descriptions — see {todo_path}")
    else:
        print("All films had cached descriptions.")


if __name__ == "__main__":
    main()
