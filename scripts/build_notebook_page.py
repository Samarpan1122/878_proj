"""Render GeoCrashAI_Complete_Analysis.ipynb into the public site's /notebook/ page.

    uv run --with markdown python scripts/build_notebook_page.py

Writes web/public/notebook.html, one PNG per figure under web/public/notebook/, and a
copy of the .ipynb served at /assets/ for download.
Rerun after re-executing the notebook; the page is static and needs no Jupyter at runtime.
"""
import base64
import html
import json
import re
import shutil
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'GeoCrashAI_Complete_Analysis.ipynb'
PAGE, FIGURES = ROOT / 'web/public/notebook.html', ROOT / 'web/public/notebook'
DOWNLOAD = ROOT / 'web/public' / NOTEBOOK.name  # served by the /assets mount
NAV = [('/', 'Map'), ('/explore/', 'Data'), ('/screening/', 'Road screening'), ('/notebook/', 'Analysis')]
SCOPED_STYLE = re.compile(r'<style scoped>.*?</style>', re.S)


def slug(title):
    """'4. Exploratory data analysis' -> 'exploratory-data-analysis' (stable anchors for the site nav)."""
    return re.sub(r'[^a-z0-9]+', '-', re.sub(r'^[\d.]+\s*', '', title.lower())).strip('-')


def text(value):
    return ''.join(value) if isinstance(value, list) else value


def render_output(output, figure, section):
    data = output.get('data', {})
    if output.get('output_type') == 'stream':
        return f'<pre class="nb-stream">{html.escape(text(output["text"]))}</pre>', figure
    if 'image/png' in data:
        figure += 1
        name = f'fig-{figure:02d}.png'
        (FIGURES / name).write_bytes(base64.b64decode(text(data['image/png'])))
        alt = html.escape(f'Figure {figure}: {section}')
        return f'<figure class="nb-figure"><img src="/assets/notebook/{name}" alt="{alt}" loading="lazy"><figcaption>Figure {figure}</figcaption></figure>', figure
    if 'text/html' in data:  # pandas tables from the author's own notebook
        return f'<div class="nb-table">{SCOPED_STYLE.sub("", text(data["text/html"]))}</div>', figure
    if 'text/plain' in data:
        return f'<pre class="nb-stream">{html.escape(text(data["text/plain"]))}</pre>', figure
    return '', figure


def render(cells):
    body, toc, figure, section = [], [], 0, 'Introduction'
    for cell in cells:
        source = text(cell['source'])
        if cell['cell_type'] == 'markdown':
            block = markdown.markdown(source, extensions=['tables', 'fenced_code'])
            for level, title in re.findall(r'^(#{2,3}) (.+)$', source, re.M):
                anchor = slug(title)
                toc.append((len(level), title.strip(), anchor))
                block = block.replace(f'<h{len(level)}>{html.escape(title.strip(), quote=False)}</h{len(level)}>',
                                      f'<h{len(level)} id="{anchor}">{html.escape(title.strip(), quote=False)}</h{len(level)}>', 1)
                section = title.strip()
            body.append(f'<div class="nb-markdown">{block}</div>')
            continue
        if cell['cell_type'] != 'code' or not source.strip():
            continue
        lines = source.count('\n') + 1
        parts = [f'<details class="nb-code"><summary>Code · {lines} line{"s" * (lines != 1)}</summary><pre><code>{html.escape(source)}</code></pre></details>']
        for output in cell.get('outputs', []):
            rendered, figure = render_output(output, figure, section)
            parts.append(rendered)
        body.append(f'<div class="nb-cell">{"".join(parts)}</div>')
    return '\n'.join(body), toc, figure


def page(body, toc, figures):
    nav = ''.join(f'<a href="{href}"{" aria-current=\"page\"" if label == "Analysis" else ""}>{label}</a>' for href, label in NAV)
    contents = ''.join(f'<li class="toc-{level}"><a href="#{anchor}">{html.escape(title)}</a></li>' for level, title, anchor in toc)
    return f'''<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="GeoCrashAI research notebook: data quality, exploratory data analysis, classification, regression, time series and clustering on the US Accidents dataset.">
<title>Analysis · GeoCrash</title><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/assets/app.css"><link rel="stylesheet" href="/assets/notebook.css"></head>
<body>
<a class="skip" href="#notebook">Skip to the notebook</a>
<header class="site-head"><a class="brand" href="/">GeoCrash</a><nav aria-label="Main navigation">{nav}</nav></header>
<main>
<section class="intro" aria-labelledby="page-title"><div><p class="nb-kicker">CSCE 878 · RESEARCH ANALYSIS</p><h1 id="page-title">The complete analysis notebook</h1>
<p>Every step from raw data to models, with its output: data quality, exploratory analysis, classification, regression, time series and clustering.</p>
<div class="nb-actions"><a class="button" href="#exploratory-data-analysis">Jump to the EDA</a><a class="button secondary" href="/assets/{NOTEBOOK.name}" download>Download .ipynb</a></div></div>
<div class="dataset-caption"><strong>US Accidents · 2016–2023</strong><span>7.7M recorded crashes, 49 states</span><span>{figures} figures · rendered from the saved outputs</span></div></section>
<p class="nb-scope" role="note"><strong>Different dataset from the map.</strong> This notebook studies the US Accidents dataset (Moosavi et al., <a href="https://www.kaggle.com/datasets/sobhanmoosavi/us-accidents">CC BY-NC-SA 4.0</a>, noncommercial), where severity 1–4 means traffic impact. The map, data explorer and road screening use NHTSA FARS fatal-crash records.</p>
<div class="nb-layout"><nav class="nb-toc" aria-label="Notebook contents"><p>Contents</p><ol>{contents}</ol></nav>
<article id="notebook" class="nb-article">{body}</article></div>
</main>
<footer class="nb-footer"><a class="brand" href="/">GeoCrash</a><a href="/docs">API docs</a><p>Research notebook rendered from <a href="/assets/{NOTEBOOK.name}" download>{NOTEBOOK.name}</a>. Code cells are collapsed; open any “Code” row to read it.</p></footer>
</body></html>
'''


def main():
    cells = json.loads(NOTEBOOK.read_text())['cells']
    shutil.rmtree(FIGURES, ignore_errors=True)
    FIGURES.mkdir(parents=True)
    body, toc, figures = render(cells)
    PAGE.write_text(page(body, toc, figures))
    shutil.copyfile(NOTEBOOK, DOWNLOAD)
    anchors = {anchor for _, _, anchor in toc}
    assert 'exploratory-data-analysis' in anchors, 'site nav links to the EDA anchor'
    assert figures == len(list(FIGURES.glob('*.png'))) and figures > 0
    print(f'{PAGE.relative_to(ROOT)}: {len(toc)} headings, {figures} figures')


if __name__ == '__main__':
    main()
