#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 819 食谱 Markdown 转换为 RFC / ISO / IETF 风格 PDF。

用法：
    python3 RFC风格PDF生成脚本.py 819食谱.md -o 819食谱-RFC定稿.pdf

默认从 Markdown 所在目录解析图片；如图片集中存放，可使用：
    python3 RFC风格PDF生成脚本.py 819食谱.md -o out.pdf --asset-dir ./images

依赖：Python 3、Pandoc、Node.js、Playwright/Chromium，以及本环境中的
kimi-pdf HTML 转换器。脚本不改动源 Markdown，只在内存中做排版投影。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

# 默认使用 converter/ 子目录下的 html_to_pdf.js（感谢 kimi）。
# 该目录还应包含其依赖的 browser_helper.js、paged.polyfill.js 与 package.json。
DEFAULT_CONVERTER = Path(__file__).resolve().parent / "converter" / "html_to_pdf.js"

CSS_TEMPLATE = r"""
@page {
    size: A4;
    margin: 25.4mm 22mm 20mm 22mm;
    @top-left {
        content: __HEADER_LEFT__;
        font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
        font-size: 8pt;
        color: #777;
        border-bottom: 0.75pt solid #aaa;
        padding-bottom: 5pt;
        vertical-align: bottom;
    }
    @top-right {
        content: __HEADER_RIGHT__;
        font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
        font-size: 8pt;
        color: #777;
        text-align: right;
        border-bottom: 0.75pt solid #aaa;
        padding-bottom: 5pt;
        vertical-align: bottom;
    }
    @bottom-left {
        content: "[Page " counter(page) "]";
        font-family: "DejaVu Sans Mono", monospace;
        font-size: 8.5pt;
        color: #777;
    }
}

@page cover {
    margin: 0;
    @top-left { content: none; border: none; }
    @top-right { content: none; border: none; }
    @bottom-left { content: none; }
}

html, body {
    margin: 0;
    padding: 0;
    background: white;
}

body {
    font-family: "Noto Serif", "Noto Serif CJK SC", "Noto Color Emoji", serif;
    font-size: 10.5pt;
    line-height: 1.68;
    color: #111;
    text-align: justify;
    text-align-last: left;
    font-variant-ligatures: common-ligatures;
}

/* ---------- RFC cover ---------- */
.cover {
    page: cover;
    width: 210mm;
    height: 297mm;
    box-sizing: border-box;
    padding: 23.6mm 22mm 20mm 22mm;
    overflow: hidden;
    page-break-after: always;
    background: white;
}

.rfc-head {
    display: grid;
    grid-template-columns: 56% 44%;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 9pt;
    line-height: 1.85;
    color: #111;
    text-align: left;
}

.rfc-head .right {
    padding-left: 0;
}

.head-rule {
    border-top: 0.85pt solid #333;
    margin-top: 5pt;
}

.cover-title {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-size: 17pt;
    line-height: 1.38;
    font-weight: 700;
    margin: 45pt 0 18pt 0;
    width: 70%;
    text-align: left;
    color: #111;
}

.cover-subtitle {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-size: 12.5pt;
    letter-spacing: 0.42em;
    margin: 0 0 31.5pt 0;
    color: #111;
    text-align: left;
}

.cover-meta {
    width: 78%;
    margin: 0 auto 44pt auto;
    border-collapse: collapse;
    border-top: 0.85pt solid #333;
    border-bottom: 0.85pt solid #333;
    font-size: 9.5pt;
    line-height: 1.42;
}

.cover-meta td {
    padding: 4.5pt 0 4.8pt 0;
    vertical-align: top;
}

.cover-meta td:first-child {
    width: 35%;
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-weight: 700;
}

.cover-meta td:last-child {
    font-family: "Noto Serif", "Noto Serif CJK SC", serif;
}

.cover blockquote.preface {
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
}

.cover blockquote.preface p {
    margin: 0 0 10.5pt 0;
}

.cover blockquote.preface p.opening-quote {
    width: 82%;
    margin: 0 auto 9pt auto;
    font-size: 11.5pt;
    line-height: 1.45;
    text-align: left;
    text-align-last: left;
}

.cover blockquote.preface p.quote-source {
    width: 82%;
    margin: 0 auto 35pt auto;
    font-size: 10pt;
    line-height: 1.45;
    text-align: left;
}

/* ---------- TOC ---------- */
.toc-page {
    page-break-after: always;
}

.toc-title {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-size: 14pt;
    font-weight: 700;
    line-height: 1.3;
    margin: 0 0 17pt 0;
    padding-bottom: 8pt;
    border-bottom: 0.85pt solid #333;
    text-align: left;
}

.toc-item {
    margin: 0 0 5.5pt 0;
    line-height: 1.5;
    page-break-inside: avoid;
}

.toc-item a {
    display: block;
    color: #111;
    text-decoration: none;
}

.toc-item a::after {
    content: target-counter(attr(href url), page);
    float: right;
    margin-left: 12pt;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 10pt;
    color: #111;
}

.toc-item.level1 {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-size: 10.5pt;
    font-weight: 700;
    margin-top: 8pt;
}

.toc-item.level2 {
    font-family: "Noto Serif", "Noto Serif CJK SC", serif;
    font-size: 10pt;
    margin-left: 22pt;
}

.toc-item .secno {
    margin-right: 0.55em;
}

/* ---------- Body headings ---------- */
.document-body h2,
.document-body h3 {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    color: #111;
    text-align: left;
    page-break-after: avoid;
}

.document-body h2 {
    font-size: 14pt;
    line-height: 1.35;
    margin: 20pt 0 13pt 0;
    padding-bottom: 7pt;
    border-bottom: 0.85pt solid #333;
}

.document-body h2:first-child {
    margin-top: 20pt;
}

.document-body h3 {
    font-size: 11.5pt;
    line-height: 1.35;
    margin: 20pt 0 6pt 0;
}

.heading-table-block {
    page-break-inside: avoid;
}

.secno {
    font-weight: inherit;
}

/* ---------- Body text ---------- */
.document-body p {
    margin: 0 0 7pt 0;
    orphans: 2;
    widows: 2;
}

.document-body strong,
.document-body b {
    font-family: "Noto Serif", "Noto Serif CJK SC", serif;
    font-weight: 700;
}

.document-body a {
    color: #111;
    text-decoration: underline;
    word-break: break-word;
}

.document-body del {
    color: #666;
    text-decoration-thickness: 0.55pt;
}

.document-body ul,
.document-body ol {
    margin: 5pt 0 9pt 0;
    padding-left: 22pt;
}

.document-body li {
    margin: 0 0 4.2pt 0;
    padding-left: 1pt;
}

.document-body li::marker {
    font-family: "Noto Serif", "Noto Serif CJK SC", serif;
}

/* ---------- Tables ---------- */
.table-caption {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-size: 9.5pt;
    font-weight: 700;
    margin: 6pt 0 5pt 0;
    text-align: left;
    page-break-after: avoid;
}

.document-body table {
    width: 100%;
    max-width: 100%;
    border-collapse: collapse;
    margin: 0 0 15pt 0;
    font-size: 9.8pt;
    line-height: 1.48;
    table-layout: fixed;
    page-break-inside: avoid;
}

.document-body thead {
    display: table-header-group;
}

.document-body th {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-size: 9pt;
    font-weight: 700;
    background: #efefef;
    border: 0.75pt solid #999;
    border-bottom: 1pt solid #333;
    padding: 5pt 8pt;
    text-align: left;
}

.document-body td {
    border: 0.75pt solid #999;
    padding: 5pt 8pt;
    vertical-align: top;
    text-align: left;
    overflow-wrap: anywhere;
}

.document-body tr {
    page-break-inside: avoid;
}

/* ---------- Blockquote cards and notes ---------- */
.document-body blockquote {
    margin: 10pt 0 13pt 0;
    padding: 9pt 14pt 10pt 14pt;
    border: 0.75pt solid #888;
    background: white;
    page-break-inside: avoid;
}

.document-body blockquote p {
    margin: 0 0 6.5pt 0;
}

.document-body blockquote p:last-child {
    margin-bottom: 0;
}

.document-body blockquote.recommendation {
    border: 0.75pt solid #888;
    background: white;
}

.document-body blockquote.recommendation p:first-child strong {
    font-family: "Noto Sans CJK SC", "Liberation Sans", sans-serif;
}

.document-body blockquote.attribution {
    margin: 0 0 12pt 0;
    padding: 0;
    border: none;
    background: transparent;
    font-size: 9.5pt;
    font-style: italic;
    page-break-inside: avoid;
}

.document-body blockquote.attribution p {
    margin: 0;
}

.document-body blockquote.takeaway {
    border: none;
    border-left: 2.5pt solid #333;
    background: #f3f3f3;
    padding: 9pt 14pt 10pt 15pt;
}

.document-body blockquote.takeaway p:first-child {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-weight: 700;
}

.document-body blockquote.takeaway em {
    font-style: italic;
}

.document-body blockquote.guideline {
    border: 0.75pt solid #888;
    border-left: 2.5pt solid #333;
    background: white;
}

.document-body blockquote.guideline p:first-child {
    font-family: "Liberation Sans", "Noto Sans CJK SC", sans-serif;
    font-weight: 700;
}

/* ---------- Figures ---------- */
.document-body figure {
    margin: 10pt 0 11pt 0;
    padding: 0;
    page-break-inside: avoid;
    max-width: 100%;
}

.image-frame {
    box-sizing: border-box;
    width: 100%;
    min-height: 45pt;
    padding: 8pt;
    border: 0.8pt dashed #aaa;
    background: white;
    text-align: center;
}

.image-frame img {
    display: block;
    max-width: 82%;
    height: auto;
    margin: 0 auto;
}

.figure-caption,
.document-body p.figure-caption {
    margin-top: -5pt;
    font-size: 9pt;
    color: #333;
    text-align: left;
}

/* ---------- Miscellaneous ---------- */
pre, code, table, figure, img, svg, blockquote {
    max-width: 100%;
    box-sizing: border-box;
}

pre {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    background: #f5f5f5;
    padding: 7pt 9pt;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 8.5pt;
    line-height: 1.45;
}

code {
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 0.92em;
}

hr {
    border: none;
    border-top: 0.75pt solid #999;
    margin: 14pt 0;
}
"""


