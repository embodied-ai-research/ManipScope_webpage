#!/usr/bin/env python3
"""ManiScope documentation site generator.

Dependencies: pyyaml, markdown (both usually present in a scientific Python env).
No Node.js required. Output is a fully static site under ./site.

    python3 scripts/sync_from_maniscope.py   # refresh data/*.json from ManiScope (read-only)
    python3 build.py                         # write ./site
    python3 scripts/serve.py                 # preview at http://localhost:8008

Layout of the generated site:
    /                         home (paper-style landing page)
    /usage/<slug>/            markdown docs from content/usage
    /common-issue/<slug>/     markdown docs from content/common-issue
    /sim-tasks/               task catalogue grouped by task family
    /sim-tasks/<scene>/       one page per scene (video, instruction, description, scoring)
    /policies/                integrated policy registry
    /leaderboard/             results table (archival until re-run)
    /community/               markdown
"""
import html
import json
import os
import re
import shutil
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import markdown
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HERE, "content")
DATA = os.path.join(HERE, "data")
TEMPLATES = os.path.join(HERE, "templates")
ASSETS = os.path.join(HERE, "assets")
OUT = os.path.join(HERE, "site")


def asset_url(rel_path):
    """Site-relative asset URL with a short content hash as query string (cache busting)."""
    import hashlib
    with open(os.path.join(HERE, rel_path), "rb") as f:
        digest = hashlib.md5(f.read()).hexdigest()[:8]
    return f"{rel_path}?v={digest}"


_CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
MD_EXT = ["tables", "fenced_code", "toc", "attr_list", "md_in_html", "sane_lists", "def_list", "admonition"]
MD_CFG = {"toc": {"permalink": "#", "toc_depth": "2-3"}}
# Scenes with a separate controlled diagnostic study (content/diagnostics.md); shown as a callout on the scene page.
DIAGNOSTIC_SCENES = {
    "attr_color_block_3way": "A separate version of this task (20 new seeds 200000–200019, two target instructions × two layouts with the red and blue blocks exchanged, "
                             "80 trajectories per checkpoint for π0.5 and Motus, 256-call budget) instantiates the three-level language-following protocol.",
}
# The nine D3 tasks of the 315-episode attribute-selection study (paper §5.3 / Appendix D).
ATTRIBUTE_STUDY_SCENES = {"attr_color_block_3way", "attr_bind_soap_box", "attr_bind_bottle", "attr_size_block_pick",
                          "attr_size_rank_middle", "attr_category_can_plasticbox", "attr_category_press_bell",
                          "attr_color_beat_block", "attr_size_beat_smaller"}


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def render_template(name, **ctx):
    tpl = read(os.path.join(TEMPLATES, name))
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), "")), tpl)


def front_matter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            meta = yaml.safe_load(text[3:end]) or {}
            return meta, text[end + 4:]
    return {}, text


def md_render(text):
    md = markdown.Markdown(extensions=MD_EXT, extension_configs=MD_CFG)
    body = md.convert(text)
    return body, getattr(md, "toc_tokens", [])


def toc_html(tokens):
    if not tokens:
        return ""

    def items(toks):
        out = []
        for t in toks:
            sub = items(t.get("children") or [])
            out.append(f'<li><a href="#{esc(t["id"])}">{esc(t["name"])}</a>{sub}</li>')
        return "<ul>" + "".join(out) + "</ul>" if out else ""
    return '<div class="toc-title">On this page</div>' + items(tokens)


def rel_prefix(out_path):
    """Relative path from a page directory back to site root ('' or '../' * n)."""
    depth = out_path.strip("/").count("/")
    return "../" * depth


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


