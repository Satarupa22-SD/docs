#!/usr/bin/env python3
"""Build the Privateer docs site: content/*.md -> site/*.html."""
import json
import re
import shutil
from html import escape
from pathlib import Path

import markdown

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
OUT = ROOT / "site"
REPO_URL = "https://github.com/privateerproj"
MERIDIAN_URL = "https://meridian.revanite.io/"
# TODO: replace with the real Privateer Slack invite link when available
SLACK_URL = "https://slack.example.com/privateer"
LINKEDIN_URL = "https://www.linkedin.com/company/privateerproj/"
BRAND_LOGO = "assets/logo/patches-head.png"  # swap path here to change the brand mark

# ---------------------------------------------------------------- partners
# "Used by" logos. To add an org, append a dict here and drop the image in
# assets/partners/ and the layout tier below adapts to the count automatically.
PARTNERS = [
    {"name": "LFX Insights", "logo": "assets/partners/lfx.svg",
     "href": "https://insights.linuxfoundation.org/"},
    {"name": "FINOS CCC", "logo": "assets/partners/finos-horizontal.svg",
     "href": "https://ccc.finos.org/"},
    {"name": "OpenSSF", "logo": "assets/partners/openssf.svg",
     "href": "https://openssf.org/"},
]


def logo_tier(n):
    """Pick a layout tier from the partner count (computed at build time,
    in the spirit of Pretext's editorial-engine demo: content drives layout).
      <= 4 logos: one generous centered row
      5-8 logos:  tighter wrapped grid, smaller marks
      > 8 logos:  compact logo wall, smallest marks
    """
    if n <= 4:
        return "tier-row"
    if n <= 8:
        return "tier-grid"
    return "tier-wall"


# Base size per tier: the height (px) a perfectly square logo would render at.
TIER_BASE = {"tier-row": 54, "tier-grid": 38, "tier-wall": 30}


def image_dimensions(path):
    """Intrinsic (width, height) of an SVG or PNG, stdlib only."""
    p = ROOT / path
    if p.suffix.lower() == ".svg":
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', text)
        if m:
            return float(m.group(1)), float(m.group(2))
        mw = re.search(r'\bwidth="([\d.]+)', text)
        mh = re.search(r'\bheight="([\d.]+)', text)
        if mw and mh:
            return float(mw.group(1)), float(mh.group(1))
    elif p.suffix.lower() == ".png":
        import struct
        with open(p, "rb") as f:
            head = f.read(24)
        if head[12:16] == b"IHDR":
            w, h = struct.unpack(">II", head[16:24])
            return float(w), float(h)
    return 1.0, 1.0  # unknown: treat as square


# Max rendered width per tier: wide banners get height-capped so they
# don't visually dominate narrower marks.
TIER_MAX_W = {"tier-row": 160, "tier-grid": 130, "tier-wall": 100}


def logo_height(path, tier):
    """Size logos so they look uniform: equal-area as a starting point,
    then width-capped so wide banners shrink and narrow marks grow.
    """
    iw, ih = image_dimensions(path)
    aspect = max(iw / ih, 0.05)
    base = TIER_BASE[tier]
    px = base / (aspect ** 0.5)
    px = min(max(px, base * 0.65), base * 1.6)
    # if rendered width exceeds the cap, shrink height to fit
    max_w = TIER_MAX_W[tier]
    if px * aspect > max_w:
        px = max_w / aspect
    return round(px)


GROUP_ORDER = ["Getting started", "Developer reference"]

# ---------------------------------------------------------------- parsing

def parse_page(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    meta["order"] = int(meta.get("order", 99))
    return meta, m.group(2)


def render_md(body):
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc"],
                           extension_configs={"toc": {"toc_depth": "2-3"}})
    html = md.convert(body)
    toc = [{"id": t["id"], "name": t["name"], "level": t["level"]}
           for t in flatten_toc(md.toc_tokens)]
    return html, toc


def flatten_toc(tokens, out=None):
    out = [] if out is None else out
    for t in tokens:
        out.append(t)
        flatten_toc(t.get("children", []), out)
    return out


def chipify(html):
    """Wrap bare result-value codes in table cells with status chips."""
    for val in ("pass", "fail", "skip", "error"):
        html = html.replace(f"<td><code>{val}</code></td>",
                            f'<td><span class="chip {val}">{val}</span></td>')
    return html