def css_quote(value: str) -> str:
    """Return a safe CSS string literal."""
    return json.dumps(value, ensure_ascii=False)


def strip_markdown_inline(text: str) -> str:
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    return text.strip()


def path_to_file_uri(path: Path) -> str:
    return "file://" + quote(str(path.resolve()))


def resolve_asset(name: str, asset_dir: Path) -> Optional[Path]:
    name = name.strip()
    if not name:
        return None
    parsed = urlparse(name)
    if parsed.scheme in {"http", "https", "file", "data"}:
        return None
    candidate = Path(name)
    if not candidate.is_absolute():
        candidate = asset_dir / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    return resolved if resolved.exists() else None


def replace_obsidian_images(markdown_text: str, asset_dir: Path, warnings: List[str]) -> str:
    """Convert Obsidian embeds to HTML figures, preserving missing embeds as text."""

    pattern = re.compile(r"!\[\[([^\]\n]+)\]\]")

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        parts = [p.strip() for p in raw.split("|")]
        filename = parts[0]
        width = None
        if len(parts) > 1:
            width_match = re.search(r"\d+", parts[1])
            if width_match:
                width = width_match.group(0)

        resolved = resolve_asset(filename, asset_dir)
        if resolved is None:
            warnings.append(f"图片未找到，已保留原始引用：![[{raw}]]")
            return html.escape(match.group(0))

        style = f'width: {width}px;' if width else ""
        return (
            '\n\n<figure class="source-figure">'
            '<div class="image-frame">'
            f'<img src="{path_to_file_uri(resolved)}" alt="{html.escape(filename)}" style="{style}" />'
            "</div>"
            "</figure>\n\n"
        )

    return pattern.sub(repl, markdown_text)