class Site:
    def __init__(self):
        self.cfg = yaml.safe_load(read(os.path.join(HERE, "site.yaml")))
        # cache-busting version for style.css/main.js: browsers and mirror caches otherwise keep
        # serving stale assets after a rebuild (recurring problem for collaborators)
        import hashlib
        h = hashlib.sha256()
        for f in ("assets/css/style.css", "assets/js/main.js", "assets/js/i18n.js", "data/i18n-zh.json"):
            h.update(open(os.path.join(HERE, f), "rb").read())
        self.asset_v = h.hexdigest()[:10]
        self.clean_urls = bool(self.cfg["site"].get("clean_urls", False))
        self.tasks = json.load(open(os.path.join(DATA, "tasks.json"), encoding="utf-8"))
        self.policies = json.load(open(os.path.join(DATA, "policies.json"), encoding="utf-8"))
        lb_path = os.path.join(DATA, "leaderboard.json")
        self.leaderboard = json.load(open(lb_path, encoding="utf-8")) if os.path.exists(lb_path) else None
        pt_path = os.path.join(DATA, "paper_tables.json")
        self.paper_tables = json.load(open(pt_path, encoding="utf-8")) if os.path.exists(pt_path) else {}
        pa_path = os.path.join(DATA, "policy_audit.json")
        self.audit = json.load(open(pa_path, encoding="utf-8")) if os.path.exists(pa_path) else {}
        vd_path = os.path.join(DATA, "videos.json")
        self.videos = json.load(open(vd_path, encoding="utf-8")) if os.path.exists(vd_path) else {}
        if self.leaderboard:
            self.normalise_leaderboard()
        self.scene_index = {sc["name"]: (d, sc) for d in self.tasks["dimensions"] for sc in d["scenes"]}
        self.depgraph = self.load_depgraph()
        self.search_docs = []
        self.pages = 0

    def load_depgraph(self):
        """Scene -> RoboTwin base-task dependencies, read from the `const DATA = {...}` block of the
        interactive graph at assets/depgraph/index.html. Returns None when the graph is absent."""
        p = os.path.join(ASSETS, "depgraph", "index.html")
        if not os.path.exists(p):
            return None
        m = re.search(r"const DATA = (\{.*?\});\n", read(p), re.S)
        if not m:
            return None
        data = json.loads(m.group(1))
        base = data["base"]
        use = {b: 0 for b in base}
        n_edges = 0
        for s in data["scenes"]:
            for i in s["deps"]:
                use[base[i - 1]] += 1
                n_edges += 1
        used = [b for b in base if use[b]]
        return {"base": base, "scenes": data["scenes"], "use": use, "n_base": len(base), "n_used": len(used),
                "unused": [b for b in base if not use[b]], "n_edges": n_edges,
                "top": sorted(used, key=lambda b: (-use[b], base.index(b)))}

    # ---- leaderboard data -------------------------------------------------------
    def normalise_leaderboard(self):
        """Apply site.yaml exclude/rename, then compute the paper's aggregates from per-scene rates:
        family means, level means, family-balanced Overall (Eq. 1 in the paper) and Pooled success."""
        lb = self.leaderboard
        cfg = self.cfg.get("leaderboard") or {}
        excluded = set(cfg.get("exclude") or [])
        rename = cfg.get("rename") or {}
        agents = set(cfg.get("agents") or [])

        def nm(p):
            return rename.get(p, p)
        lb["policies"] = [nm(p) for p in lb["policies"] if p not in excluded]
        order = {n: i for i, n in enumerate(cfg.get("order") or [])}
        lb["policies"].sort(key=lambda p: (order.get(p, len(order)), 0))   # stable: unlisted keep data order
        lb["episodes"] = {nm(k): v for k, v in lb["episodes"].items() if k not in excluded}
        lb["per_scene"] = {sc: {nm(k): v for k, v in row.items() if k not in excluded} for sc, row in lb["per_scene"].items()}
        lb["overall_pooled_reported"] = {nm(k): v for k, v in lb.get("overall", {}).items() if k not in excluded}
        lb["agents"] = [p for p in lb["policies"] if p in agents]
        lb["learned"] = [p for p in lb["policies"] if p not in agents]

        dims = self.tasks["dimensions"]
        agg = {}
        for p in lb["policies"]:
            fam, tier_acc = {}, {}
            rates = []
            for d in dims:
                vals = [lb["per_scene"][sc["name"]][p]["rate"] for sc in d["scenes"]
                        if sc["name"] in lb["per_scene"] and lb["per_scene"][sc["name"]].get(p)]
                if vals:
                    fam[d["id"]] = sum(vals) / len(vals)
                for sc in d["scenes"]:
                    r = lb["per_scene"].get(sc["name"], {}).get(p)
                    if r:
                        tier_acc.setdefault(sc["tier"], []).append(r["rate"])
                        rates.append(r["rate"])
            agg[p] = {
                "family": fam,
                "tier": {t: sum(v) / len(v) for t, v in tier_acc.items()},
                "overall": sum(fam.values()) / len(fam) if fam else None,
                "pooled": sum(rates) / len(rates) if rates else None,   # equal episodes per scene → mean of rates
                "n_scenes": len(rates),
            }
        lb["agg"] = agg

    # ---- links ------------------------------------------------------------------
    _HREF_RE = re.compile(r'(href=")([^"]*)(")')

    def fix_links(self, html_out):
        """Directory-style links ("sim-tasks/", "../") only resolve behind a web server.
        Unless site.clean_urls is true, append index.html so the site also works when
        opened straight from disk (file://) or from a static host without index fallback."""
        if self.clean_urls:
            return html_out

        def repl(m):
            href = m.group(2)
            if not href or href.startswith(("#", "mailto:", "javascript:")) or "://" in href:
                if href == "":
                    return m.group(1) + "index.html" + m.group(3)
                return m.group(0)
            path, _, frag = href.partition("#")
            if path == "" or path.endswith("/"):
                path += "index.html"
            return m.group(1) + path + ("#" + frag if frag else "") + m.group(3)
        return self._HREF_RE.sub(repl, html_out)

    # ---- chrome ---------------------------------------------------------------
    def sidebar(self, current, rel):
        def link(label, href, cls=""):
            if href.strip("/") == "participate":
                cls += " nav-evaluate"
            active = " active" if href.strip("/") == current.strip("/") else ""
            return f'<a class="nav-link{cls}{active}" href="{rel}{href}">{esc(label)}</a>'

        parts = []
        for item in self.cfg["nav"]:
            if "items" in item or item.get("auto"):
                open_attr = ""
                inner = []
                if item.get("auto") == "tasks":
                    for d in self.tasks["dimensions"]:
                        sub = "".join(link(f'{sc["name"]}', f'sim-tasks/{sc["name"]}/', " small") for sc in d["scenes"])
                        # open the axis that contains the current scene; on the overview page open all axes
                        on_overview = current.strip("/") == item["href"].strip("/")
                        in_group = any(current.strip("/") == f'sim-tasks/{sc["name"]}' for sc in d["scenes"])
                        d_open = " open" if (on_overview or in_group) else ""
                        label = f'{esc(d["id"])} · {esc(d["short_en"])} <span class="count">{len(d["scenes"])}</span>'
                        inner.append(f'<details class="nav-group nested"{d_open}><summary>{label}</summary>{sub}</details>')
                    if current.startswith("sim-tasks"):
                        open_attr = " open"
                    head = link("Overview", item["href"])
                    inner.insert(0, head)
                else:
                    for it in item["items"]:
                        inner.append(link(it["label"], it["href"]))
                    if any(current.strip("/") == it["href"].strip("/") for it in item["items"]):
                        open_attr = " open"
                parts.append(f'<details class="nav-group"{open_attr}><summary>{esc(item["label"])}</summary>{"".join(inner)}</details>')
            else:
                parts.append(link(item["label"], item["href"]))
        return "".join(parts)

    def header_links(self, rel):
        out = []
        if self.cfg["site"].get("anonymous"):
            return ""
        for l in self.cfg.get("header_links", []):
            href = l["href"] if l["href"].startswith("http") else rel + l["href"]
            icon = ""
            if l.get("icon") == "github":
                icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2.2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1.1 1.9 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.7 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .5z"/></svg>'
            external = ' target="_blank" rel="noopener"' if href.startswith('http') else ''
            out.append(f'<a class="header-link{" has-icon" if icon else ""}" href="{esc(href)}"{external} title="{esc(l["label"])}" aria-label="{esc(l["label"])}">{icon}<span>{esc(l["label"])}</span></a>')
        return "".join(out)

    def robots_meta(self):
        """Anonymous builds are for reviewers only: keep them out of search indexes so they cannot be
        linked to the later public site. The public build carries no robots restriction."""
        return '<meta name="robots" content="noindex, nofollow">' if self.cfg["site"].get("anonymous") else ""

    def page(self, out_path, title, content, toc="", description="", body_class="", extra_scripts="", search_text=None):
        rel = rel_prefix(out_path)
        current = out_path.rsplit("index.html", 1)[0]
        site = self.cfg["site"]
        html_out = render_template(
            "base.html", lang=site.get("language", "en"), title=esc(title), site_name=esc(site["name"]),
            description=esc(description or site.get("description", "")), rel=rel, body_class=body_class, robots=self.robots_meta(),
            header_links=self.header_links(rel), sidebar=self.sidebar(current, rel), content=content, toc=toc,
            footer_left=f'© {date.today().year} {esc(site["name"])}'
                        + (f' · {esc(site["version"])}' if site.get("version") else ""),
            extra_scripts=extra_scripts, asset_v=self.asset_v, clean_urls="true" if self.clean_urls else "false")
        html_out = self.fix_links(html_out)
        m = _CJK_RE.search(html_out)
        if m:
            ctx = html_out[max(0, m.start() - 60): m.end() + 60].replace("\n", " ")
            raise SystemExit(f"CJK text in {out_path}: …{ctx}…  (site must be English only)")
        write(os.path.join(OUT, out_path), html_out)
        self.pages += 1
        self.search_docs.append({"title": title, "url": current, "text": (search_text if search_text is not None else strip_tags(content))[:1200]})

    # ---- markdown documents ---------------------------------------------------
    def doc_placeholders(self, text):
        """Outward links kept configurable in site.yaml: the benchmark repository and the
        submission entry point. `submit` falls back to the repository when it is unset."""
        links = self.cfg.get("links", {})
        repo = links.get("code") or "#"      # "#" while the repository is not public
        submit = links.get("submit") or repo
        return text.replace("{{submit}}", submit).replace("{{repo}}", repo)

    def build_markdown_dir(self, sub):
        src = os.path.join(CONTENT, sub)
        if not os.path.isdir(src):
            return
        for fn in sorted(os.listdir(src)):
            if not fn.endswith(".md"):
                continue
            meta, body = front_matter(read(os.path.join(src, fn)))
            slug = os.path.splitext(fn)[0]
            out_path = f"{sub}/index.html" if slug == "index" else f"{sub}/{slug}/index.html"
            rendered, toks = md_render(self.doc_placeholders(body.replace("{{rel}}", rel_prefix(out_path))))
            title = meta.get("title", slug.replace("-", " ").title())
            header = f'<h1>{esc(title)}</h1>' + (f'<p class="lead">{esc(meta["description"])}</p>' if meta.get("description") else "")
            self.page(out_path, title, header + rendered, toc_html(toks), description=meta.get("description", ""))

    def build_markdown_file(self, sub, out_path):
        p = os.path.join(CONTENT, sub)
        meta, body = front_matter(read(p))
        rendered, toks = md_render(self.doc_placeholders(body.replace("{{rel}}", rel_prefix(out_path))))
        title = meta.get("title", "Untitled")
        header = f'<h1>{esc(title)}</h1>' + (f'<p class="lead">{esc(meta["description"])}</p>' if meta.get("description") else "")
        self.page(out_path, title, header + rendered, toc_html(toks), description=meta.get("description", ""))

    # ---- home -------------------------------------------------------------------
    def build_home(self):
        cfg = self.cfg
        site, paper, links = cfg["site"], cfg["paper"], cfg["links"]
        rel = ""
        meta, body = front_matter(read(os.path.join(CONTENT, "index.md"))) if os.path.exists(os.path.join(CONTENT, "index.md")) else ({}, "")
        abstract_html, _ = md_render(body.replace("{{rel}}", rel))
        anon = bool(site.get("anonymous"))
        if anon:
            author_block = ""
            # Paper button links back to this page; the Code button may point at the anonymized
            # benchmark repository (an identity-free org), but never at a TODO placeholder.
            code = links.get("code") or ""
            paper_href, code_href = "", (code if code.startswith("http") and "TODO" not in code else "")
            meta_block = ""
            cite_block = ""
        else:
            authors = " ".join(
                f'<span class="author">{esc(a["name"])}<sup>{esc(a.get("affil", ""))}{esc(a.get("mark", ""))}</sup></span>'
                for a in paper.get("authors", []))
            affils = " · ".join(f'<span><sup>{esc(a["id"])}</sup>{esc(a["name"])}</span>' for a in paper.get("affiliations", []))
            author_block = f'<div class="authors">{authors}</div><div class="affils">{affils}</div><div class="marks">{esc(paper.get("marks", ""))}</div>'
            paper_href, code_href = links.get("paper") or "", links.get("code") or ""
            meta_block = ""
            if links.get("email"):
                meta_block = ('<dl class="meta-grid"><div><dt>Email</dt><dd>'
                              f'<a href="mailto:{esc(links["email"])}">{esc(links["email"])}</a>'
                              '</dd></div></dl>')
            cite_block = f'<section class="home-citation" id="cite"><h2>Cite our work</h2><pre><code>{esc(paper.get("bibtex", ""))}</code></pre></section>'
        n_scenes = sum(len(d["scenes"]) for d in self.tasks["dimensions"])
        n_pol = len(self.leaderboard["learned"]) if self.leaderboard else len(self.policies["policies"])
        n_ag = len(self.leaderboard["agents"]) if self.leaderboard else 0
        stats = [
            (n_scenes, "evaluation scenes"), (len(self.tasks["dimensions"]), "task families"),
            (self.tasks["suite"]["seeds_per_scene"], "frozen seeds per scene"),
            (n_scenes * self.tasks["suite"]["seeds_per_scene"], "episodes per policy"),
            (n_pol, "policy checkpoints"), (n_ag, "LLM agent systems"),
        ]
        stats_html = "".join(f'<div class="stat"><div class="stat-n">{esc(n)}</div><div class="stat-l">{esc(l)}</div></div>' for n, l in stats)
        def thumbs(d):
            return "".join('<img src="%s" alt="%s" loading="lazy">' % (sc["thumbnail"], esc(sc["name"])) for sc in d["scenes"][:4])
        dims_html = "".join(
            f'<a class="card dim-card" href="sim-tasks/#{d["id"].lower()}"><div class="card-kicker">{esc(d["id"])} · {len(d["scenes"])} scenes</div>'
            f'<h3>{esc(d["name_en"])}</h3><p>{esc(d["desc_en"])}</p>'
            f'<div class="thumb-row">{thumbs(d)}</div></a>'
            for d in self.tasks["dimensions"])
        # An empty Code link means the repository is not public yet: render a disabled chip instead
        # of a link, which would otherwise resolve to this page.
        code_btn = ("Code", code_href, "") if code_href else ("Code · coming soon", None, "soon")
        paper_btn = ("Paper", paper_href, "") if paper_href else ("Paper · coming soon", None, "soon")
        buttons = [
            ("Evaluate your model", "participate/", "primary"), paper_btn, code_btn,
            ("Documentation", "usage/install-and-download/", ""), ("Leaderboard", "leaderboard/", ""), ("Tasks", "sim-tasks/", ""),
        ]
        btn_html = "".join(
            f'<span class="btn {c}" aria-disabled="true">{esc(l)}</span>' if h is None else
            f'<a class="btn {c}" href="{esc(h)}"' + (' target="_blank" rel="noopener"' if str(h).startswith('http') else '') + f'>{esc(l)}</a>'
            for l, h, c in buttons)
        content = f"""
<section class="home-hero">
  {f'<div class="kicker">{esc(site["version"])}</div>' if site.get("version") else ""}
  <h1 class="home-title">{esc(paper["title"])}</h1>
  <p class="home-tagline">{esc(site.get("tagline", ""))}</p>
  {author_block}
  <div class="btn-row">{btn_html}</div>
  {meta_block}
</section>
{self.participate_block(rel)}
{self.overview_figure()}
<section class="home-abstract">{abstract_html}</section>
<section class="home-stats">{stats_html}</section>
{self.source_map_figure()}
<section>
  <h2 id="axes">Six task families</h2>
  <p>Each evaluation scene is derived from RoboTwin 2.0 base tasks and records what changes: objects, spatial conditions, target selection, referring expressions, action sequences or a mixture. Families organise tasks by their dominant requirement; they overlap and do not isolate independent abilities. Scenes additionally carry descriptive levels L1–L3 (9 / 29 / 10 scenes).</p>
  {self.families_figure()}
  <div class="card-grid">{dims_html}</div>
</section>
{cite_block}
"""
        self.page("index.html", site["name"], content, body_class="home", description=site.get("description", ""))

    def participate_block(self, rel):
        """Submission entry point on the home page. The nav item alone does not tell a visitor that
        the leaderboard accepts new models and systems, or what it costs them to try."""
        steps = [
            ("1", "Run the development set",
             "Six scenes, five episodes each, on locally generated initial states. One command checks "
             "that your model drives the robot and that its logs export cleanly."),
            ("2", "File a request",
             "Model configuration, code revision, the exported result file and a runnable recipe. "
             "An API model is one JSON file: the agent framework, tools and controller stay fixed."),
            ("3", "Get an official result",
             "The organizers run the same evaluator on the organizer-held initial states and publish "
             "the score with the logs they produced."),
        ]
        cards = "".join(
            f'<div class="step"><div class="step-n">{esc(n)}</div>'
            f'<h3>{esc(title)}</h3><p>{esc(body)}</p></div>' for n, title, body in steps)
        return f"""<section class="home-participate">
  <h2 id="participate">Evaluate your model on ManipScope</h2>
  <p class="lead">The leaderboard is open to new models and new methods. Two tracks: a
  <strong>standard agent framework</strong> with a fixed prompt, two tools, controller and budgets,
  where only the base model changes — and an <strong>open system</strong> track for your own planner,
  tools, memory, skills and control policy.</p>
  <div class="step-row">{cards}</div>
  <div class="btn-row">
    <a class="btn primary" href="{rel}participate/">How to participate</a>
    <a class="btn" href="{rel}usage/evaluation-protocol/">Evaluation protocol</a>
  </div>
</section>"""

    def overview_figure(self):
        """Teaser figure. Source of truth is assets/img/manipscope-teaser.pdf (a copy of
        reference_doc/ManipScope_teaser_latest.pdf); assets/img/manipscope-teaser.jpg is its raster
        render for <img>. The image URL carries a content hash so CDN caches (GitHub Pages,
        anonymous.4open.science) cannot keep serving a stale render after the figure changes."""
        p = "assets/img/manipscope-teaser.jpg"
        if not os.path.exists(os.path.join(HERE, p)):
            return ""
        pdf = "assets/img/manipscope-teaser.pdf"
        img = f'<img src="{asset_url(p)}" alt="ManipScope teaser: diverse compositional scenes; 48 scenes across three levels and six task families; evaluation protocol with full policy evaluation and matched-subset agent comparison; open-source code, scene settings, protocol and leaderboards; unified evaluation interface for 17 VLA, WAM and agent systems; diagnostic findings" loading="lazy">'
        if os.path.exists(os.path.join(HERE, pdf)):
            img = f'<a href="{asset_url(pdf)}" target="_blank" rel="noopener" title="Open the vector PDF">{img}</a>'
        return (f'<figure class="home-figure">{img}'
                f'<figcaption>Overview. ManipScope evaluates 48 compositional scenes spanning three levels (L1 single changes, L2 additional distinctions, L3 combined constraints) and six task families (D1–D6). '
                f'Policies run 100 episodes per scene (4,800 per policy); agents run 5 episodes per scene and are compared on a matched subset of 240 episodes with shared initial conditions. '
                f'A unified interface exposes the same simulator action controller to VLA policies, world-action models and tool-using agents (17 systems). '
                f'Open resources include the source code, classified scene settings, the evaluation protocol and interface, and leaderboards with the diagnostic protocol. '
                f'Diagnostic findings: task success does not establish reliable instruction following; most failures displace a distractor, the selected object stays unchanged when the instruction changes, and systems can select the correct target yet fail the task, forecast and execute the wrong target consistently, and change actions under representation swaps without useful goal transfer.</figcaption></figure>')

    def families_figure(self):
        """Paper Figure 1 (concept illustration of the six families), if assets/img/families-overview.jpg exists."""
        p = "assets/img/families-overview.jpg"
        if not os.path.exists(os.path.join(HERE, p)):
            return ""
        return (f'<figure class="home-figure"><img src="{asset_url(p)}" alt="From RoboTwin base tasks to the six ManipScope task families: object transfer, spatial transfer, attribute selection, referring expressions, skill sequences, mixed requirements" loading="lazy">'
                f'<figcaption>From RoboTwin base tasks to ManipScope evaluation scenes: the six panels illustrate changes in objects, spatial conditions, target selection, referring expressions, action sequences and mixed requirements. '
                f'This is a concept illustration drawn from the scene sheets, not rollout screenshots; arrows indicate illustrative contrasts, not verified source-task dependencies (see the <a href="#source-map">link diagram</a> for those).</figcaption></figure>')

    def depgraph_iframe(self, view, title):
        """Inline the dependency graph via srcdoc with the embed view hard-wired. A src= iframe breaks
        on hosts that serve every page with X-Frame-Options/CSP sandbox (e.g. anonymous.4open.science):
        the sandboxed parent becomes an opaque origin and same-origin framing is refused. srcdoc needs
        no HTTP request, so those response headers never apply."""
        html_in = read(os.path.join(HERE, "assets", "depgraph", "index.html"))
        needle = 'var view = (new URLSearchParams(location.search).get("view") || "").toLowerCase();'
        if needle not in html_in:
            raise SystemExit("assets/depgraph/index.html: embed-view line not found; cannot inline the graph")
        html_in = html_in.replace(needle, f'var view = "{view}";')
        srcdoc = html_in.replace("&", "&amp;").replace('"', "&quot;")
        return f'<iframe class="depgraph" srcdoc="{srcdoc}" title="{esc(title)}" loading="lazy" scrolling="no"></iframe>'

    def source_map_figure(self):
        """Figure relating evaluation scenes to their RoboTwin source tasks. Preferred source is the
        interactive dependency graph at assets/depgraph/index.html (inlined via srcdoc); otherwise a
        static image assets/img/source-task-map.{png,svg,jpg}; otherwise a placeholder box."""
        graph = "assets/depgraph/index.html"
        if os.path.exists(os.path.join(HERE, graph)):
            g = self.depgraph or {}
            n_edges, n_used, n_base = g.get("n_edges"), g.get("n_used"), g.get("n_base")
            stats = f' The 48 scenes draw on {n_used} of the {n_base} RoboTwin base tasks through {n_edges} source links.' if n_edges else ""
            return (f'<section><h2 id="source-map">From RoboTwin base tasks to evaluation scenes</h2>'
                    f'<p>Every evaluation scene recombines objects, skills or success criteria from one or more RoboTwin 2.0 base tasks; '
                    f'training data is the unchanged RoboTwin 2.0 demonstration set and ManipScope adds evaluation scenes only.{stats} '
                    f'Evaluation scenes are on the left, grouped by family; base tasks are on the right. Hover a name on either side to highlight its links; base tasks in orange are not used by any scene.</p>'
                    f'<figure class="home-figure home-graph">{self.depgraph_iframe("arc", "Link diagram: RoboTwin 2.0 base tasks used by the 48 ManipScope evaluation scenes")}'
                    f'<figcaption>Source links of the 48 formal scenes. The <a href="sim-tasks/#coverage">scene × base-task matrix and coverage statistics</a> are on the Simulation Tasks page; '
                    f'<a href="{graph}" target="_blank" rel="noopener">open the full graph in a new tab</a>.</figcaption></figure></section>')
        for ext in ("svg", "png", "jpg", "webp"):
            p = f"assets/img/source-task-map.{ext}"
            if os.path.exists(os.path.join(HERE, p)):
                return (f'<section><h2 id="source-map">From RoboTwin base tasks to evaluation scenes</h2>'
                        f'<figure class="home-figure"><img src="{p}" alt="Mapping from RoboTwin 2.0 source tasks to the ManipScope evaluation scenes" loading="lazy">'
                        f'<figcaption>Each evaluation scene is linked to the RoboTwin 2.0 base tasks that supply its skills, objects or relations. Training data is the unchanged RoboTwin 2.0 demonstration set; ManipScope adds only evaluation scenes.</figcaption></figure></section>')
        return ('<section><h2 id="source-map">From RoboTwin base tasks to evaluation scenes</h2>'
                '<div class="figure-placeholder">Source-task relationship figure — coming soon<br>'
                '<small>expected at <code>assets/img/source-task-map.png</code> (or .svg)</small></div>'
                '<p class="muted small">Training data is the unchanged RoboTwin 2.0 demonstration set. ManipScope adds evaluation scenes only; each scene page lists the source tasks it derives from.</p></section>')

    # ---- tasks ------------------------------------------------------------------
    def build_tasks_index(self):
        out_path = "sim-tasks/index.html"
        rel = rel_prefix(out_path)
        intro_meta, intro_body = ({}, "")
        p = os.path.join(CONTENT, "sim-tasks", "index.md")
        if os.path.exists(p):
            intro_meta, intro_body = front_matter(read(p))
        intro_html, intro_toks = md_render(intro_body.replace("{{rel}}", rel))
        suite = self.tasks["suite"]
        rows = "".join(
            f'<tr><td><a href="#{d["id"].lower()}">{esc(d["id"])}</a></td><td>{esc(d["name_en"])}</td><td>{len(d["scenes"])}</td><td>{esc(d["desc_en"])}</td></tr>'
            for d in self.tasks["dimensions"])
        groups = []
        toks = list(intro_toks)
        for d in self.tasks["dimensions"]:
            cards = "".join(
                f'<a class="task-card" href="{rel}sim-tasks/{sc["name"]}/">'
                f'<img src="{rel}{sc["thumbnail"]}" alt="{esc(sc["name"])}" loading="lazy">'
                f'<div class="task-card-body"><div class="task-card-title">{esc(sc["title"])}</div>'
                f'<div class="badges"><span class="badge tier-{sc["tier"].lower()}">{esc(sc["tier"])}</span>'
                + (f'<span class="badge">{esc(sc["criterion"])}</span>' if sc["criterion"] != sc["source"] else "")
                + f'<span class="badge muted">{esc(sc["source"])}</span></div>'
                f'<code class="task-code">{esc(sc["name"])}</code></div></a>'
                for sc in d["scenes"])
            groups.append(f'<h3 id="{d["id"].lower()}">{esc(d["id"])} · {esc(d["name_en"])} <span class="count">{len(d["scenes"])}</span></h3>'
                          f'<p class="dim-desc">{esc(d["desc_en"])}</p><div class="task-grid">{cards}</div>')
            toks.append({"id": d["id"].lower(), "name": f'{d["id"]} · {d["short_en"]}', "children": []})
        tier_counts = {}
        for d in self.tasks["dimensions"]:
            for sc in d["scenes"]:
                tier_counts[sc["tier"]] = tier_counts.get(sc["tier"], 0) + 1
        tiers = "".join(f'<tr><td><span class="badge tier-{k.lower()}">{esc(k)}</span></td><td class="num">{tier_counts.get(k, 0)}</td><td>{esc(v["en"])}</td></tr>' for k, v in self.tasks["tiers"].items())
        excl = self.tasks.get("excluded") or {}
        excl_html = ""
        if excl.get("scenes"):
            meas = "".join(f'<li><code>{esc(k)}</code>: expert yield {esc(str(v).split("~")[0].strip())} (≈{esc(str(v).split("~")[-1].strip())})</li>' for k, v in (excl.get("measured") or {}).items())
            excl_html = f'<h2 id="excluded">Excluded candidates</h2><p>{esc(excl.get("reason", ""))}</p><ul>{meas}</ul><p class="muted">{esc(excl.get("status", ""))}</p>'
            toks.append({"id": "excluded", "name": "Excluded candidates", "children": []})
        coverage_html = self.coverage_html(rel)
        content = f"""
<h1>Simulation Tasks</h1>
<p class="lead">{esc(suite["formal_scenes"])} frozen scenes · {esc(suite["seeds_per_scene"])} seeds per scene · default {esc(suite["episodes_default"])} episodes, <code>{esc(suite["task_config"])}</code>, {esc(suite["instruction_type"])} instructions.</p>
<figure class="home-figure">
  <img src="{rel}assets/img/formal48-overview.png" alt="Scene overview of the 48 evaluation tasks: one tile per scene with its task identifier and level" loading="lazy">
  <figcaption>Scene overview of the 48 evaluation tasks (paper Figure 5). Each tile shows an example scene and its task identifier; L1–L3 denote the assigned levels. The overview retains an earlier working title and labels the mixture family D7; this is D6 in the paper, not an additional family.</figcaption>
</figure>
{intro_html}
<h2 id="groups">Task families</h2>
<table><thead><tr><th>Family</th><th>Name</th><th>Tasks</th><th>Focus</th></tr></thead><tbody>{rows}</tbody></table>
<h2 id="tiers">Levels</h2>
<p class="muted small">Levels are manual design annotations, not a calibrated difficulty scale (L1: 9 scenes with a single replacement, few distractors, one action segment; L2: 29 with an additional distinction or a two-action task; L3: 10 with combined constraints or dependent actions). Changes in object geometry and execution demands can also affect performance.</p>
<table><thead><tr><th>Level</th><th>Scenes</th><th>Registry definition</th></tr></thead><tbody>{tiers}</tbody></table>
{coverage_html}
<h2 id="catalog">Task catalogue</h2>
{"".join(groups)}
{excl_html}
"""
        toks_final = [{"id": "groups", "name": "Task families", "children": []}, {"id": "tiers", "name": "Levels", "children": []}]
        if coverage_html:
            toks_final.append({"id": "coverage", "name": "Source-task coverage", "children": []})
        toks_final.append({"id": "catalog", "name": "Task catalogue", "children": [t for t in toks if t["id"].startswith("d")]})
        toks_final = intro_toks + toks_final + [t for t in toks if t["id"] == "excluded"]
        self.page(out_path, "Simulation Tasks", content, toc_html(toks_final), description="Catalogue of the 48 ManipScope formal scenes.")

    def coverage_html(self, rel):
        """Simulation Tasks page: which RoboTwin base tasks the 48 scenes draw on (matrix embed from
        assets/depgraph plus static reuse / gap lists derived from the same data)."""
        g = self.depgraph
        if not g:
            return ""
        graph = f"{rel}assets/depgraph/index.html"
        n_scenes = len(g["scenes"])
        mean = g["n_edges"] / n_scenes if n_scenes else 0
        stats = [(n_scenes, "evaluation scenes"), (g["n_edges"], "source links"),
                 (f'{g["n_used"]} / {g["n_base"]}', "base tasks used"), (len(g["unused"]), "base tasks not used"), (f"{mean:.2f}", "sources per scene")]
        stats_html = "".join(f'<div class="stat"><div class="stat-n">{esc(n)}</div><div class="stat-l">{esc(l)}</div></div>' for n, l in stats)
        top = g["top"][:10]
        mx = g["use"][top[0]] if top else 1
        doc = lambda b: f'<a href="https://robotwin-platform.github.io/doc/tasks/{esc(b)}.html" target="_blank" rel="noopener"><code>{esc(b)}</code></a>'
        reuse = "".join(
            f'<tr><td>{doc(b)}</td><td class="bar-cell"><span class="bar" style="width:{100 * g["use"][b] / mx:.0f}%"></span></td><td class="num">{g["use"][b]}</td></tr>'
            for b in top)
        unused = "".join(f"<li>{doc(b)}</li>" for b in g["unused"])
        return f"""
<h2 id="coverage">Source-task coverage</h2>
<p>Each scene recombines objects, skills or success criteria from one or more of the {g["n_base"]} RoboTwin 2.0 base tasks (listed as "Source skills" on every scene page). The matrix below shows the {n_scenes} scenes as rows in family order and the base tasks as columns; a filled cell is a source link. Hover a row to see its instruction, level, expert seed yield and the task success of the twelve policies; click to pin it. Struck-through columns are base tasks no formal scene uses. The number at the end of each row is the DM0.5 task-success rate on that scene.</p>
<div class="home-stats coverage-stats">{stats_html}</div>
<figure class="home-figure home-graph">{self.depgraph_iframe("matrix", "Dependency matrix: 48 ManipScope scenes against 50 RoboTwin 2.0 base tasks")}
<figcaption>Rows: evaluation scenes; columns: RoboTwin 2.0 base tasks. The <a href="{rel}#source-map">link diagram</a> of the same data is on the home page; <a href="{graph}" target="_blank" rel="noopener">open the full graph in a new tab</a>.</figcaption></figure>
<div class="two-col">
<div><h4>Most reused base tasks</h4>
<table class="reuse"><thead><tr><th>Base task</th><th></th><th>Scenes</th></tr></thead><tbody>{reuse}</tbody></table>
<p class="muted small">Heavy reuse of <code>place_a2b_left</code> / <code>place_a2b_right</code> is expected: the skill–spatial family (D2) is built around the "put A on one side of B" relation these two native tasks define.</p></div>
<div><h4>Base tasks not used by any scene ({len(g["unused"])})</h4>
<ul class="cols">{unused}</ul>
<p class="muted small">Current coverage gaps of the formal list. Most fall into bimanual coordination (<code>pick_dual_bottles</code>, <code>place_dual_shoes</code>), articulated-object manipulation (<code>open_microwave</code>, <code>turn_switch</code>) and dynamic motions (the two <code>shake_bottle</code> tasks), the groups for which stable scripted experts are hardest to obtain.</p></div>
</div>
<p class="muted small">Source links are a design notion, not code-level inheritance: every scene is implemented independently, but its objects, skills and criteria trace back to these native tasks. Links come from the <code>deps</code> field of each scene in <code>suite/table.py</code> and, for the hand-written scenes, from their lineage in <code>suite/scenes.py</code>; exported by <code>suite/gen_depgraph.py</code>.</p>
"""

    def build_task_pages(self):
        for name, (d, sc) in self.scene_index.items():
            out_path = f"sim-tasks/{name}/index.html"
            rel = rel_prefix(out_path)
            self.page(out_path, sc["title"], self.task_html(d, sc, rel), self.task_toc(sc),
                      description=sc.get("description_en", ""), body_class="task")

    def video_block(self, label, src, poster, rel, note):
        exists = os.path.exists(os.path.join(HERE, src))
        if exists:
            inner = f'<video controls muted loop playsinline preload="metadata" poster="{rel}{poster}"><source src="{rel}{src}" type="video/mp4">Your browser does not support the video tag.</video>'
        else:
            inner = f'<div class="video-placeholder"><img src="{rel}{poster}" alt=""><div class="video-missing">Video coming soon<br><small>expected at <code>{esc(src)}</code></small></div></div>'
        return f'<figure class="video-card">{inner}<figcaption><strong>{esc(label)}</strong><span>{esc(note)}</span></figcaption></figure>'

    def rollout_html(self, sc, rel):
        """One processed successful rollout per scene (G0.5, or the GPT-6 fallback where G0.5 produced
        no success in the re-rendered candidates). Falls back to a placeholder when absent."""
        v = self.videos.get(sc["name"])
        if not v or not os.path.exists(os.path.join(HERE, v["file"])):
            return f'<div class="video-row">{self.video_block("Successful rollout", sc["video"]["success"], sc["thumbnail"], rel, "head camera, frozen seed, task success = 1")}</div>'
        wide = " wide" if v.get("decisions") else ""
        poster = v.get("poster") if v.get("poster") and os.path.exists(os.path.join(HERE, v["poster"])) else sc["thumbnail"]
        video = (f'<video controls muted loop playsinline preload="metadata" poster="{rel}{poster}">'
                 f'<source src="{rel}{v["file"]}" type="video/mp4">Your browser does not support the video tag.</video>')
        seedtxt = "a frozen initial state"
        cap = (f'<figcaption><strong>Successful rollout · {esc(v["system"])} ({esc(v["kind"])})</strong>'
               f'<span>Re-rendered presentation camera, {seedtxt}, actual outcome: task success = 1. Played at ×{v["speed"]} '
               f'(simulation time {v["source_seconds"]:.1f} s → {v["output_seconds"]:.1f} s; model and API waiting time excluded).'
               + (' The right-hand panel lists every tool call with the note the agent attached to it; the highlighted entry follows the recorded step counter.' if v.get("decisions") else "")
               + '</span></figcaption>')
        html_out = f'<div class="video-row single"><figure class="video-card{wide}">{video}{cap}</figure></div>'
        if v.get("decisions"):
            rows = []
            for c in v["decisions"]:
                what = esc(c["type"])
                if c["type"] == "move_eef":
                    what += f' · {esc(c["phase"])} · {esc(c["arm"])} arm' + (f' · gripper {c["gripper"]:g}' if c.get("gripper") is not None else "")
                step = "—" if c.get("step_after") is None else esc(c["step_after"])
                rows.append(f'<tr><td class="num">{c["call"]}</td><td>{what}</td><td class="num">{step}</td><td>{esc(c["note"])}</td></tr>')
            html_out += (f'<details class="goal decisions"><summary>Agent tool calls for this episode ({len(v["decisions"])})</summary>'
                         f'<p class="muted small">Each row is one API call of the agent: the tool it invoked, the recorded step counter after execution, and the free-text note it attached. '
                         f'The note is the only model-written text that is stored; the model\'s internal reasoning is not recorded.</p>'
                         f'<table class="decisions"><thead><tr><th>#</th><th>Action</th><th>Step after</th><th>Note</th></tr></thead><tbody>{"".join(rows)}</tbody></table></details>')
        return html_out

    def task_html(self, d, sc, rel):
        suite = self.tasks["suite"]
        instr = sc["instructions"]
        placeholders = 'Placeholders: <code>{A}</code> = target description' + (f' (here <em>{esc(sc["a_desc"])}</em>)' if sc.get("a_desc") else "") + ', <code>{a}</code> = arm.'
        seen = "".join(f"<li><code>{esc(s)}</code></li>" for s in instr["seen"]) or "<li class='muted'>—</li>"
        unseen = "".join(f"<li><code>{esc(s)}</code></li>" for s in instr["unseen"]) or "<li class='muted'>—</li>"
        example = (instr["unseen"] or instr["seen"] or ["—"])[0]
        if sc.get("a_desc"):
            example = example.replace("{A}", sc["a_desc"]).replace("{a}", "the left arm")
        baseline = ", ".join(f'<a href="https://robotwin-platform.github.io/doc/tasks/{esc(b)}.html" target="_blank" rel="noopener"><code>{esc(b)}</code></a>' for b in sc["baseline"]) or "—"
        seeds = sc["seeds"]
        seed_txt = f'{esc(seeds.get("count"))} frozen initial states (seed lists held by the organizers)'
        neighbours = d["scenes"]
        idx = [s["name"] for s in neighbours].index(sc["name"])
        prev_ = neighbours[idx - 1] if idx > 0 else None
        next_ = neighbours[idx + 1] if idx + 1 < len(neighbours) else None
        nav = '<nav class="pager">' + (f'<a class="prev" href="{rel}sim-tasks/{prev_["name"]}/">← {esc(prev_["title"])}</a>' if prev_ else "<span></span>") + \
              (f'<a class="next" href="{rel}sim-tasks/{next_["name"]}/">{esc(next_["title"])} →</a>' if next_ else "<span></span>") + "</nav>"

        objects_html = ""
        if sc["objects"]:
            rows = "".join(
                f'<tr><td><span class="badge kind-{o["kind"]}">{esc(o["kind"])}</span></td><td><code>{esc(o["role"])}</code></td>'
                f'<td>{esc(o["desc"] or "")}</td><td><code>{esc(o["model"] or "")}</code>{(" ids " + esc(o["ids"])) if o.get("ids") else ""}</td>'
                f'<td>{"static" if o["static"] else ("on <code>" + esc(o["rel"]) + "</code>" if o.get("rel") else "free")}</td></tr>'
                for o in sc["objects"])
            objects_html = f'<h2 id="objects">Scene objects</h2><table class="objects"><thead><tr><th>Kind</th><th>Role</th><th>Description</th><th>Asset</th><th>Placement</th></tr></thead><tbody>{rows}</tbody></table>' \
                           f'<p class="muted">Kinds: <em>target</em> must be manipulated; <em>reference</em> objects define the goal or anchor placement; <em>distractor</em> objects must move strictly less than the target.</p>'

        goal_html = ""
        if sc.get("goal"):
            flags = []
            if sc.get("mirror"):
                flags.append("MIRROR on: each episode is left-right mirrored with 50 % probability so the target is not always on one side.")
            if sc.get("exclusive") is False:
                flags.append("EXCLUSIVE off: distractor displacement is not compared.")
            goal_html = f'<details class="goal"><summary>Declared goal (from <code>envs/{esc(sc["name"])}.py</code>)</summary><pre><code>GOAL = {esc(json.dumps(sc["goal"], ensure_ascii=False))}</code></pre>' + \
                        ("".join(f"<p>{esc(f)}</p>" for f in flags)) + "</details>"

        scoring = "".join(f'<tr><td class="score">{esc(r["score"])}</td><td>{md_inline(r["cond"])}</td></tr>' for r in sc["scoring"])
        env_doc = ""      # original environment docstrings are Chinese; not rendered
        note_zh = ""

        # media: the processed successful rollout (data/videos.json, produced by scripts/process_videos.py)
        media_html = self.rollout_html(sc, rel)

        hist = ""
        if self.leaderboard and sc["name"] in self.leaderboard["per_scene"]:
            per = self.leaderboard["per_scene"][sc["name"]]

            def result_rows(names):
                out = []
                for p_name in names:
                    r = per.get(p_name)
                    if not r:
                        continue
                    n = self.leaderboard["episodes"].get(p_name, 4800 if p_name == "DM0.5" else None)
                    ci = f' <small>[{100 * r["ci"][0]:.1f}, {100 * r["ci"][1]:.1f}]</small>' if r.get("ci") else ""
                    out.append(f'<tr><td>{esc(p_name)}</td><td class="num">{100 * r["rate"]:.0f} %{ci}</td><td class="num">{esc(n // 48 if n else "?")}</td></tr>')
                return "".join(out)
            pol_rows = result_rows(self.leaderboard["learned"])
            ag_rows = result_rows(self.leaderboard["agents"])
            ag_html = ""
            if ag_rows:
                ag_html = f'<h4>Agents (first 5 seeds)</h4><table class="results"><thead><tr><th>System</th><th>Task success <small>[Wilson 95 % CI]</small></th><th>Episodes</th></tr></thead><tbody>{ag_rows}</tbody></table>'
            hist = f'''<h2 id="results">Results</h2>
<p class="muted small">Paper snapshot <code>{esc(self.leaderboard.get("snapshot", ""))}</code>; same frozen seeds for every system. Per-scene 95 % Wilson intervals. See the <a href="{rel}leaderboard/">leaderboard</a> for aggregates.</p>
<h4>Policies (100 episodes)</h4><table class="results"><thead><tr><th>Policy</th><th>Task success <small>[Wilson 95 % CI]</small></th><th>Episodes</th></tr></thead><tbody>{pol_rows}</tbody></table>
{ag_html}'''
        delivery = f'<div class="callout warn"><strong>Instruction delivery.</strong> {esc(sc["delivery_note"])}</div>' if sc.get("delivery_note") else ""
        if sc["name"] in DIAGNOSTIC_SCENES and os.path.exists(os.path.join(CONTENT, "diagnostics.md")):
            delivery += (f'<div class="callout"><strong>Controlled diagnostic study.</strong> {esc(DIAGNOSTIC_SCENES[sc["name"]])} '
                         f'See <a href="{rel}diagnostics/">Language-Following Diagnostics</a>. Those trials use their own seeds and budgets and are not part of the results below.</div>')
        if sc["name"] in ATTRIBUTE_STUDY_SCENES and os.path.exists(os.path.join(CONTENT, "diagnostics.md")):
            delivery += (f'<div class="callout"><strong>Attribute-selection study.</strong> This task is one of the nine attribute tasks measured with five fixed trials per system '
                         f'(five policies and two agents, 315 episodes in total): selection is scored at the first loaded interaction of at least 0.1 N. '
                         f'See the <a href="{rel}diagnostics/#attribute-selection-and-completion-on-the-formal-tasks">attribute study</a> on the Diagnostics page.</div>')

        return f"""
<div class="task-head">
  <div class="crumbs"><a href="{rel}sim-tasks/">Simulation Tasks</a> / <a href="{rel}sim-tasks/#{d["id"].lower()}">{esc(d["id"])} {esc(d["short_en"])}</a></div>
  <h1>{esc(sc["title"])} <code class="task-code">{esc(sc["name"])}</code></h1>
  <div class="badges">
    <span class="badge dim">{esc(d["id"])} · {esc(d["name_en"])}</span>
    <span class="badge tier-{sc["tier"].lower()}">{esc(sc["tier"])}</span>
    <span class="badge">criterion: {esc(sc["criterion"])}</span>
    <span class="badge muted">{esc(sc["source"])}</span>
    <span class="badge muted">{esc(sc["context_en"])}</span>
  </div>
</div>
<h2 id="media" class="visually-hidden">Media</h2>
{media_html}
<table class="info">
<tbody>
<tr><th>Instruction</th><td><em>{esc(example)}</em><div class="muted small">{placeholders}</div></td></tr>
<tr><th>Description</th><td>{esc(sc.get("description_en") or "")}</td></tr>
<tr><th>Platform</th><td>Simulation · RoboTwin 2.0 on SAPIEN 3 · embodiment <code>aloha-agilex</code> (dual-arm)</td></tr>
<tr><th>Task family</th><td>{esc(d["id"])} — {esc(d["name_en"])}</td></tr>
<tr><th>Level</th><td><span class="badge tier-{sc["tier"].lower()}">{esc(sc["tier"])}</span> {esc(sc["tier_desc_en"])} <span class="muted small">Levels are manual design annotations, not a calibrated difficulty scale (9 / 29 / 10 scenes).</span></td></tr>
<tr><th>Scene context</th><td>{esc(sc["context_en"])}</td></tr>
<tr><th>Source skills</th><td>{baseline}<div class="muted small">RoboTwin 2.0 training tasks that this scene recombines. Policies are expected to have trained on these, never on this scene.</div></td></tr>
<tr><th>Scene source</th><td>{esc(sc["source"])} {"(declarative <code>CompoScene</code>, generated by <code>suite/table.py</code>)" if sc["source"] == "generated" else "(hand-written environment with task-specific success check)"}</td></tr>
<tr><th>Success criterion</th><td>{esc(sc.get("criterion_en") or sc["criterion"])}</td></tr>
<tr><th>Step limit</th><td>{esc(sc.get("step_limit"))} <code>take_action</code> calls</td></tr>
<tr><th>Episodes</th><td>{seed_txt}. The paper snapshot evaluates all 100 per scene for policies and the first 5 for agents; the runner default is {esc(suite["episodes_default"])}. Seeds are consumed in file order and determine the sampled instruction.</td></tr>
<tr><th>Observations</th><td>head + left-wrist + right-wrist RGB (320×240), joint positions, end-effector pose. No depth, no privileged state.</td></tr>
<tr><th>Training data</th><td>Unchanged RoboTwin 2.0 demonstrations of the source tasks. ManipScope distributes no demonstrations for this scene; scripted experts were used only to screen seeds for feasibility.</td></tr>
<tr><th>Usage</th><td>Evaluation only.</td></tr>
</tbody>
</table>
{note_zh}
<h2 id="instructions">Instruction templates</h2>
<p>{placeholders} Instruction type <code>{esc(suite["instruction_type"])}</code> is used for formal evaluation.</p>
<div class="two-col"><div><h4>Seen ({len(instr["seen"])})</h4><ul class="instr">{seen}</ul></div><div><h4>Unseen ({len(instr["unseen"])})</h4><ul class="instr">{unseen}</ul></div></div>
{objects_html}
<h2 id="scoring">Scoring</h2>
<p>Task success is the primary measurement and is binary per episode: <em>y<sub>i</sub> = q<sub>i</sub>·g<sub>i</sub></em>, where <em>q<sub>i</sub></em> marks correct target selection and <em>g<sub>i</sub></em> physical goal completion{"; sequences additionally require all stages in order" if sc["criterion"] == "seq" else ""}. {"Selection is currently scored from the largest target displacement (the instructed object must move strictly more than every distractor); the goal is the declared end state below." if sc["source"] == "generated" else "This hand-written scene implements its own <code>check_success</code> following the same selection × goal principle."} Timeouts and inaction count as failures. Per-attribute correctness, exact-target event labels and stage-completion labels are planned measurements not yet exported.</p>
<table class="scoring"><thead><tr><th>Score</th><th>Condition</th></tr></thead><tbody>{scoring}</tbody></table>
{goal_html}
{env_doc}
{delivery}
{hist}
<h2 id="run">Run this scene</h2>
<pre><code>DRY_RUN=1 bash suite/run_suite.sh dm05 {esc(sc["name"])}          # validate inputs only
EPISODES=50 RUN_NAME=my_run bash suite/run_suite.sh dm05 {esc(sc["name"])}
# results: eval_result/my_run/{esc(sc["name"])}/DM05/{esc(suite["task_config"])}/dm05/&lt;timestamp&gt;/</code></pre>
{nav}
"""

    def task_toc(self, sc):
        toks = [{"id": "instructions", "name": "Instruction templates", "children": []}]
        if sc["objects"]:
            toks.append({"id": "objects", "name": "Scene objects", "children": []})
        toks.append({"id": "scoring", "name": "Scoring", "children": []})
        if self.leaderboard and sc["name"] in self.leaderboard["per_scene"]:
            toks.append({"id": "results", "name": "Results", "children": []})
        toks.append({"id": "run", "name": "Run this scene", "children": []})
        return toc_html(toks)

    # ---- policies ---------------------------------------------------------------
    def build_policies(self):
        out_path = "policies/index.html"
        rel = rel_prefix(out_path)
        p = os.path.join(CONTENT, "policies.md")
        intro_html, intro_toks = ("", [])
        if os.path.exists(p):
            _, body = front_matter(read(p))
            intro_html, intro_toks = md_render(body.replace("{{rel}}", rel))
        cards = []
        for pol in self.policies["policies"]:
            env = "".join(f"<code>{esc(e)}</code> " for e in pol.get("required_env", []))
            links = []
            if pol.get("code_repo"):
                links.append(f'<a href="{esc(pol["code_repo"])}" target="_blank" rel="noopener">code</a>')
            if pol.get("hf_repo") and str(pol["hf_repo"]).startswith("http"):
                note = f' title="{esc(pol["hf_note_en"])}"' if pol.get("hf_note_en") else ""
                links.append(f'<a href="{esc(str(pol["hf_repo"]).split(" ")[0])}" target="_blank" rel="noopener"{note}>weights</a>')
            iface = pol.get("interface") or {}
            iface_html = (f'<span class="badge {"dim" if iface.get("control", "").startswith("Joint") else ""}">{esc(iface.get("control", "?"))}</span>'
                          f'<div class="small muted">state: {esc(iface.get("state", "—"))}<br>action: {esc(iface.get("action", "—"))}</div>')
            cards.append(f'''<tr id="{esc(pol["key"])}">
<td><strong>{esc(pol["key"])}</strong></td>
<td>{esc(pol.get("desc_en") or "")}</td>
<td>{iface_html}</td>
<td>{" · ".join(links) or "—"}</td>
<td><code>{esc(pol.get("server", ""))}</code> :{esc(pol.get("port", ""))}<br><code>{esc(pol.get("launch") or "external")}</code><div class="small">{env}</div></td>
</tr>''')
        planned_en = {"eventvla": ("EventVLA (InternRobotics): event-driven keyframe evidence-memory VLA; RoboTwin-MeM weights.", "integration in progress")}
        planned = "".join(f'<tr><td><strong>{esc(p["key"])}</strong></td><td>{esc(planned_en.get(p["key"], ("", ""))[0])}</td><td>{esc(planned_en.get(p["key"], ("", "planned"))[1])}</td></tr>' for p in self.policies["planned"])
        n_paper = sum(1 for p in self.policies["policies"] if p.get("in_paper"))
        content = f"""
<h1>Policies</h1>
<p class="lead">{len(self.policies["policies"])} systems are registered in <code>suite/policies.yaml</code> and adapted under <code>policy/&lt;Plugin&gt;/deploy_policy.py</code>; {n_paper} checkpoints have full-run results in the paper snapshot. Each runs in its own Python environment behind a loopback HTTP/socket service; the simulator never imports model code.</p>
{intro_html}
<h2 id="integrated">Integrated policies</h2>
<p class="muted small">Control interface as reported in the paper (Table 7): a 14-D joint vector is six arm joints plus one gripper value per side; a 16-D EEF vector is [xyz, quaternion, grip] × 2 and a 20-D EEF vector [xyz, rot6D, grip] × 2. EEF policies go through RoboTwin's <code>take_action(ee)</code> and cuRobo planning. Dimensions are per time step, before model-specific preprocessing. Weight and code revisions of the evaluated checkpoints remain to be pinned.</p>
<table class="policies"><thead><tr><th>Key</th><th>Model</th><th>Control interface</th><th>Links</th><th>Service / env vars</th></tr></thead><tbody>{"".join(cards)}</tbody></table>
{self.audit_html()}
<h2 id="planned">Planned</h2>
<table><thead><tr><th>Key</th><th>Model</th><th>Status</th></tr></thead><tbody>{planned or '<tr><td colspan="3">—</td></tr>'}</tbody></table>
"""
        toks = intro_toks + [{"id": "integrated", "name": "Integrated policies", "children": []}]
        if self.audit:
            toks.append({"id": "provenance", "name": "Training provenance and inference modules", "children": [
                {"id": "provenance-table", "name": "Per-checkpoint records", "children": []}, {"id": "audit-findings", "name": "What the audit changes", "children": []}]})
        toks.append({"id": "planned", "name": "Planned", "children": []})
        self.page(out_path, "Policies", content, toc_html(toks), description="Policies integrated with the ManipScope evaluator.")

    def audit_html(self):
        """Policies page: training provenance and enabled inference modules per checkpoint
        (paper Appendix B.2 / Table 8 and the Table 1 provenance markers), from data/policy_audit.json."""
        a = self.audit
        if not a:
            return ""
        legend = a.get("provenance_legend", {})
        order = self.leaderboard["learned"] if self.leaderboard else list(a["policies"].keys())
        rows = []
        for name in order:
            r = a["policies"].get(name)
            if not r:
                continue
            mark, scope = r.get("provenance", ""), r.get("scope", "")
            scope_sup = f'<sup class="prov" title="{esc(a.get("scope_legend", {}).get(scope, ""))}">{esc(scope)}</sup>' if scope else ""
            rows.append(f'<tr><td class="pol"><strong>{esc(name)}</strong><sup class="prov" title="{esc(legend.get(mark, ""))}">{esc(mark)}</sup>{scope_sup}</td>'
                        f'<td>{esc(r.get("backbone", ""))}</td><td>{esc(r.get("robot_pretraining", ""))}</td><td>{esc(r.get("robotwin_quota", ""))}</td>'
                        f'<td>{esc(r.get("action_generation", ""))}</td><td class="num">{esc(r.get("predict", ""))} / {esc(r.get("execute", ""))}</td><td>{esc(r.get("inference_path", ""))}</td></tr>')
        agents = a.get("agents", {})
        arows = "".join(f'<tr><td class="pol"><strong>{esc(n)}</strong></td><td colspan="3">{esc(v.get("backbone", ""))}</td><td>{esc(v.get("action_generation", ""))}</td>'
                        f'<td class="num">1 call / ≥ 1 step</td><td>{esc(v.get("inference_path", ""))}</td></tr>' for n, v in agents.items())
        legend_html = " ".join(f'<sup class="prov">{esc(k)}</sup> {esc(v)}' for k, v in legend.items())
        findings = "".join(f"<li>{esc(f)}</li>" for f in a.get("findings", []))
        return f"""
<h2 id="provenance">Training provenance and enabled inference modules</h2>
<p>Method names do not describe what ran. The configuration audit of {esc(a.get("audit_date", ""))} (paper Appendix B.2, Table 8) combined checkpoint files, adapter call paths, model cards and the available historical launch logs to record, for each checkpoint, three separate components of training provenance and the inference modules that were actually enabled. Launch-log evidence does not establish identical settings for every accepted episode, and public training recipes are source-reported, not reproduced here.</p>
<p class="muted small"><strong>Training provenance</strong> has three layers: the vision/language/video <em>backbone</em>; any subsequent <em>robot or latent-action pretraining</em>; and the <em>RoboTwin adaptation</em> quota. The marker after each name follows paper Table 1: {legend_html} A backbone's own priors are not robot-action pretraining, and an unknown quota is recorded as unknown rather than zero.</p>
<h3 id="provenance-table">Per-checkpoint records</h3>
<div class="table-scroll"><table class="policies audit"><thead><tr><th>System</th><th>Backbone</th><th>Robot / latent-action pretraining</th><th>RoboTwin adaptation</th><th>Action generation</th><th>Predict / execute<br><small>(action targets per request)</small></th><th>Inference path and context</th></tr></thead>
<tbody><tr class="group"><td colspan="7">Policies</td></tr>{"".join(rows)}<tr class="group"><td colspan="7">Agents</td></tr>{arows}</tbody></table></div>
<p class="muted small">Prediction / execution lengths count action targets per request, not measured control frequency; an EEF call additionally contains a planned trajectory, so step counters are not comparable across control interfaces. Observation history also differs: WLA consumes eight historical head images, AHA-WAM and LingBot-VA keep cross-chunk context, agents keep text and tool history within an episode, while the other adapters send the current observation only.</p>
<h3 id="audit-findings">What the audit changes in how results should be read</h3>
<ul>{findings}</ul>
<p class="muted small">Consequently the leaderboard compares released checkpoints under their recorded system configurations. Grouped readings (joint- vs. EEF-controlled systems, confirmed robot-pretrained vs. target-domain-only training) are descriptive; with parameters, data, controllers and observations unmatched, no result here is an architecture ablation or a discrete- vs. continuous-action comparison.</p>
"""

    # ---- leaderboard -------------------------------------------------------------
    def build_leaderboard(self):
        out_path = "leaderboard/index.html"
        rel = rel_prefix(out_path)
        p = os.path.join(CONTENT, "leaderboard.md")
        intro_html, intro_toks = ("", [])
        if os.path.exists(p):
            _, body = front_matter(read(p))
            intro_html, intro_toks = md_render(body.replace("{{rel}}", rel))
        lb = self.leaderboard
        if not lb:
            content = f"<h1>Leaderboard</h1>{intro_html}<p>No results data found. Run <code>scripts/sync_from_maniscope.py</code>.</p>"
            self.page(out_path, "Leaderboard", content, toc_html(intro_toks))
            return
        dims = self.tasks["dimensions"]
        tiers = ["L1", "L2", "L3"]
        agg = lb["agg"]
        audit_pol = (self.audit or {}).get("policies", {})
        prov_legend = (self.audit or {}).get("provenance_legend", {})

        def pct(v):
            """Percent with two decimals, rounded half-up on the exact value (matches the paper's tables)."""
            if v is None:
                return "—"
            # round(…, 6) first removes float accumulation noise (e.g. 29.374999999 for 1410/4800)
            return str(Decimal(str(round(100 * v, 6))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        def num_cell(v, strong=False, extra=""):
            if v is None:
                return f'<td class="num{extra}">—</td>'
            # Same score-tinted background as the per-scene matrix (td.heat, CSS var --v in 0..1).
            return f'<td class="num heat{" strong" if strong else ""}{extra}" style="--v:{v:.2f}" data-sort="{v:.6f}">{pct(v)}</td>'

        scope_legend = (self.audit or {}).get("scope_legend", {})

        def pol_name(pname):
            """Display name with the provenance (∗ / † / ‡) and scope (§ / ¶) markers of paper Table 1."""
            r = audit_pol.get(pname, {})
            marks = [(m, prov_legend.get(m, "")) for m in [r.get("provenance")] if m] + \
                    [(m, scope_legend.get(m, "")) for m in [r.get("scope")] if m]
            return esc(pname) + "".join(f'<sup class="prov" title="{esc(t)}">{esc(m)}</sup>' for m, t in marks)

        # Paper Table 1: Policy | Level | Overall | D1 … D6 | Pooled, three level rows per policy
        def family_level_table(names, table_id, n_ep):
            rows = []
            for pname in names:
                a = agg.get(pname)
                if not a or a["overall"] is None:
                    continue
                for k, t in enumerate(tiers):
                    cells = []
                    for d in dims:
                        vals = [lb["per_scene"][sc["name"]][pname]["rate"] for sc in d["scenes"]
                                if sc["tier"] == t and lb["per_scene"].get(sc["name"], {}).get(pname)]
                        cells.append(num_cell(sum(vals) / len(vals) if vals else None))
                    first = (f'<td class="pol" rowspan="3">{pol_name(pname)}</td>' if k == 0 else "")
                    span = (f'<td class="num strong heat" rowspan="3" style="--v:{a["overall"]:.2f}" data-sort="{a["overall"]:.6f}">{pct(a["overall"])}</td>' if k == 0 else "")
                    pooled = (f'<td class="num heat" rowspan="3" style="--v:{a["pooled"]:.2f}" data-sort="{a["pooled"]:.6f}">{pct(a["pooled"])}</td>' if k == 0 else "")
                    rows.append(f'<tr class="lvl-{t.lower()}{" first" if k == 0 else ""}">{first}<td class="lvl">{t}</td>{span}{"".join(cells)}{pooled}</tr>')
            counts = "; ".join(f'{d["id"]} ' + "/".join(str(sum(1 for sc in d["scenes"] if sc["tier"] == t)) for t in tiers) for d in dims)
            head = "".join(f'<th title="{esc(d["name_en"])} · {len(d["scenes"])} tasks">{esc(d["id"])} ↑</th>' for d in dims)
            return (f'<div class="table-scroll"><table class="leaderboard family-level" id="{table_id}"><thead><tr><th>Policy</th><th>Level</th>'
                    f'<th title="Mean of the six complete-family means (Eq. 1)">Overall ↑</th>{head}<th title="Successes / all {n_ep} episodes">Pooled ↑</th></tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody></table></div>'
                    f'<p class="muted small">Task counts (L1/L2/L3): {counts}. Dashes mark family–level subsets with no tasks. Level subsets contain different tasks (one to six) and do not isolate a single difficulty factor. '
                    f'Overall and Pooled span the three level rows of each policy.</p>')

        # Paper Table 12 layout: Policy | L1 | L2 | L3 | Overall | Pooled
        def level_table(names, table_id):
            rows = []
            for pname in names:
                a = agg.get(pname)
                if not a or a["overall"] is None:
                    continue
                rows.append(f'<tr><td class="pol">{pol_name(pname)}</td>' + "".join(num_cell(a["tier"].get(t)) for t in tiers)
                            + num_cell(a["overall"], strong=True) + num_cell(a["pooled"]) + '</tr>')
            head = "".join(f'<th data-sort="num" title="Mean over the {n} level-{t[1]} scenes">{t} ↑</th>' for t, n in zip(tiers, (9, 29, 10)))
            return (f'<div class="table-scroll"><table class="leaderboard sortable" id="{table_id}"><thead><tr><th>Policy</th>{head}'
                    f'<th data-sort="num" title="Mean of the six family means (Eq. 1)">Overall ↑</th>'
                    f'<th data-sort="num" title="Successes / all episodes">Pooled ↑</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')

        # Paper Table 13 layout: Policy | D1 … D6
        def family_table(names, table_id):
            rows = []
            for pname in names:
                a = agg.get(pname)
                if not a or a["overall"] is None:
                    continue
                rows.append(f'<tr><td class="pol">{pol_name(pname)}</td>' + "".join(num_cell(a["family"].get(d["id"])) for d in dims) + '</tr>')
            head = "".join(f'<th data-sort="num" title="{esc(d["name_en"])} · {len(d["scenes"])} tasks">{esc(d["id"])} ↑</th>' for d in dims)
            return (f'<div class="table-scroll"><table class="leaderboard sortable" id="{table_id}"><thead><tr><th>Policy</th>{head}</tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody></table></div>')

        prov_html = ""
        if prov_legend:
            prov_html = ('<p class="muted small"><strong>Training provenance</strong> (superscript after each policy; paper Table 1 and Appendix B.2): '
                         + " ".join(f'<sup class="prov">{esc(k)}</sup> {esc(v)}' for k, v in prov_legend.items())
                         + f' Details per checkpoint are on the <a href="{rel}policies/#provenance">Policies page</a>.</p>')
        if scope_legend:
            prov_html += ('<p class="muted small"><strong>Scope</strong> (paper Table 1): '
                          + " ".join(f'<sup class="prov">{esc(k)}</sup> {esc(v)}' for k, v in scope_legend.items())
                          + ' Both rows are excluded from pooled diagnostic statements.</p>')

        # Paper Tables 2 and 7: matched 240-episode comparison transcribed from the paper
        matched_html = ""
        m240 = (self.paper_tables or {}).get("matched240")
        if m240:
            cols = m240["columns"]

            def fmt(v, nd):
                return "—" if v is None else f"{v:.{nd}f}"

            def cell(v, nd, strong=False, heat=False):
                # heat: success columns only (values in percent); timing/call columns keep a plain background.
                cls = "num" + (" strong" if strong else "") + (" heat" if heat and v is not None else "")
                style = f' style="--v:{v / 100:.2f}"' if heat and v is not None else ""
                return f'<td class="{cls}"{style}{"" if v is None else f" data-sort={chr(34)}{v}{chr(34)}"}>{fmt(v, nd)}</td>'

            def t2_row(name, vals, agent=False):
                v = dict(zip(cols, vals))
                nm = (esc(name) + ' <span class="star">*</span>') if name in ('GPT-6 Astra', 'Gemini 3.8 Flash') else (esc(name) if agent else pol_name(name))
                step = f'{v["step_counter"]}' + ("<sup>†</sup>" if agent else "")
                return (f'<tr><td class="pol">{nm}</td>{cell(v["overall"], 2, True, heat=True)}{cell(v["pooled"], 2, heat=True)}{cell(v["calls_per_ep"], 1)}'
                        f'{cell(v["model_s_per_call"], 3)}{cell(v["model_s_per_ep"], 1)}{cell(v.get("eval_wall_s_per_ep"), 1)}'
                        f'{cell(v["episode_wall_s_per_ep"], 1)}<td class="num" data-sort="{v["step_counter"]}">{step}</td></tr>')

            def t7_row(name, vals, agent=False):
                v = dict(zip(cols, vals))
                nm = (esc(name) + ' <span class="star">*</span>') if name in ('GPT-6 Astra', 'Gemini 3.8 Flash') else (esc(name) if agent else pol_name(name))
                return (f'<tr><td class="pol">{nm}</td>{cell(v.get("L1"), 2, heat=True)}{cell(v.get("L2"), 2, heat=True)}{cell(v.get("L3"), 2, heat=True)}'
                        f'{cell(v.get("p50_s_per_call"), 3)}{cell(v.get("p95_s_per_call"), 3)}{cell(v.get("model_share_pct"), 1)}</tr>')

            def grouped(rowfn, ncols):
                prow = "".join(rowfn(k, v) for k, v in m240["policies"].items())
                arow = "".join(rowfn(k, v, True) for k, v in m240["agents"].items())
                return f'<tr class="group"><td colspan="{ncols}">Policies</td></tr>{prow}<tr class="group"><td colspan="{ncols}">Agents</td></tr>{arow}'

            t2_head = ('<tr><th rowspan="2">System</th><th rowspan="2" data-sort="num">Overall ↑</th><th rowspan="2" data-sort="num">Pooled ↑</th>'
                       '<th data-sort="num">Calls</th><th data-sort="num">Model ↓</th><th data-sort="num">Model ↓</th><th data-sort="num">Eval wall ↓</th>'
                       '<th data-sort="num">Episode wall ↓</th><th rowspan="2" data-sort="num">Step counter</th></tr>'
                       '<tr><th class="sub">(/ ep.)</th><th class="sub">(s / call)</th><th class="sub">(s / ep.)</th><th class="sub">(s / ep.)</th><th class="sub">(s / ep.)</th></tr>')
            t7_head = ('<tr><th rowspan="2">System</th><th rowspan="2" data-sort="num">L1 ↑</th><th rowspan="2" data-sort="num">L2 ↑</th><th rowspan="2" data-sort="num">L3 ↑</th>'
                       '<th data-sort="num">p50 ↓</th><th data-sort="num">p95 ↓</th><th data-sort="num">Model share</th></tr>'
                       '<tr><th class="sub">(s / call)</th><th class="sub">(s / call)</th><th class="sub">(%)</th></tr>')
            matched_html = f"""
<h2 id="matched">Matched-seed comparison: first five frozen seeds, 240 episodes per system</h2>
<p>Policies and agents evaluated on the same 240 accepted episodes: the first five frozen seeds of every scene. This is the only table in which the two groups appear together. Success in %, timing in seconds; timing means include failures. <strong>Overall</strong> weights the six families equally; <strong>Pooled</strong> is the success fraction over all 240 episodes. ↑ higher success is better; ↓ lower time is better, read jointly with success. Calls and step counters have no preferred direction. Timing minima do not imply equal success or deployment conditions.</p>
<h3 id="matched-success">Success and timing <span class="muted small">(paper Table 2)</span></h3>
<div class="table-scroll"><table class="leaderboard sortable" id="lb-matched"><thead>{t2_head}</thead><tbody>{grouped(t2_row, 9)}</tbody></table></div>
<p class="muted small"><strong>*</strong> GPT-6 Astra and Gemini 3.8 Flash differ from the policies in exported instruction wording on 84 of the 240 episodes (spanning all 48 scenes) and in staged delivery on two tasks (<a href="{rel}sim-tasks/adjust_bottle_dustbin/">adjust_bottle_dustbin</a>, <a href="{rel}sim-tasks/stapler_pad_press/">stapler_pad_press</a>): these two agents receive the full compound instruction from the start, policies an oracle-staged instruction that switches after stage 1. GPT-6.2 Astra, Opus 5.5 and Gemini 4 Argon use policy-exported wording and the budget adjustments described above. Model-side clocks follow each adapter (policy inference-service report incl. service-side preprocessing vs. agent <code>api_seconds</code>); shared seeds do not equalise deployments. <strong>†</strong> The shared agent step counter is forced to the scene limit at termination and is not actual executed steps. Eval wall time sums timed <code>eval()</code> calls; episode wall time additionally includes observation retrieval and loop overhead. Three superseded GPT-6 attempts from an earlier partial run are excluded. DM0.5: {esc(m240.get("notes", {}).get("DM0.5", ""))}</p>
<h3 id="matched-levels">Level success and latency quantiles <span class="muted small">(paper Table 11)</span></h3>
<div class="table-scroll"><table class="leaderboard sortable" id="lb-matched-levels"><thead>{t7_head}</thead><tbody>{grouped(t7_row, 7)}</tbody></table></div>
<p class="muted small">Same 240 episodes per system; level sample counts are 45 / 145 / 50 episodes. p50 / p95 are quantiles of the <em>episode-mean</em> call times, not pooled per-call percentiles. Model share divides total model-side time by total eval wall time and is descriptive, without a preferred direction. All timings are online evaluation measurements, not isolated hardware speed.</p>
"""

        # Paper Table 10: recorded termination reasons of the agents
        term_html = ""
        term = (self.paper_tables or {}).get("agent_termination")
        if term and lb["agents"]:
            names = [a for a in lb["agents"] if a in term]
            head = "".join(f"<th>{esc(a)}</th>" for a in names)
            rows = []
            for i, label in enumerate(term["rows"]):
                cells = "".join(f'<td class="num">{term[a][i]} <small>({100 * term[a][i] / 240:.2f} %)</small></td>' for a in names)
                rows.append(f'<tr><td>{esc(label)}</td>{cells}</tr>')
            tot = "".join(f'<td class="num">{sum(term[a])} <small>(100.00 %)</small></td>' for a in names)
            term_html = f"""
<h3 id="agents-termination">Recorded termination reasons <span class="muted small">(paper Table 10; 240 accepted episodes per agent)</span></h3>
<div class="table-scroll"><table class="leaderboard" id="lb-agent-termination"><thead><tr><th>Recorded termination</th>{head}</tr></thead><tbody>{"".join(rows)}<tr class="total"><td>Total</td>{tot}</tr></tbody></table></div>
<p class="muted small">Environment success, finish-channel termination and resource limits are mutually exclusive recorded outcomes; every success carries <code>env_success</code>. A <code>model_finish</code> entry means the finish channel ended the attempt before environment success. It is not automatically a false claim of completion: the prompt permits <code>finish</code> when the model cannot proceed, and the client generates the same action after repeated API failures. Separating claimed completion, acknowledged inability and infrastructure-triggered endings requires the final tool note and error trace of each episode. Counts are episode proportions, not the family-balanced Overall.</p>
"""

        # Paper Tables 20–22 (policies) and 24 (agents): scenes as rows, systems as columns
        order = lb["learned"] + lb["agents"]
        scene_head = "".join(f'<th class="rot"><span>{esc(pn)}{" *" if pn in lb["agents"] else ""} ↑</span></th>' for pn in order)
        scene_rows = []
        for d in dims:
            scene_rows.append(f'<tr class="group"><td colspan="{3 + len(order)}">{esc(d["id"])} · {esc(d["name_en"])}</td></tr>')
            for sc in d["scenes"]:
                per = lb["per_scene"].get(sc["name"], {})
                cells = []
                for pn in order:
                    r = per.get(pn)
                    if r is None:
                        cells.append("<td>—</td>")
                    else:
                        v = r["rate"]
                        ci = f' · 95 % Wilson CI [{100 * r["ci"][0]:.1f}, {100 * r["ci"][1]:.1f}]' if r.get("ci") else ""
                        cells.append(f'<td class="heat" style="--v:{v:.2f}" title="{esc(pn)} · {esc(sc["name"])}: {100 * v:.0f} %{ci}">{100 * v:.0f}</td>')
                scene_rows.append(f'<tr><td><a href="{rel}sim-tasks/{sc["name"]}/">{esc(sc["name"])}</a></td><td>{esc(d["id"])}</td><td>{esc(sc["tier"])}</td>{"".join(cells)}</tr>')
        runs = ", ".join(f"<code>{esc(r)}</code>" for r in lb.get("runs", []))
        agents_note = ""
        if lb["agents"]:
            agents_note = f"""
<h2 id="agents">Agents</h2>
<p>Language-model agent systems that act through a shared tool/controller interface (<code>move_eef</code>, <code>finish</code>) with current three-view RGB, measured EEF/joint state and contact/tracking feedback; no privileged object poses. Request settings and budget accounting are listed below; returned provider versions are not pinned. Given evaluation cost, each model is tested on five episodes per scene. Agents are evaluated on the <strong>first 5 frozen seeds</strong> of each scene only (240 episodes per system; 45 / 145 / 50 episodes in L1 / L2 / L3), so the aggregates below use the layouts of the policy tables but are not comparable with the 4,800-episode policy results. Compare the two groups only through the matched-seed tables.</p>
<h3 id="agents-config">Agent configurations</h3>
<div class="table-scroll"><table><thead><tr><th>Agent</th><th>API identifier</th><th>Interface</th><th>Reasoning</th><th>Output cap</th></tr></thead><tbody>
<tr><td>GPT-6 Astra</td><td><code>gpt-6-astra</code></td><td>Responses</td><td>high</td><td>4,096</td></tr>
<tr><td>GPT-6.2 Astra</td><td><code>gpt-6.2-astra</code></td><td>Responses</td><td>high</td><td>4,096</td></tr>
<tr><td>Opus 5.5</td><td><code>claude-opus-5-5</code></td><td>Messages</td><td>adaptive, high</td><td>16,000</td></tr>
<tr><td>Gemini 4 Argon</td><td><code>gemini-4-argon</code></td><td>generateContent</td><td>HIGH</td><td>65,536</td></tr>
<tr><td>Gemini 3.8 Flash</td><td><code>gemini-3.8-flash</code></td><td>generateContent</td><td>HIGH</td><td>8,192</td></tr>
</tbody></table></div>
<p>All agents use a 120-call ceiling and the scene step limit. For GPT-6.2 Astra, Opus 5.5 and Gemini 4 Argon, the soft 3,300 s budget excludes API waiting so that provider latency does not consume the action budget; these agents use policy-exported instruction wording. Gemini 4 Argon's output cap was raised from 8,192 to 65,536 because preliminary requests exhausted the smaller cap during reasoning before producing a tool action. GPT-6 Astra and Gemini 3.8 Flash retain their original September configurations and results. Shared episode identities therefore do not make every configuration identical.</p>
<h3 id="agents-family-level">Task success by family and level (%) <span class="muted small">(layout of paper Table 1; 240 episodes)</span></h3>
{family_level_table(lb["agents"], "lb-agents-family-level", 240)}
<h3 id="agents-levels">Global level, Overall and Pooled success (%) <span class="muted small">(layout of paper Table 12; 240 episodes)</span></h3>
{level_table(lb["agents"], "lb-agents")}
<h3 id="agents-families">Within-family mean task success (%) <span class="muted small">(layout of paper Table 13; 240 episodes)</span></h3>
{family_table(lb["agents"], "lb-agents-families")}
{term_html}
"""
        # hero: the two overall rankings side by side (policies left, agents right)
        def hero_table(names, n_note):
            ranked = sorted((n for n in names if agg.get(n, {}).get("overall") is not None),
                            key=lambda n: -agg[n]["overall"])
            rows = "".join(f'<tr><td class="num rank">{i}</td><td class="pol">{pol_name(n)}</td>'
                           + num_cell(agg[n]["overall"], strong=True) + num_cell(agg[n]["pooled"]) + "</tr>"
                           for i, n in enumerate(ranked, 1))
            return (f'<div class="table-scroll"><table class="leaderboard hero"><thead><tr><th>#</th><th>System</th>'
                    f'<th title="Mean of the six family means (Eq. 1)">Overall ↑</th><th title="Successes / all {n_note} episodes">Pooled ↑</th></tr></thead>'
                    f'<tbody>{rows}</tbody></table></div>')
        hero_html = f"""
<div class="lb-hero">
<div><h3 id="overall-policies">Policies <span class="muted small">(100 episodes per scene, 4,800 per checkpoint)</span></h3>
{hero_table(lb["learned"], "4,800")}</div>
<div><h3 id="overall-agents">Agents <span class="muted small">(first 5 frozen seeds per scene, 240 episodes)</span></h3>
{hero_table(lb["agents"], "240")}
<p class="muted small">Agents run on 240 episodes with different instruction delivery and execution interfaces; these numbers are not comparable with the policy column. See the matched-seed comparison below.</p></div>
</div>
"""
        content = f"""
<h1>Leaderboard</h1>
<p class="lead">Task success on the {self.tasks["suite"]["formal_scenes"]} formal scenes with frozen seeds. Tables follow the layout of the paper: policies (Table 1 and Appendix Tables 12–13), agents (incl. Table 10), the matched-seed comparison of both groups (Tables 2 and 11) and per-scene results (Tables 20–22 and 24).</p>
<h2 id="overall">Overall standings</h2>
<p class="muted small">Ranked by <strong>Overall</strong> (equal weight for the six task families, Eq. 1). Detailed breakdowns and provenance markers ({" ".join(f'<sup class="prov">{esc(k)}</sup>' for k in list(prov_legend) + list(scope_legend))}) are explained in the sections below.</p>
{hero_html}
{intro_html}
<h2 id="policies">Policies</h2>
<p>The {len(lb["learned"])} learned policy checkpoints (VLA and world-action models) evaluated on 100 episodes per scene, 4,800 per checkpoint, after RoboTwin 2.0 training and without adaptation on the derived scenes. Training conditions, enabled inference modules, observation histories, action horizons and control interfaces (joint vs. end-effector) differ between checkpoints, so this comparison concerns the supplied checkpoints and their execution pipelines rather than matched-training architectures. Rows follow the order of the paper; where a header is clickable, click it to sort.</p>
{prov_html}
<h3 id="policies-family-level">Task success by family and level (%) <span class="muted small">(paper Table 1)</span></h3>
<p class="muted small"><strong>Overall</strong> averages the six complete-family means equally (Eq. 1); <strong>Pooled</strong> is success over all 4,800 episodes. Family–level cells average the tasks in that subset; to reconstruct a family mean from them, weight the level cells by their task counts. Bold in the paper marks the highest observed value, not statistical significance.</p>
{family_level_table(lb["learned"], "lb-policies-family-level", 4800)}
<h3 id="policies-levels">Global level, Overall and Pooled task success (%) <span class="muted small">(paper Table 12)</span></h3>
<p class="muted small"><strong>L1 / L2 / L3</strong> weight their 9 / 29 / 10 scenes equally without family balancing. All twelve checkpoints show decreasing global success from L1 to L3; the level sets contain different tasks, so this does not validate a general difficulty scale. Per-task Wilson intervals are on the scene pages.</p>
{level_table(lb["learned"], "lb-policies")}
<h3 id="policies-families">Within-family mean task success (%) <span class="muted small">(paper Table 13)</span></h3>
<p class="muted small">D1–D6 contain 10 / 9 / 9 / 7 / 6 / 7 tasks; D6 is the mixture family. Each column averages its tasks equally, and the unrounded column means receive equal weight in Overall. These are final task-success rates, not attribute-selection or subtask-completion rates.</p>
{family_table(lb["learned"], "lb-policies-families")}
{agents_note}
{matched_html}
<h2 id="per-scene">Per-scene task success (%)</h2>
<p class="muted small">Layout of paper Tables 20–22 (policies, 100 episodes per scene) and Table 24 (agents *, 5 episodes per scene): scenes as rows in family order, systems as columns in paper order. Hover a cell for the per-scene 95 % Wilson interval; the intervals are also listed on each scene page.</p>
<div class="table-scroll"><table class="matrix"><thead><tr><th>Scene</th><th>Family</th><th>Level</th>{scene_head}</tr></thead><tbody>{"".join(scene_rows)}</tbody></table></div>
<h2 id="provenance">Provenance</h2>
<p>Code freeze <code>{esc(lb.get("snapshot", ""))}</code>. Runs: {runs or "—"}. Source file: <code>{esc(lb.get("source", ""))}</code>. Aggregates on this page are recomputed from the per-scene rates and reproduce the paper's Tables 1, 10 and 11; the matched-seed and termination tables are transcribed from the paper. On the two staged-delivery tasks GPT-6 Astra and Gemini 3.8 Flash receive the full compound instruction from the start (paper Appendix B). To regenerate from new evaluations, run <code>python3 suite/collect.py</code> and <code>suite/compare_runs.py</code> in the benchmark repository, then re-run <code>scripts/sync_from_maniscope.py</code> here. Entries added after the paper snapshot must state their evaluation version separately.</p>
<h2 id="submit">Submitting results</h2>
<p>Report the model and adapter revision, training provenance (backbone, robot or latent-action pretraining, RoboTwin adaptation quota), enabled inference modules, control interface, prediction and execution lengths, observation history, image preprocessing, hardware and sampling settings alongside success rates; the shared evaluator does not equalise these. For agents also record tools, skills, examples, memory, prompt revisions and provider versions. Include the <code>_run_metadata.json</code> emitted per task (commit, dirty state, protocol hashes).</p>
"""
        toks = [{"id": "overall", "name": "Overall standings", "children": []}] + intro_toks + [{"id": "policies", "name": "Policies", "children": [
            {"id": "policies-family-level", "name": "Table 1 · family × level", "children": []},
            {"id": "policies-levels", "name": "Table 12 · global levels", "children": []},
            {"id": "policies-families", "name": "Table 13 · families", "children": []}]}]
        if lb["agents"]:
            toks.append({"id": "agents", "name": "Agents", "children": [{"id": "agents-termination", "name": "Table 10 · termination", "children": []}] if term_html else []})
        if matched_html:
            toks.append({"id": "matched", "name": "Matched-seed comparison", "children": [
                {"id": "matched-success", "name": "Table 2 · success and timing", "children": []},
                {"id": "matched-levels", "name": "Table 11 · levels and latency", "children": []}]})
        toks += [{"id": "per-scene", "name": "Per-scene task success", "children": []},
                 {"id": "provenance", "name": "Provenance", "children": []}, {"id": "submit", "name": "Submitting results", "children": []}]
        self.page(out_path, "Leaderboard", content, toc_html(toks), description="ManipScope leaderboard: policies and agents.", body_class="leaderboard")

    # ---- misc -------------------------------------------------------------------
    def build_404(self):
        content = '<h1>Page not found</h1><p>The page you requested does not exist. <a href="">Return home</a>.</p>'
        rel = ""
        write(os.path.join(OUT, "404.html"), self.fix_links(render_template(
            "base.html", lang="en", title="Not found", site_name=esc(self.cfg["site"]["name"]), description="", rel=rel,
            body_class="", robots=self.robots_meta(), header_links=self.header_links(rel), sidebar=self.sidebar("404", rel), content=content, toc="",
            footer_left="", extra_scripts="", asset_v=self.asset_v, clean_urls="true" if self.clean_urls else "false")))

    def copy_assets(self):
        dst = os.path.join(OUT, "assets")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(ASSETS, dst, ignore=shutil.ignore_patterns("README.md", ".gitkeep"))
        translations = json.loads(read(os.path.join(DATA, "i18n-zh.json")))
        write(os.path.join(OUT, "assets/js/translations-zh.js"),
              "window.__ZH__ = " + json.dumps(translations, ensure_ascii=True) + ";\n")
        write(os.path.join(OUT, "search-index.json"), json.dumps(self.search_docs, ensure_ascii=False))
        write(os.path.join(OUT, ".nojekyll"), "")

    def build(self):
        if os.path.exists(OUT):
            for entry in os.listdir(OUT):
                p = os.path.join(OUT, entry)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        self.build_home()
        self.build_markdown_dir("usage")
        self.build_markdown_dir("common-issue")
        self.build_tasks_index()
        self.build_task_pages()
        self.build_policies()
        self.build_leaderboard()
        if os.path.exists(os.path.join(CONTENT, "diagnostics.md")):
            self.build_markdown_file("diagnostics.md", "diagnostics/index.html")
        if os.path.exists(os.path.join(CONTENT, "participate.md")):
            self.build_markdown_file("participate.md", "participate/index.html")
        if os.path.exists(os.path.join(CONTENT, "community.md")):
            self.build_markdown_file("community.md", "community/index.html")
        self.build_404()
        self.copy_assets()
        print(f"built {self.pages} pages -> {OUT}")


def md_inline(text):
    """Render a one-line markdown snippet (code spans, emphasis) without wrapping <p>."""
    out = markdown.markdown(text, extensions=[])
    return re.sub(r"^<p>|</p>$", "", out.strip())


if __name__ == "__main__":
    Site().build()