def strip_text(html):
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()

# ---------------------------------------------------------------- templates

ICONS = {
    "menu": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
    "search": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
    "sun": '<svg class="sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    "moon": '<svg class="moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>',
    "github": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.7.5.6 5.6.6 11.9c0 5 3.3 9.3 7.8 10.8.6.1.8-.2.8-.5v-2c-3.2.7-3.9-1.3-3.9-1.3-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.7 2.7 1.2 3.3.9.1-.7.4-1.2.7-1.5-2.5-.3-5.2-1.3-5.2-5.7 0-1.3.4-2.3 1.2-3.1-.1-.3-.5-1.5.1-3 0 0 1-.3 3.1 1.2a10.9 10.9 0 0 1 5.7 0C18 4.6 19 4.9 19 4.9c.6 1.5.2 2.7.1 3 .8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.2 5.7.4.4.8 1 .8 2.1v3.1c0 .3.2.7.8.5 4.5-1.5 7.8-5.8 7.8-10.8C23.4 5.6 18.3.5 12 .5Z"/></svg>',
    "arrow": '<svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M7 17 17 7M9 7h8v8"/></svg>',
}


def nav_html(pages, active_slug):
    groups = {}
    for p in pages:
        groups.setdefault(p["group"], []).append(p)
    parts = []
    for g in GROUP_ORDER:
        items = ""
        for p in sorted(groups.get(g, []), key=lambda x: x["order"]):
            active = ' class="active"' if p["slug"] == active_slug else ""
            items += (f'<li><a href="{p["slug"]}.html"{active}>'
                      f'{escape(p["title"])}</a></li>')
        parts.append(f'<div class="nav-group"><h4>{escape(g)}</h4><ul>{items}</ul></div>')
    return "".join(parts)


def slim_footer():
    """Compact footer used on doc pages."""
    return f"""<footer class="site-footer">
  <div class="footer-inner">
    <span>Privateer is an open source validation framework.</span>
    <nav>
      <a href="{REPO_URL}" target="_blank" rel="noopener">GitHub</a>
      <a href="{REPO_URL}/releases" target="_blank" rel="noopener">Releases</a>
      <a href="https://gemara.openssf.org/" target="_blank" rel="noopener">Gemara</a>
      <a href="https://baseline.openssf.org/" target="_blank" rel="noopener">OSPS Baseline</a>
    </nav>
  </div>
</footer>"""