def extract_cover(markdown_text: str) -> Tuple[Dict[str, str], str, str]:
    """Extract title, metadata, and leading blockquote without changing their text."""
    lines = markdown_text.splitlines()
    meta: Dict[str, str] = {
        "title": "A Handbook for The Deadline-Driven and Dying of Hunger",
        "subtitle": "Food Guide",
        "Version": "1.0.0",
        "Date": "",
        "Maintainers": "XueHai 819ers",
        "Status": "Open for Contributions",
        "Request": "819",
        "Category": "Informational",
        "Organization": "WHUT Xuehai Building",
    }

    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1

    if i < len(lines):
        title_match = re.match(r"^##\s+\*\*(.*?)\*\*\s*$", lines[i])
        if title_match:
            meta["title"] = strip_markdown_inline(title_match.group(1))
            i += 1

    # The source separates title and metadata with a blank line.
    while i < len(lines) and not lines[i].strip():
        i += 1

    # Read contiguous front-matter-like lines up to the first blank line.
    while i < len(lines) and lines[i].strip():
        line = lines[i].strip()
        key_value = re.match(r"^(Version|Date|Maintainers|Status)\s*:\s*(.*)$", line)
        if key_value:
            meta[key_value.group(1)] = key_value.group(2).strip()
        elif not line.startswith(">"):
            meta["subtitle"] = line
        i += 1

    while i < len(lines) and not lines[i].strip():
        i += 1

    preface_lines: List[str] = []
    if i < len(lines) and lines[i].lstrip().startswith(">"):
        while i < len(lines):
            line = lines[i]
            if line.lstrip().startswith(">"):
                preface_lines.append(line)
                i += 1
            elif not line.strip():
                # A plain blank line terminates the cover preface.
                break
            else:
                break

    body = "\n".join(lines[i:]).lstrip("\n")
    preface = "\n".join(preface_lines)
    return meta, preface, body


