# nh-menu

A personal daily "menu" for the [Nowe Horyzonty](https://www.nowehoryzonty.pl) film
festival in Wrocław — pulls the festival's [open API](https://www.nowehoryzonty.pl/open-api),
groups screenings into non-overlapping time blocks (so you can see, at a glance, which
films compete for the same slot), and shows a one-line hook plus a longer description
for each film.

Published via GitHub Pages.

## Structure

- `assets/` — shared CSS, JS, and the display font used across all day pages
- `data/movies_db.json` — cache of researched film descriptions, keyed by festival film ID,
  reused across days since many films screen more than once during the festival
- `data/days.json` — registry of which day pages exist, used to build the landing page
- `scripts/build_day.py` — generates a day page: fetch the API, filter to real film
  screenings on the given date, cluster into blocks, look up descriptions from the
  cache, render `<date>/index.html`, refresh the landing `index.html`
- `<date>/index.html` — one page per festival day

## Usage

```
python3 scripts/build_day.py 2026-07-26
```

Films not yet in `data/movies_db.json` get a "description pending" placeholder, and
their IDs are written to `data/pending_research_<date>.json` for a research pass
(fetch the festival page + a bit of web search per film) before re-running the script.

By default the first block of the day (typically an early-morning slot) is dropped;
pass `--include-morning` to keep it.