def rich_footer():
    """Full footer used on the home page (ported from privateer-site)."""
    slack_icon = ('<svg viewBox="0 0 24 24" fill="currentColor"><path d="M5.04 15.16a2.02 2.02 0 0 1'
                  '-2.02 2.02A2.02 2.02 0 0 1 1 15.16c0-1.11.9-2.02 2.02-2.02h2.02v2.02Zm1.02 0c0-1.11.9'
                  '-2.02 2.02-2.02s2.02.9 2.02 2.02v5.06a2.02 2.02 0 0 1-2.02 2.02 2.02 2.02 0 0 1-2.02'
                  '-2.02v-5.06ZM8.08 5.04a2.02 2.02 0 0 1-2.02-2.02C6.06 1.91 6.96 1 8.08 1s2.02.9 2.02'
                  ' 2.02v2.02H8.08Zm0 1.02c1.11 0 2.02.9 2.02 2.02s-.9 2.02-2.02 2.02H3.02A2.02 2.02 0 0'
                  ' 1 1 8.08c0-1.11.9-2.02 2.02-2.02h5.06ZM18.96 8.08c0-1.11.9-2.02 2.02-2.02S23 6.96 23'
                  ' 8.08s-.9 2.02-2.02 2.02h-2.02V8.08Zm-1.02 0c0 1.11-.9 2.02-2.02 2.02a2.02 2.02 0 0 1'
                  '-2.02-2.02V3.02c0-1.11.9-2.02 2.02-2.02s2.02.9 2.02 2.02v5.06ZM15.92 18.96c1.11 0 2.02'
                  '.9 2.02 2.02S17.03 23 15.92 23a2.02 2.02 0 0 1-2.02-2.02v-2.02h2.02Zm0-1.02a2.02 2.02'
                  ' 0 0 1-2.02-2.02c0-1.11.9-2.02 2.02-2.02h5.06c1.11 0 2.02.9 2.02 2.02s-.9 2.02-2.02'
                  ' 2.02h-5.06Z"/></svg>')
    linkedin_icon = ('<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.4 20.4h-3.5v-5.6c0-1.3 0-3-1.9'
                     '-3s-2.1 1.4-2.1 2.9v5.7H9.4V9h3.4v1.6h.1c.5-.9 1.6-1.9 3.4-1.9 3.6 0 4.2 2.4 4.2 5.4v6.3'
                     'ZM5.3 7.4a2 2 0 1 1 0-4.1 2 2 0 0 1 0 4.1ZM7.1 20.4H3.6V9h3.5v11.4Z"/></svg>')
    return f"""<footer class="home-footer">
  <div class="home-footer-inner">
    <div class="home-footer-top">
      <div class="footer-brand">
        <div class="row"><img src="{BRAND_LOGO}" alt=""><span class="name">Privateer</span></div>
        <p>Open-source infrastructure validation and compliance for modern DevSecOps teams.</p>
        <div class="footer-social">
          <a href="{REPO_URL}" target="_blank" rel="noopener" aria-label="GitHub">{ICONS["github"]}</a>
          <a href="{SLACK_URL}" target="_blank" rel="noopener" aria-label="Slack">{slack_icon}</a>
          <a href="{LINKEDIN_URL}" target="_blank" rel="noopener" aria-label="LinkedIn">{linkedin_icon}</a>
        </div>
      </div>
      <div class="footer-cols">
        <div>
          <h4>Project</h4>
          <ul>
            <li><a href="{MERIDIAN_URL}" target="_blank" rel="noopener">Meridian</a></li>
            <li><a href="#">Blog</a></li>
          </ul>
        </div>
        <div>
          <h4>Community</h4>
          <ul>
            <li><a href="{SLACK_URL}" target="_blank" rel="noopener">Slack</a></li>
            <li><a href="{LINKEDIN_URL}" target="_blank" rel="noopener">LinkedIn</a></li>
          </ul>
        </div>
        <div>
          <h4>Docs</h4>
          <ul>
            <li><a href="library.html">Library</a></li>
            <li><a href="quickstart.html">Quickstart</a></li>
          </ul>
        </div>
      </div>
    </div>
    <div class="home-footer-bottom">
      <span>&copy; 2026 Privateer. Open-source under the Apache 2.0 License.</span>
      <a href="{REPO_URL}?tab=coc-ov-file" target="_blank" rel="noopener">Code of Conduct</a>
    </div>
  </div>
</footer>"""


def shell(title, description, body, nav, active_tab, brand_suffix="docs",
          footer=None):
    tabs = ""
    for key, label, href in [
        ("home", "Home", "index.html"),
        ("library", "Library", "library.html"),
        ("start", "Getting started", "introduction.html"),
        ("dev", "Developer reference", "cli-reference.html"),
    ]:
        active = ' class="active"' if key == active_tab else ""
        tabs += f'<a href="{href}"{active}>{label}</a>'
    if footer is None:
        footer = slim_footer()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · Privateer Docs</title>