def group_guideline_blockquote(markdown_text: str) -> str:
    """Keep the '如何写一条 Qualified 的推荐' guidance visually inside one card."""
    lines = markdown_text.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if line.lstrip().startswith(">") and "如何写一条" in line and "Qualified" in line:
            i += 1
            while i < len(lines) and lines[i].strip() and re.match(r"^\s{2,}\S", lines[i]):
                out.append("> " + lines[i].strip())
                i += 1
            continue
        i += 1
    return "\n".join(out)


def normalize_headings(markdown_text: str) -> str:
    """Map document-specific Markdown conventions to h2/h3 while retaining text."""
    lines = markdown_text.splitlines()
    out: List[str] = []
    current_top = ""

    def next_nonblank(index: int) -> str:
        for j in range(index + 1, len(lines)):
            if lines[j].strip():
                return lines[j].strip()
        return ""

    def append_heading(level: int, text: str) -> None:
        # Pandoc's hard-line-break mode needs an explicit blank line when a
        # heading follows a caption/paragraph without one in the source.
        if out and out[-1].strip():
            out.append("")
        out.append("#" * level + " " + text)

    for index, line in enumerate(lines):
        stripped = line.strip()

        h4 = re.match(r"^####\s+(.+?)\s*$", stripped)
        h5 = re.match(r"^#####\s+(.+?)\s*$", stripped)
        bold_only = re.match(r"^\*\*([^*]+)\*\*\s*$", stripped)

        if h4:
            text = h4.group(1)
            plain = strip_markdown_inline(text)
            if current_top == "推荐 Recommendations" and plain == "推荐列表":
                append_heading(3, text)
            else:
                current_top = plain
                append_heading(2, text)
            continue

        if h5:
            append_heading(3, h5.group(1))
            continue

        if bold_only:
            text = bold_only.group(1).strip()
            nxt = next_nonblank(index)
            promote = (
                text.startswith("Example")
                or nxt.startswith("|")
                or current_top.startswith("Food Integrity")
            )
            if promote:
                append_heading(3, text)
                continue

        out.append(line)

    return "\n".join(out)


