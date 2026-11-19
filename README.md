# ManiScope documentation site

Documentation and leaderboard site for the ManiScope benchmark, generated from the
`ManiScope/` repository **without modifying it**. Pure Python, no Node.js.

```
ManiScope_webpage/
├── site.yaml                     site config: title, paper metadata, navigation, links (TODOs marked)
├── build.py                      static site generator  → site/
├── scripts/
│   ├── sync_from_maniscope.py    ManiScope → data/*.json (read-only extraction)
│   ├── crop_overview_tiles.py    formal48-overview.png → assets/img/scenes/<scene>.png
│   ├── process_videos.py         HiFi rollout renders → assets/videos/<scene>_success.mp4 + data/videos.json
│   └── serve.py                  local preview server (--watch rebuilds on change)
├── content/                      hand-written Markdown pages
│   ├── index.md                  home-page abstract
│   ├── usage/*.md                Install & Download, Quick Evaluation, Configurations, Policy Integration, Evaluation Protocol
│   ├── common-issue/*.md         Installation / Evaluation FAQs
│   ├── sim-tasks/index.md        intro text for the task catalogue
│   ├── policies.md, leaderboard.md, community.md
├── data/
│   ├── tasks.json                48 scenes with everything a task page needs (generated)
│   ├── policies.json             policy registry (generated)
│   ├── leaderboard.json          historical results (generated, flagged archival)
│   └── overrides/tasks/*.yaml    optional per-scene manual overrides (description_en, scoring, …)
├── templates/base.html           page shell (header, sidebar, TOC, footer)
├── assets/
│   ├── css/style.css, js/main.js theme toggle, mobile nav, TOC spy, sortable tables, search
│   ├── img/                      logo, overview figure, 48 scene thumbnails
│   ├── img/init/<scene>/         initial-state renders shown on the task page (any number)
│   └── videos/                   <scene>_success.mp4 from scripts/process_videos.py (see README inside)
└── site/                         build output (git-ignored)
```

## Naming and numbering

The paper and the repository README call the benchmark **ManipScope**; only the directory is `ManiScope`.
The paper numbers the task families **D1–D6** (D6 = mixed combinations); the repository registry and the
legacy reports label the mixture family **D7**. `scripts/sync_from_maniscope.py` maps `D7 → D6` for display
(`repo_id` keeps the original) so the site matches the paper without touching the repository.

`data/paper_tables.json` holds numbers transcribed from the paper that are not derivable from the repository
(matched 240-episode success/timing, agent termination and configuration). Family / level / Overall / Pooled
aggregates on the leaderboard are recomputed from per-scene rates and reproduce the paper's Tables 1–3.

## Build

```bash
cd ManipScope_webpage
python3 -m pip install -r requirements.txt
python3 scripts/crop_overview_tiles.py            # optional, needs Pillow + numpy
python3 build.py                                  # → site/
python3 scripts/serve.py --watch                  # http://localhost:8008
```

`serve.py` runs in the foreground; when its terminal closes the server stops and `http://localhost:8008`
stops answering. To keep it alive detached:

```bash
setsid nohup python3 scripts/serve.py --port 8008 > /tmp/manipscope_serve.log 2>&1 &
```

Alternatively open `site/index.html` directly from disk — links are written as `…/index.html` for that purpose.

Requirements: Python ≥ 3.11 with `pyyaml` and `markdown` (`pip install -r requirements.txt`).

## Generated pages

| URL | Source |
| --- | --- |
| `/` | `site.yaml` (paper block) + `content/index.md` + `data/tasks.json` stats |
| `/usage/<slug>/`, `/common-issue/<slug>/` | `content/usage/*.md`, `content/common-issue/*.md` (front matter: `title`, `description`) |
| `/sim-tasks/` | catalogue grouped by axis D1…D7 with thumbnails and tier badges |
| `/sim-tasks/<scene>/` | one page per scene: successful + failed rollout videos, initial-state gallery, info table, instruction templates, scene objects, scoring table, declared `GOAL`, paper-snapshot results, run command |
| `/policies/` | registry from `suite/policies.yaml` |
| `/leaderboard/` | sortable summary + per-scene heat-map from `docs/archive/EVAL_COMPARE.md` |
| `/community/` | `content/community.md` |

