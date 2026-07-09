# Privateer Docs

Static documentation site for Privateer.

## Structure

```
content/        # one markdown file per page, YAML frontmatter (title, slug, group, order, description)
assets/         # style.css, main.js, self-hosted fonts, architecture figure
build.py        # markdown -> HTML, nav, TOC, prev/next, search index, landing page
site/           # build output — open site/index.html directly or serve it
```

## Build

```bash
pip install markdown # or : python3 -m pip install markdown 
python3 build.py

#for local preview 
python3 -m http.server 8000 --directory site 
#live at : http://localhost:8000/

```


## Adding a page

Drop a new `.md` file in `content/` with frontmatter:

```yaml
---
title: Page title
slug: page-slug
group: Getting started   # or: Developer reference
order: 7
description: One-line summary shown under the title.
---
```