def run_pandoc(markdown_text: str) -> str:
    cmd = [
        "pandoc",
        "-f",
        "markdown+smart+hard_line_breaks",
        "-t",
        "html5",
        "--wrap=none",
    ]
    proc = subprocess.run(
        cmd,
        input=markdown_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Pandoc 转换失败：\n{proc.stderr}")
    return proc.stdout


def next_element(tag: Tag) -> Optional[Tag]:
    node = tag.next_sibling
    while node is not None:
        if isinstance(node, Tag):
            return node
        if isinstance(node, NavigableString) and str(node).strip():
            return None
        node = node.next_sibling
    return None


def postprocess_body(body_html: str, asset_dir: Path) -> Tuple[str, str]:
    soup = BeautifulSoup(f'<div id="markdown-root">{body_html}</div>', "lxml")
    root = soup.find("div", id="markdown-root")
    if root is None:
        raise RuntimeError("Markdown HTML 后处理失败")

    # Resolve ordinary relative Markdown images against the asset directory.
    for img in root.find_all("img"):
        src = img.get("src", "")
        if not src or urlparse(src).scheme in {"http", "https", "file", "data"}:
            continue
        resolved = resolve_asset(src, asset_dir)
        if resolved is not None:
            img["src"] = path_to_file_uri(resolved)

    # Number sections and collect TOC entries before heading content is changed.
    toc_items: List[Tuple[int, str, str]] = []
    top_no = 0
    sub_no = 0
    table_no = 0

    for heading in list(root.find_all(["h2", "h3"])):
        original_inner = heading.decode_contents()
        original_text = heading.get_text(" ", strip=True)

        if heading.name == "h2":
            top_no += 1
            sub_no = 0
            number = f"{top_no}."
            anchor = f"sec-{top_no}"
            level = 1
        else:
            sub_no += 1
            number = f"{top_no}.{sub_no}"
            anchor = f"sec-{top_no}-{sub_no}"
            level = 2

        heading["id"] = anchor
        number_span = soup.new_tag("span", attrs={"class": "secno"})
        number_span.string = number
        heading.insert(0, number_span)
        heading.insert(1, " ")
        toc_label_inner = re.sub(r"</?(?:strong|b)>", "", original_inner)
        toc_label = f'<span class="secno">{number}</span> {toc_label_inner}'
        toc_items.append((level, anchor, toc_label))

        sibling = next_element(heading)
        if heading.name == "h3" and sibling is not None and sibling.name == "table":
            table_no += 1
            caption = soup.new_tag("div", attrs={"class": "table-caption"})
            caption.string = f"Table {table_no} — {original_text}"
            sibling.insert_before(caption)

            # Keep a small subsection heading, its caption, and its table as
            # one atomic RFC-style block, avoiding an orphaned heading at a
            # page bottom. Very large tables remain paginable.
            if len(sibling.find_all("tr")) <= 10:
                block = soup.new_tag("div", attrs={"class": "heading-table-block"})
                heading.insert_before(block)
                block.append(heading.extract())
                block.append(caption.extract())
                block.append(sibling.extract())

    # Table defaults.
    for table in root.find_all("table"):
        table["class"] = (table.get("class") or []) + ["data-table"]

    # Classify blockquotes for RFC-style cards.
    for quote_tag in root.find_all("blockquote"):
        text = quote_tag.get_text(" ", strip=True)
        classes = quote_tag.get("class") or []
        if text.startswith("Takeaway:"):
            classes.append("takeaway")
        elif text.startswith("Adapted from:"):
            classes.append("attribution")
        elif "如何写一条" in text and "Qualified" in text:
            classes.append("guideline")
        elif re.match(r"^No\.", text):
            classes.append("recommendation")
        else:
            classes.append("note")
        quote_tag["class"] = classes

    # Treat a short parenthesized paragraph immediately after a figure as a caption.
    for figure in root.find_all("figure"):
        sibling = next_element(figure)
        if sibling is not None and sibling.name == "p":
            text = sibling.get_text(" ", strip=True)
            if text.startswith("（") and len(text) <= 80:
                sibling["class"] = (sibling.get("class") or []) + ["figure-caption"]

    toc_html_parts: List[str] = []
    for level, anchor, label in toc_items:
        toc_html_parts.append(
            f'<div class="toc-item level{level}">'
            f'<a href="#{anchor}">{label}</a>'
            "</div>"
        )

    return str(root), "\n".join(toc_html_parts)


def build_preface(preface_md: str) -> str:
    if not preface_md.strip():
        return ""
    # Separate quote attribution and the following Chinese preface onto distinct
    # visual paragraphs, as in the reference cover.
    preface_md = re.sub(
        r"\n>\s*——\s*([^\n]+)\n>",
        r"\n>\n> —— \1\n>\n>",
        preface_md,
    )
    preface_html = run_pandoc(preface_md)
    soup = BeautifulSoup(preface_html, "lxml")
    quote_tag = soup.find("blockquote")
    if quote_tag is None:
        return preface_html
    quote_tag["class"] = ["preface"]
    paragraphs = quote_tag.find_all("p")
    if paragraphs:
        paragraphs[0]["class"] = (paragraphs[0].get("class") or []) + ["opening-quote"]
    if len(paragraphs) > 1 and "M.F.K. Fisher" in paragraphs[1].get_text():
        paragraphs[1]["class"] = (paragraphs[1].get("class") or []) + ["quote-source"]
    return str(quote_tag)


def month_year(date_text: str) -> str:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").strftime("%B %Y")
    except ValueError:
        return date_text or "October 2026"


def build_cover(meta: Dict[str, str], preface_html: str) -> str:
    rows = [
        ("Version:", meta.get("Version", "")),
        ("Date:", meta.get("Date", "")),
        ("Maintainers:", meta.get("Maintainers", "")),
        ("Status:", meta.get("Status", "")),
    ]
    row_html = "\n".join(
        f"<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>"
        for label, value in rows
    )
    return f"""
<div class="cover">
    <div class="rfc-head">
        <div class="left">
            {html.escape(meta.get('Maintainers', 'XueHai 819ers'))}<br />
            Request for Comments: {html.escape(meta.get('Request', '819'))}<br />
            Category: {html.escape(meta.get('Category', 'Informational'))}
        </div>
        <div class="right">
            {html.escape(meta.get('Organization', 'WHUT Xuehai Building'))}<br />
            {html.escape(month_year(meta.get('Date', '')))}
        </div>
    </div>
    <div class="head-rule"></div>
    <h1 class="cover-title">{html.escape(meta.get('title', ''))}</h1>
    <div class="cover-subtitle">{html.escape(meta.get('subtitle', ''))}</div>
    <table class="cover-meta">
        <tbody>
            {row_html}
        </tbody>
    </table>
    {preface_html}
</div>
"""


def build_full_html(meta: Dict[str, str], body_html: str, toc_html: str, preface_html: str) -> str:
    header_left = meta.get("subtitle", "Food Guide")
    header_right = f"Version {meta.get('Version', '')}".strip()
    css = CSS_TEMPLATE.replace("__HEADER_LEFT__", css_quote(header_left))
    css = css.replace("__HEADER_RIGHT__", css_quote(header_right))
    cover = build_cover(meta, preface_html)
    title = f"{meta.get('subtitle', 'Food Guide')} — {meta.get('title', '')}"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<style>
{css}
</style>
</head>
<body>
{cover}
<section class="toc-page">
    <h1 class="toc-title">Table of Contents</h1>
    <nav class="toc">
{toc_html}
    </nav>
</section>
<main class="document-body">
{body_html}
</main>
</body>
</html>
"""


def convert_html_to_pdf(html_path: Path, pdf_path: Path, converter: Path) -> None:
    if not converter.exists():
        raise FileNotFoundError(
            f"未找到 HTML→PDF 转换器：{converter}\n"
            "请使用 --converter 指定 html_to_pdf.js。"
        )
    cmd = ["node", str(converter), str(html_path), "--output", str(pdf_path)]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        raise RuntimeError(f"HTML→PDF 转换失败，退出码 {proc.returncode}")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 819 食谱 Markdown 转换为固定 RFC 风格 PDF。"
    )
    parser.add_argument("input", type=Path, help="输入 Markdown 文件")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出 PDF；默认：<输入名>-RFC风格.pdf",
    )
    parser.add_argument(
        "--asset-dir",
        type=Path,
        help="图片资源目录；默认为 Markdown 所在目录",
    )
    parser.add_argument(
        "--converter",
        type=Path,
        default=DEFAULT_CONVERTER,
        help="html_to_pdf.js 路径；默认为脚本同目录下的 html_to_pdf.js",
    )
    parser.add_argument(
        "--keep-html",
        action="store_true",
        help="同时保留中间 HTML，便于调试版式",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"错误：输入文件不存在：{input_path}", file=sys.stderr)
        return 2

    output_path = args.output.expanduser().resolve() if args.output else input_path.with_name(
        f"{input_path.stem}-RFC风格.pdf"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    asset_dir = (args.asset_dir.expanduser().resolve() if args.asset_dir else input_path.parent)
    warnings: List[str] = []

    source = input_path.read_text(encoding="utf-8")
    meta, preface_md, body_md = extract_cover(source)

    body_md = group_guideline_blockquote(body_md)
    body_md = replace_obsidian_images(body_md, asset_dir, warnings)
    body_md = normalize_headings(body_md)

    body_html_raw = run_pandoc(body_md)
    body_html, toc_html = postprocess_body(body_html_raw, asset_dir)
    preface_html = build_preface(preface_md)
    full_html = build_full_html(meta, body_html, toc_html, preface_html)

    if args.keep_html:
        html_path = output_path.with_suffix(".html")
        html_path.write_text(full_html, encoding="utf-8")
        cleanup_html = False
    else:
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".html",
            prefix="rfc-food-guide-",
            dir=str(output_path.parent),
            delete=False,
        )
        with tmp:
            tmp.write(full_html)
        html_path = Path(tmp.name)
        cleanup_html = True

    try:
        convert_html_to_pdf(html_path, output_path, args.converter.expanduser().resolve())
    finally:
        if cleanup_html:
            try:
                html_path.unlink()
            except FileNotFoundError:
                pass

    for warning in warnings:
        print(f"警告：{warning}", file=sys.stderr)
    print(f"PDF 已生成：{output_path}")
    if args.keep_html:
        print(f"中间 HTML：{html_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)

