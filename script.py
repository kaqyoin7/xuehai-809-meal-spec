#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
809 食谱指南构建器：guide.toml + content/*.md → RFC 风格 PDF。

管理方式参考 819-food-guide 项目（toml + 分目录 + 指令），渲染风格
沿用本项目原 script.py 的 CSS / 封面 / 目录 / 正文管线。

用法：
    python3 script.py                   构建 PDF（默认输出 food-guide-v<version>.pdf）
    python3 script.py --keep-html       同时保留中间 HTML
    python3 script.py -o out.pdf        指定输出路径
    python3 script.py new "店名"         在 entries/ 新建一条推荐

依赖：Python 3.11+（或 tomli）、Pandoc、Node.js、Playwright/Chromium，
以及 converter/ 子目录下的 html_to_pdf.js。
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

try:
    import tomllib
except ModuleNotFoundError:          # Python < 3.11
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        sys.exit("需要 Python 3.11+ 或安装 tomli：pip install tomli")

ROOT = Path(__file__).resolve().parent
DEFAULT_CONVERTER = ROOT / "converter" / "html_to_pdf.js"
FIGURES_DIR = ROOT / "figures"
ASSETS_DIR = ROOT / "assets"
CONTENT_DIR = ROOT / "content"
ENTRIES_DIR = ROOT / "entries"
EXAMPLES_DIR = ROOT / "examples"

# ============================================================================= CSS
# 与原 script.py 完全一致——渲染风格的生命线。
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


# ============================================================================= helpers
def css_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def strip_markdown_inline(text: str) -> str:
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    return text.strip()


def path_to_file_uri(path: Path) -> str:
    return "file://" + quote(str(path.resolve()))


def resolve_asset(name: str, *dirs: Path) -> Optional[Path]:
    name = name.strip()
    if not name:
        return None
    parsed = urlparse(name)
    if parsed.scheme in {"http", "https", "file", "data"}:
        return None
    candidate = Path(name)
    if not candidate.is_absolute():
        for d in dirs:
            if d is not None:
                resolved = (d / name).resolve()
                if resolved.exists():
                    return resolved
    else:
        try:
            resolved = candidate.resolve()
            if resolved.exists():
                return resolved
        except OSError:
            pass
    return None


# ============================================================================= toml + front matter
def load_meta() -> Dict[str, str]:
    with open(ROOT / "guide.toml", "rb") as f:
        data = tomllib.load(f)
    meta: Dict[str, str] = {
        "title": "<br>".join(data.get("title_lines", [])),
        "subtitle": data.get("subtitle", ""),
        "Version": data.get("version", ""),
        "Date": data.get("date", ""),
        "Maintainers": data.get("maintainers", ""),
        "Status": data.get("status", ""),
        "Request": data.get("rfc_number", ""),
        "Category": data.get("category", ""),
        "Organization": data.get("location", ""),
        "authors": data.get("authors", ""),
        "month_year": data.get("month_year", ""),
        "quote": data.get("quote", ""),
        "quote_author": data.get("quote_author", ""),
    }
    return meta


def read_front_matter(path: Path) -> Tuple[Dict[str, str], str]:
    """Parse simple YAML-like front matter (key: value lines between --- ... ---)."""
    text = path.read_text(encoding="utf-8")
    meta: Dict[str, str] = {}
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            head, body = text[4:end], text[end + 4:].lstrip("\n")
            for line in head.splitlines():
                s = line.strip()
                if not s or s.startswith("#") or ":" not in s:
                    continue
                k, v = s.split(":", 1)
                v = re.sub(r"\s+#.*$", "", v).strip()
                if v:
                    meta[k.strip()] = v
    return meta, body


# ============================================================================= directive expansion + card rendering
def figure_html_tag(name: str, width: str, caption: str, fig_no: int) -> str:
    """Render a figure as raw HTML (Pandoc passes it through)."""
    resolved = resolve_asset(name, FIGURES_DIR, ASSETS_DIR)
    if resolved is None:
        return f"<!-- 图片未找到：{name} -->"
    src = path_to_file_uri(resolved)
    style = f"width:{width};" if width else ""
    cap = f'<p class="figure-caption">Figure {fig_no} — {html.escape(caption, quote=False)}</p>' if caption else ""
    return (
        f'<figure class="source-figure">'
        f'<div class="image-frame">'
        f'<img src="{src}" alt="{html.escape(name)}" style="{style}" />'
        f"</div>"
        f"</figure>"
        f"\n{cap}"
    )


def card_markdown(fm: Dict[str, str], body: str, show_no: bool = True) -> str:
    """Render an example/entry card as Markdown blockquote (matches 809.md style)."""
    head: List[str] = []
    if fm.get("no") and show_no:
        head.append("No.%s" % fm["no"])
    for k in ("name", "type", "where"):
        if fm.get(k):
            head.append(fm[k])
    lines: List[str] = []
    if head:
        lines.append("> **%s**" % "　".join(head))
    for line in body.splitlines():
        if line.strip():
            lines.append("> %s" % line.strip())
    if fm.get("by"):
        who = "推荐人：%s" % fm["by"]
        if fm.get("date"):
            who += "　%s" % fm["date"]
        lines.append("> %s" % who)
    if fm.get("status") == "retired":
        lines.append("> 状态：已停止推荐（%s）" % fm.get("retired_note", ""))
    return "\n".join(lines)


def card_with_figure_markdown(fm: Dict[str, str], body: str, show_no: bool, fig_no: int) -> str:
    card = card_markdown(fm, body, show_no)
    parts = [card]
    if fm.get("figure"):
        parts.append("")
        parts.append(figure_html_tag(
            fm["figure"],
            fm.get("figure_width", ""),
            fm.get("figure_caption", ""),
            fig_no,
        ))
    return "\n".join(parts)


def examples_markdown(fig_counter: List[int]) -> str:
    parts: List[str] = []
    show_no = True  # guide.toml 的 show_example_numbers 默认 true
    for p in sorted(EXAMPLES_DIR.glob("*.md")):
        if p.name.startswith("_"):
            continue
        fm, body = read_front_matter(p)
        parts.append("\n### %s\n" % fm.get("heading", p.stem))
        fig_counter[0] += 1
        parts.append(card_with_figure_markdown(fm, body, show_no, fig_counter[0]))
    return "\n".join(parts)


def entries_markdown(fig_counter: List[int]) -> str:
    parts: List[str] = ["\n### 推荐列表\n"]
    files = [p for p in ENTRIES_DIR.glob("*.md") if not p.name.startswith("_")]

    def key(p):
        fm, _ = read_front_matter(p)
        return (int(fm["no"]) if fm.get("no", "").isdigit() else 10 ** 9, p.name)

    files.sort(key=key)
    if not files:
        parts.append("\n【新的推荐从这里开始，按编号往后追加。】\n")
    for p in files:
        fm, body = read_front_matter(p)
        fig_counter[0] += 1
        parts.append(card_with_figure_markdown(fm, body, True, fig_counter[0]))
    return "\n".join(parts)


def expand_directives(text: str, fig_counter: List[int]) -> str:
    """Expand @examples / @entries / @pagebreak / @split / Table: / Figure:."""
    out: List[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if s == "@split":
            out.append("")  # soft break hint; our CSS handles keep-together
        elif s == "@pagebreak":
            out.append('\n<div style="page-break-after: always;"></div>\n')
        elif s == "@examples":
            out.append(examples_markdown(fig_counter))
        elif s == "@entries":
            out.append(entries_markdown(fig_counter))
        elif s.startswith("Table:"):
            # Strip — let postprocess_body auto-caption h3+table pairs.
            pass
        elif s.startswith("Figure:"):
            parts = [x.strip() for x in s[7:].split("|")]
            name = parts[0] if len(parts) > 0 else ""
            width = parts[1] if len(parts) > 1 else ""
            cap = parts[2] if len(parts) > 2 else ""
            fig_counter[0] += 1
            out.append("\n" + figure_html_tag(name, width, cap, fig_counter[0]) + "\n")
        else:
            out.append(line)
    return "\n".join(out)


# ============================================================================= Markdown preprocessing
def demote_headings(text: str) -> str:
    """content/*.md uses # / ##; demote to ## / ### to match the rendering pipeline."""
    lines = text.splitlines()
    out: List[str] = []
    for line in lines:
        # Match heading lines, possibly with trailing {: .attr }
        m = re.match(r"^(#{1,2})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            rest = m.group(2)
            out.append("#" * (level + 1) + " " + rest)
        else:
            out.append(line)
    return "\n".join(out)


def replace_obsidian_images(markdown_text: str, warnings: List[str]) -> str:
    """Convert ![[file]] embeds to HTML figures."""
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
        resolved = resolve_asset(filename, FIGURES_DIR, ASSETS_DIR)
        if resolved is None:
            warnings.append(f"图片未找到，已保留原始引用：![[{raw}]]")
            return html.escape(match.group(0))
        style = f"width: {width}px;" if width else ""
        return (
            '\n\n<figure class="source-figure">'
            '<div class="image-frame">'
            f'<img src="{path_to_file_uri(resolved)}" alt="{html.escape(filename)}" style="{style}" />'
            "</div>"
            "</figure>\n\n"
        )

    return pattern.sub(repl, markdown_text)


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


# ============================================================================= Pandoc
def preprocess_attr_blocks(markdown_text: str) -> str:
    """Convert Pandoc-style `{: .class }` attribute blocks into raw HTML.

    Pandoc 3.6.4's `markdown` format doesn't enable `attr_list`, so we
    preprocess:
      - Heading lines trailing `{: .nonum }` → compact `{#auto-N .nonum}`
        syntax that Pandoc's `header_attributes` (on by default) understands.
      - Standalone `{: .class }` lines attach class to the previous paragraph:
        the paragraph becomes <p class="class">...</p> (raw HTML, kept).
    """
    counter = [0]

    # Heading attribute: `# Title {: .nonum }` → `# Title {#auto-N .nonum}`
    def repl_heading(match: re.Match[str]) -> str:
        counter[0] += 1
        return f'{match.group(1)} {{#auto-{counter[0]} .{match.group(2)}}}'

    markdown_text = re.sub(
        r"^(#{1,2}\s+.+?)\s*\{: *\.([a-zA-Z0-9_-]+)\s*\}\s*$",
        repl_heading,
        markdown_text,
        flags=re.MULTILINE,
    )

    # Standalone `{: .class }` line attaches to the previous paragraph:
    # wrap the previous line (single-line paragraph) with <p class="class">.
    def repl_block(match: re.Match[str]) -> str:
        para = match.group("para").strip()
        cls = match.group(2)
        if para.startswith("<") and para.endswith(">"):
            return re.sub(
                r"^<([a-zA-Z][a-zA-Z0-9]*)",
                rf'<\1 class="{cls}"',
                para,
                count=1,
            )
        return f'<p class="{cls}">{para}</p>'

    markdown_text = re.sub(
        r"^(?P<para>[^\n>].*?)\n\{: *\.([a-zA-Z0-9_-]+)\s*\}\s*$",
        repl_block,
        markdown_text,
        flags=re.MULTILINE,
    )

    return markdown_text


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


# ============================================================================= Post-processing (HTML)
def next_element(tag: Tag) -> Optional[Tag]:
    node = tag.next_sibling
    while node is not None:
        if isinstance(node, Tag):
            return node
        if isinstance(node, NavigableString) and str(node).strip():
            return None
        node = node.next_sibling
    return None


def postprocess_body(body_html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(f'<div id="markdown-root">{body_html}</div>', "lxml")
    root = soup.find("div", id="markdown-root")
    if root is None:
        raise RuntimeError("Markdown HTML 后处理失败")

    # Resolve ordinary relative Markdown images against figures/ and assets/.
    for img in root.find_all("img"):
        src = img.get("src", "")
        if not src or urlparse(src).scheme in {"http", "https", "file", "data"}:
            continue
        resolved = resolve_asset(src, FIGURES_DIR, ASSETS_DIR)
        if resolved is not None:
            img["src"] = path_to_file_uri(resolved)

    # Convert <p class="note"> starting with "Adapted from:" into blockquote.attribution
    # (food-guide content uses {: .note } attribute instead of > blockquote).
    for p in root.find_all("p"):
        classes = p.get("class") or []
        text = p.get_text(" ", strip=True)
        if "note" in classes and text.startswith("Adapted from:"):
            bq = soup.new_tag("blockquote", attrs={"class": "attribution"})
            for child in list(p.children):
                bq.append(child.extract())
            p.replace_with(bq)

    # Number sections and collect TOC entries.
    toc_items: List[Tuple[int, str, str]] = []
    top_no = 0
    sub_no = 0
    table_no = 0

    for heading in list(root.find_all(["h2", "h3"])):
        classes = heading.get("class") or []
        original_inner = heading.decode_contents()
        original_text = heading.get_text(" ", strip=True)
        is_nonum = "nonum" in classes

        if heading.name == "h2":
            if is_nonum:
                number = ""
                anchor = f"sec-nonum-{len(toc_items)}"
                level = 1
            else:
                top_no += 1
                sub_no = 0
                number = f"{top_no}."
                anchor = f"sec-{top_no}"
                level = 1
        else:
            if is_nonum:
                number = ""
                anchor = f"sec-nonum-{len(toc_items)}"
                level = 2
            else:
                sub_no += 1
                number = f"{top_no}.{sub_no}"
                anchor = f"sec-{top_no}-{sub_no}"
                level = 2

        heading["id"] = anchor
        if number:
            number_span = soup.new_tag("span", attrs={"class": "secno"})
            number_span.string = number
            heading.insert(0, number_span)
            heading.insert(1, " ")
            toc_label = f'<span class="secno">{number}</span> {original_inner}'
        else:
            toc_label = original_inner
        toc_items.append((level, anchor, toc_label))

        sibling = next_element(heading)
        if heading.name == "h3" and sibling is not None and sibling.name == "table":
            table_no += 1
            caption = soup.new_tag("div", attrs={"class": "table-caption"})
            caption.string = f"Table {table_no} — {original_text}"
            sibling.insert_before(caption)
            if len(sibling.find_all("tr")) <= 10:
                block = soup.new_tag("div", attrs={"class": "heading-table-block"})
                heading.insert_before(block)
                block.append(heading.extract())
                block.append(caption.extract())
                block.append(sibling.extract())

    for table in root.find_all("table"):
        table["class"] = (table.get("class") or []) + ["data-table"]

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
        # Dedupe while preserving order.
        seen = set()
        quote_tag["class"] = [c for c in classes if not (c in seen or seen.add(c))]

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


# ============================================================================= Cover + preface + full HTML
def build_preface(meta: Dict[str, str]) -> str:
    """Assemble preface blockquote from guide.toml quote + content/_intro.md."""
    intro_path = CONTENT_DIR / "_intro.md"
    intro_text = intro_path.read_text(encoding="utf-8") if intro_path.exists() else ""

    quote = meta.get("quote", "")
    quote_author = meta.get("quote_author", "")

    lines: List[str] = []
    if quote:
        lines.append(f'> *"{quote}"*')
        lines.append(">")
        if quote_author:
            lines.append(f"> —— {quote_author}")
        lines.append(">")
    for line in intro_text.splitlines():
        if line.strip():
            lines.append("> " + line.strip())
        else:
            lines.append(">")

    preface_md = "\n".join(lines)
    if not preface_md.strip():
        return ""

    preface_html = run_pandoc(preface_md)
    soup = BeautifulSoup(preface_html, "lxml")
    quote_tag = soup.find("blockquote")
    if quote_tag is None:
        return preface_html
    quote_tag["class"] = ["preface"]
    paragraphs = quote_tag.find_all("p")
    if paragraphs:
        paragraphs[0]["class"] = (paragraphs[0].get("class") or []) + ["opening-quote"]
    if len(paragraphs) > 1 and quote_author and quote_author in paragraphs[1].get_text():
        paragraphs[1]["class"] = (paragraphs[1].get("class") or []) + ["quote-source"]
    return str(quote_tag)


def month_year(date_text: str, fallback: str = "") -> str:
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").strftime("%B %Y")
    except ValueError:
        return fallback or date_text or "October 2026"


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
    title_html = meta.get("title", "")
    my = meta.get("month_year") or month_year(meta.get("Date", ""))
    return f"""
<div class="cover">
    <div class="rfc-head">
        <div class="left">
            {html.escape(meta.get('authors', meta.get('Maintainers', 'XueHai 809ers')))}<br />
            Request for Comments: {html.escape(meta.get('Request', '809'))}<br />
            Category: {html.escape(meta.get('Category', 'Informational'))}
        </div>
        <div class="right">
            {html.escape(meta.get('Organization', 'WHUT Xuehai Building'))}<br />
            {html.escape(my)}
        </div>
    </div>
    <div class="head-rule"></div>
    <h1 class="cover-title">{title_html}</h1>
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


# ============================================================================= HTML → PDF
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


# ============================================================================= CLI
def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="809 食谱指南构建器：guide.toml + content/*.md → RFC 风格 PDF。"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出 PDF；默认：food-guide-v<version>.pdf",
    )
    parser.add_argument(
        "--converter",
        type=Path,
        default=DEFAULT_CONVERTER,
        help="html_to_pdf.js 路径；默认为 converter/html_to_pdf.js",
    )
    parser.add_argument(
        "--keep-html",
        action="store_true",
        help="同时保留中间 HTML，便于调试版式",
    )
    sub = parser.add_subparsers(dest="cmd")
    n = sub.add_parser("new", help="在 entries/ 新建一条推荐")
    n.add_argument("name")
    return parser.parse_args(argv)


def new_entry(name: str) -> int:
    nums: List[int] = []
    for p in ENTRIES_DIR.glob("*.md"):
        if p.name.startswith("_"):
            continue
        fm, _ = read_front_matter(p)
        if fm.get("no", "").isdigit():
            nums.append(int(fm["no"]))
    no = max(nums) + 1 if nums else 1
    path = ENTRIES_DIR / ("%04d.md" % no)
    path.write_text(
        "---\n"
        "no: %d\n"
        "name: %s\n"
        "type: 堂食\n"
        "where:\n"
        "by:\n"
        "date: %s\n"
        "---\n"
        "点评：\n" % (no, name, datetime.date.today().isoformat()),
        encoding="utf-8",
    )
    print("Created %s  (see entries/_template.md for all fields)" % path.relative_to(ROOT))
    return 0


def build(args) -> int:
    meta = load_meta()
    warnings: List[str] = []

    # Walk content/*.md in filename order, expand directives.
    chunks: List[str] = []
    fig_counter = [0]  # mutable counter for figure auto-numbering
    for p in sorted(CONTENT_DIR.glob("*.md")):
        if p.name.startswith("_"):
            continue
        text = p.read_text(encoding="utf-8")
        text = expand_directives(text, fig_counter)
        chunks.append(text)
    body_md = "\n\n".join(chunks)

    # Pre-process Markdown: attr blocks, demote headings, group guideline blockquote, resolve images.
    body_md = preprocess_attr_blocks(body_md)
    body_md = demote_headings(body_md)
    body_md = group_guideline_blockquote(body_md)
    body_md = replace_obsidian_images(body_md, warnings)

    # Run Pandoc.
    body_html_raw = run_pandoc(body_md)
    body_html, toc_html = postprocess_body(body_html_raw)

    # Preface.
    preface_html = build_preface(meta)

    # Full HTML.
    full_html = build_full_html(meta, body_html, toc_html, preface_html)

    # Output path.
    if args.output:
        output_path = args.output.expanduser().resolve()
    else:
        output_path = ROOT / f"food-guide-v{meta.get('Version', '0')}.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
        tmp.write(full_html)
        tmp.close()
        html_path = Path(tmp.name)
        cleanup_html = True

    try:
        convert_html_to_pdf(html_path, output_path, args.converter)
    finally:
        if cleanup_html:
            try:
                html_path.unlink()
            except OSError:
                pass

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    print(f"Built {output_path.name} ({output_path.stat().st_size // 1024} KB)")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    if args.cmd == "new":
        return new_entry(args.name)
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