<meta name="description" content="{escape(description)}">
<link rel="stylesheet" href="assets/style.css">
<script>try{{if(localStorage.getItem('pvtr-theme')==='dark'||(!localStorage.getItem('pvtr-theme')&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}}catch(e){{}}</script>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <button id="menu-btn" class="icon-btn" aria-label="Open navigation">{ICONS["menu"]}</button>
    <a class="brand" href="index.html"><img class="logo" src="{BRAND_LOGO}" alt="" height="26">privateer <span class="docs">/ {brand_suffix}</span></a>
    <div class="header-search">
      <button class="search-trigger" data-search-open>{ICONS["search"]}<span>Search docs&hellip;</span><kbd>Ctrl K</kbd></button>
    </div>
    <nav class="header-tabs">{tabs}</nav>
    <div class="header-actions">
      <button id="theme-btn" class="icon-btn" aria-label="Toggle theme">{ICONS["sun"]}{ICONS["moon"]}</button>
      <a class="icon-btn" href="{REPO_URL}" target="_blank" rel="noopener" aria-label="GitHub">{ICONS["github"]}</a>
    </div>
  </div>
</header>
<div class="drawer-backdrop"></div>
<aside class="drawer">{nav}</aside>
{body}
{footer}
<div class="search-overlay">
  <div class="search-panel">
    <input id="search-input" type="text" placeholder="Search the Privateer docs&hellip;" aria-label="Search">
    <div id="search-results" class="search-results"></div>
  </div>
</div>
<script src="search-index.js"></script>
<script src="assets/main.js"></script>
</body>
</html>"""


def doc_body(page, html, toc, nav, prev_p, next_p):
    toc_html = ""
    if toc:
        links = "".join(
            f'<li><a class="depth-{t["level"]}" href="#{t["id"]}">{escape(t["name"])}</a></li>' for t in toc)
        toc_html = f'<aside class="toc"><div class="toc-inner"><h5>On this page</h5><ul>{links}</ul></div></aside>'
    pn = ""
    if prev_p or next_p:
        prev_a = (f'<a class="prev" href="{prev_p["slug"]}.html"><span class="dir">&larr; Previous</span>'
                  f'<span class="name">{escape(prev_p["title"])}</span></a>') if prev_p else "<span></span>"
        next_a = (f'<a class="next" href="{next_p["slug"]}.html"><span class="dir">Next &rarr;</span>'
                  f'<span class="name">{escape(next_p["title"])}</span></a>') if next_p else ""
        pn = f'<div class="prev-next">{prev_a}{next_a}</div>'
    return f"""<div class="shell">
  <aside class="sidebar"><div class="sidebar-scroll">{nav}</div></aside>
  <main class="doc-main">
    <article class="doc-column">
      <div class="crumbs">{escape(page["group"])}<span class="sep">/</span>{escape(page["title"])}</div>
      <h1 class="page-title">{escape(page["title"])}</h1>
      <p class="page-desc">{escape(page["description"])}</p>
      <div class="prose">{html}</div>
      <a class="edit-link" href="{REPO_URL}" target="_blank" rel="noopener">Edit this page on GitHub &#8599;</a>
      {pn}
    </article>
    {toc_html}
  </main>
</div>"""

# ---------------------------------------------------------------- home page

FIT_ICONS = {
    "branch": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="6" r="3"/><path d="M6 9v6M18 9a9 9 0 0 1-9 9"/></svg>',
    "filecode": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6M10 13l-2 2 2 2M14 13l2 2-2 2"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg>',
    "workflow": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><path d="M10 6.5h5A2.5 2.5 0 0 1 17.5 9v5"/></svg>',
    "cloud": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.5 19a4.5 4.5 0 0 0 .4-9A7 7 0 0 0 4.3 12.6 4 4 0 0 0 6 19.9h11.5Z"/></svg>',
    "puzzle": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 7V4.5A1.5 1.5 0 0 0 12.5 3h-1A1.5 1.5 0 0 0 10 4.5V7H6a2 2 0 0 0-2 2v3h2.5a1.5 1.5 0 0 1 1.5 1.5v1A1.5 1.5 0 0 1 6.5 16H4v3a2 2 0 0 0 2 2h3v-2.5a1.5 1.5 0 0 1 1.5-1.5h1a1.5 1.5 0 0 1 1.5 1.5V21h3a2 2 0 0 0 2-2v-4h2.5a1.5 1.5 0 0 0 0-3H18V9a2 2 0 0 0-2-2h-2Z"/></svg>',
}

FITS = [
    ("branch", "CI/CD Pipelines",
     "Validate infrastructure automatically within GitHub Actions, GitLab CI, and Jenkins."),
    ("filecode", "Infrastructure as Code",
     "Ensure Terraform, Kubernetes, and cloud configurations meet compliance standards."),
    ("shield", "Policy-as-Code & Compliance",
     "Enforce governance using automated, policy-driven validation."),
    ("workflow", "DevSecOps Workflows",
     "Embed security and compliance throughout the software delivery lifecycle."),
    ("cloud", "Cloud-Native Ecosystem",
     "Integrate seamlessly with modern cloud and containerized environments."),
    ("puzzle", "Open-Source Plugin Framework",
     "Extend capabilities through community-driven validation plugins."),
]


def home_body():
    tier = logo_tier(len(PARTNERS))
    logos = "".join(
        f'<a href="{p["href"]}" target="_blank" rel="noopener" aria-label="{escape(p["name"])}">'
        f'<img src="{p["logo"]}" alt="{escape(p["name"])}" loading="lazy"'
        f' style="height:{logo_height(p["logo"], tier)}px"></a>'
        for p in PARTNERS)
    fit_cards = "".join(
        f'<div class="card fit-card"><div class="fit-icon">{FIT_ICONS[icon]}</div>'
        f'<h3>{escape(title)}</h3><p>{escape(desc)}</p></div>'
        for icon, title, desc in FITS)
    return f"""<section class="home-hero">
  <div class="home-hero-inner">
    <div class="home-hero-copy">
      <div class="hero-badges">
        <span>Open Source</span><span>DevSecOps Ready</span><span>Policy-as-Code</span><span>CI/CD Integrated</span>
      </div>
      <h1>Automate Infrastructure <span class="accent">Validation &amp; Compliance</span></h1>
      <p class="sub">Privateer empowers teams to test, secure, and validate infrastructure using policy-driven automation and community-powered plugins.</p>
      <div class="hero-ctas">
        <a class="btn btn-primary" href="{REPO_URL}" target="_blank" rel="noopener">View on GitHub &rarr;</a>
      </div>
    </div>
    <div class="hero-mascot"><div class="glow"><img src="assets/logo/privateer-mascot.png" alt="Privateer mascot"></div></div>
  </div>
</section>
<section class="used-by">
  <div class="used-by-inner">
    <h2>Trusted and used by</h2>
    <div class="logos {tier}">{logos}</div>
  </div>
</section>
<section class="fits">
  <div class="fits-head">
    <h2>Where Privateer <span class="accent">Fits</span></h2>
    <p>Seamlessly integrated into your DevSecOps and cloud-native workflows.</p>
  </div>
  <div class="card-grid cols-3">{fit_cards}</div>
  <div class="fits-cta"><a class="btn btn-primary" href="library.html">Explore Documentation &rarr;</a></div>
</section>"""


# ---------------------------------------------------------------- library

def landing_body():
    def card(href, title, desc, badge="", featured=False):
        b = f'<span class="badge">{badge}</span>' if badge else ""
        cls = "card featured" if featured else "card"
        return (f'<a class="{cls}" href="{href}">{b}<h3>{escape(title)}</h3>'
                f'<p>{escape(desc)}</p>{ICONS["arrow"]}</a>')

    course_svg = """<svg class="hero-course" viewBox="0 0 400 300" fill="none" aria-hidden="true">
      <path d="M40 250 L130 190 L210 210 L290 120 L360 70" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="5 6" opacity="0.55"/>
      <g fill="var(--accent)"><circle cx="40" cy="250" r="3.5"/><circle cx="130" cy="190" r="3.5"/><circle cx="210" cy="210" r="3.5"/><circle cx="290" cy="120" r="3.5"/></g>
      <g stroke="var(--brass)" stroke-width="1.5" fill="none"><circle cx="360" cy="70" r="7"/><circle cx="360" cy="70" r="2.2" fill="var(--brass)" stroke="none"/></g>
    </svg>"""

    start_cards = "".join([
        card("quickstart.html", "Quickstart (5 minutes)",
             "Install pvtr, add the GitHub repo scanner plugin, and run your first validation.",
             badge="Recommended", featured=True),
        card("introduction.html", "Introduction",
             "How Core, plugins, and the SDK fit together, and why compliance is a data engineering problem."),
        card("installation.html", "Installation",
             "Install script, GitHub releases, source builds, or Homebrew on Windows, Linux, and macOS."),
        card("first-run.html", "Your first validation run",
             "Validate a GitHub repository step by step, from plugin install to results on disk."),
        card("results.html", "Understanding results",
             "Where output lands, how to switch between YAML, JSON, and SARIF, and CI-friendly flags."),
        card("upgrading.html", "Upgrading Privateer",
             "Keep the binary current, and remember that plugins upgrade independently."),
    ])
    dev_cards = "".join([
        card("cli-reference.html", "CLI reference",
             "Every pvtr subcommand and flag: run, install, list, env, version, generate-plugin, completion."),
        card("configuration.html", "Configuration reference",
             "Top-level and per-service settings, variable resolution, policy, and the invasive flag."),
        card("output-schema.html", "Output schema",
             "File locations, the Gemara Evaluation Log JSON schema, result values, and SARIF 2.1.0."),
        card("build-a-plugin.html", "Build your first plugin",
             "Generate a scaffold from a Gemara Layer 2 catalog, implement AssessmentSteps, and publish."),
        card("github-actions.html", "GitHub Actions integration",
             "Run validations in CI, inject secrets safely, and upload SARIF to the Security tab."),
        card("troubleshooting.html", "Troubleshooting",
             "PATH problems, plugin discovery, missing output files, policy errors, and edge builds."),
    ])
    chips = "".join(f'<span class="chip {v}">{v}</span>' for v in ("pass", "fail", "skip", "error"))
    return f"""<main class="landing">
  <section class="hero">
    {course_svg}
    <div class="hero-inner">
      <div class="eyebrow">Compliance as a data engineering problem</div>
      <h1>Validate your infrastructure against the standards that <span class="accent">actually apply</span>.</h1>
      <p>Privateer is a validation framework that runs automated checks, called plugins, against your resources,
         then writes structured, machine-readable evidence in YAML, JSON, or SARIF. Built to operate at the
         Evaluation layer of the Gemara GRC engineering model.</p>
      <div class="hero-ctas">
        <a class="btn btn-primary" href="quickstart.html">Get started &rarr;</a>
        <a class="btn btn-ghost" href="{REPO_URL}" target="_blank" rel="noopener">View on GitHub</a>
      </div>
      <div class="hero-install"><span class="dollar">$</span>/bin/bash -c "$(curl -sSL https://raw.githubusercontent.com/privateerproj/privateer/main/install.sh)"</div>
      <div class="signal-row">{chips}</div>
    </div>
  </section>

  <h2 class="section-label">Getting started</h2>
  <p class="section-sub">From zero to a control-by-control validation report.</p>
  <div class="card-grid cols-3">{start_cards}</div>

  <h2 class="section-label">Developer reference</h2>
  <p class="section-sub">For plugin authors, contributors, and CI/CD pipeline engineers.</p>
  <div class="card-grid cols-3">{dev_cards}</div>

</main>"""

# ---------------------------------------------------------------- build

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets", OUT / "assets",
                    ignore=shutil.ignore_patterns("architecture-overview.png"))
    (OUT / "assets").mkdir(exist_ok=True)
    shutil.copy(ROOT / "assets" / "architecture-overview.png", OUT / "assets")

    pages = []
    for path in CONTENT.glob("*.md"):
        meta, body = parse_page(path)
        meta["body_md"] = body
        pages.append(meta)
    pages.sort(key=lambda p: (GROUP_ORDER.index(p["group"]), p["order"]))

    search_index = []
    for i, page in enumerate(pages):
        html, toc = render_md(page["body_md"])
        html = chipify(html)
        nav = nav_html(pages, page["slug"])
        prev_p = pages[i - 1] if i > 0 else None
        next_p = pages[i + 1] if i < len(pages) - 1 else None
        tab = "start" if page["group"] == "Getting started" else "dev"
        doc = shell(page["title"], page["description"],
                    doc_body(page, html, toc, nav, prev_p, next_p), nav, tab)
        (OUT / f'{page["slug"]}.html').write_text(doc, encoding="utf-8")
        search_index.append({
            "title": page["title"], "group": page["group"],
            "url": f'{page["slug"]}.html', "body": strip_text(html)[:1200],
        })

    nav = nav_html(pages, None)
    (OUT / "index.html").write_text(
        shell("Privateer", "Open-source infrastructure validation and compliance for modern DevSecOps teams.",
              home_body(), nav, "home", brand_suffix="home", footer=rich_footer()),
        encoding="utf-8")
    (OUT / "library.html").write_text(
        shell("Library", "The Privateer documentation library with every guide and reference page.",
              landing_body(), nav, "library", brand_suffix="library"),
        encoding="utf-8")
    (OUT / "search-index.js").write_text(
        "window.__PVTR_SEARCH_INDEX__ = " + json.dumps(search_index) + ";", encoding="utf-8")
    print(f"Built {len(pages) + 2} pages -> {OUT}")


if __name__ == "__main__":
    main()