## Editing

- **Text pages**: edit Markdown under `content/`. Use `{{rel}}` for root-relative links (e.g. `[x]({{rel}}usage/…/)`). Admonitions: `!!! note "Title"`.
- **Per-scene fixes** without touching ManiScope: create `data/overrides/tasks/<scene>.yaml`, e.g.

  ```yaml
  description_en: Pick up the green bottle, ignoring the brown one.
  scoring:
    - {score: 0,   cond: The brown bottle moved more than the green one, or the green bottle is still on the table.}
    - {score: 100, cond: The green bottle is lifted ≥ 2 cm above its support while held by a gripper.}
  ```

  Then re-run `sync_from_maniscope.py` and `build.py`.
- **Media**: `python3 scripts/process_videos.py` builds one successful rollout per scene (`assets/videos/<scene>_success.mp4`, sped up and annotated) plus `data/videos.json` from the HiFi re-renders (see `assets/videos/README.md`); the home-page source-task graph is `assets/depgraph/index.html` (fallback image `assets/img/source-task-map.png` or `.svg`). Re-run `build` afterwards.
- **English only**: `build.py` aborts if any CJK character reaches the generated HTML (registry fields in Chinese are never rendered; English equivalents live in `scripts/sync_from_maniscope.py`).
- **Navigation / links / authors**: `site.yaml`.
- **Double-blind mode**: `site.anonymous: true` (current default) hides authors, affiliations, the
  citation block, repository / email / community links and the header GitHub button; the Paper and
  Code buttons link back to the home page. Set to `false` after the review period and fill in the
  `paper:` / `links:` blocks.
- **Link style**: `site.clean_urls: false` (default) writes `…/index.html` links so the site works when
  `site/index.html` is opened directly from disk (`file://`) or on hosts without directory-index
  fallback. Set `true` for clean `…/` URLs behind a normal web server.
- **Styling**: `assets/css/style.css` (CSS variables at the top; dark mode via `[data-theme="dark"]`).

## Deploy

`site/` is plain static HTML with relative links. Copy it to any static host or GitHub Pages
(`.nojekyll` is written automatically). Set `site.base_url` in `site.yaml` only if you need absolute URLs.

## Data freshness

`data/*.json` are snapshots. Re-run `scripts/sync_from_maniscope.py` after any change in the benchmark
repository (new scenes, policies, results). The leaderboard is flagged as archival until fresh runs
replace `docs/archive/EVAL_COMPARE.md` as the source.

## GitHub Pages

Public repository: https://github.com/embodied-ai-research/ManipScope_webpage

Website: https://embodied-ai-research.github.io/ManipScope_webpage/

Every push to `main` builds the checked-in data and content with `build.py` and deploys `site/` through `.github/workflows/pages.yml`. In repository Settings → Pages, use **GitHub Actions** as the source. Generated `site/` and legacy `docs/` output are not committed. All links are relative and work under the repository subpath.

The website was migrated from the existing website snapshot at commit `75e3581`. The revised agent tables integrate GPT-6.2 Astra, Gemini 4 Argon and Opus 5.5, each on 240 episodes. The original GPT-6 Astra and Gemini 3.8 Flash results retain the September data. Only aggregate per-scene results are published; organizer-managed formal seeds remain private.

`data/leaderboard.json` is the per-scene source for success aggregates; `data/paper_tables.json` contains matched-episode timing, termination and request settings. Review changes before re-running `scripts/sync_from_maniscope.py`: it imports the legacy benchmark reports and can replace the revised agent data.
