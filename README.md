# Handbook of The Deadline-Driven and Starving of Hunger

将 Markdown 渲染为 RFC / ISO / IETF 风格的 PDF。

## Get Started

```bash
git clone https://github.com/kaqyoin7/xuehai-809-meal-spec.git
cd xuehai-809-meal-spec
./bootstrap.sh             # 依赖安装（首次运行，最小入侵 + 增量）
./run.sh                   # 构建 PDF（默认输出 food-guide-v<version>.pdf）
```

usage：

```bash
./run.sh --keep-html       # 同时保留中间 HTML，便于调试版式
./run.sh -o out.pdf        # 指定输出路径
./run.sh new "店名"        # 在 entries/ 新建一条推荐
```

## How It Works

整体为 `Markdown → HTML → PDF` 两段式：

1. **md → html**（[script.py](script.py)）：根据 `guide.toml` 与 `content/*.md` 拼装正文，展开 `@examples` / `@entries` / `@pagebreak` ，再交给 Pandoc 转 HTML5，最后 Python 后处理做章节编号、目录、表格 caption、引文卡片化、图片路径解析
2. **html → pdf**（[converter/html_to_pdf.js](converter/html_to_pdf.js)）：Node + Playwright/Chromium + Paged.js 完成分页与 PDF 导出

中间产物是一份自包含 HTML（含完整 CSS / 封面 / 目录 / 正文），可独立浏览。**这意味着你可以先生成 HTML，手动调整后再转 PDF：**

```bash
# 1) 同时输出 HTML 和 PDF
./run.sh --keep-html          # 得到 food-guide-v1.0.0.html

# 2) 手动编辑该 HTML

# 3) 改好的 HTML 直接转 PDF
node converter/html_to_pdf.js food-guide-v1.0.0.html --output 最终.pdf
```

> 适合在 md 表达力不足、需要微调样式或临时插入富 HTML 的场景。

## 目录结构

```
.
├── guide.toml            # 全局元信息：封面、页眉页脚、版本号、引言
├── content/              # 正文 markdown，按 10-/20-/... 顺序拼接
│   ├── _intro.md         # 封面引言（不含 front matter）
│   ├── 10-food-integrity.md
│   ├── 20-recommendations.md   # 用 @examples / @entries 指令引入下两目录
│   ├── 30-ordering-under-pressure.md
│   ├── 40-contributing.md
│   └── 60-license.md
├── examples/             # 推荐示例卡片（带 front matter）
├── entries/              # 真实推荐条目（带 front matter，编号自动递增）
│   └── _template.md      # 字段模板
├── figures/              # examples/entries 引用的图片
├── assets/               # 其他图片资源（Obsidian ![[...]] 嵌入从这里解析）
├── script.py             # 主转换脚本
├── bootstrap.sh          # 一键依赖安装
├── run.sh                # 由 bootstrap.sh 生成的运行器
├── converter/            # HTML→PDF 工具链（Playwright + Paged.js）
│   ├── html_to_pdf.js
│   ├── browser_helper.js
│   ├── paged.polyfill.js
│   └── package.json
└── .gitignore
```

## 写一条新推荐

```bash
./run.sh new "东北水饺"
# → 创建 entries/0001.md，含 front matter 模板
```

字段含义见 [entries/_template.md](entries/_template.md)。修改后 `./run.sh` 重新构建。

## Markdown 扩展语法

- **front matter**：`entries/*.md` / `examples/*.md` 用 `--- ... ---` 包裹的简单 YAML 描述卡片元信息（`no` / `name` / `type` / `where` / `by` / `date` / `figure` 等）。
- **指令**（写在 `content/*.md` 中的独立行）：
  - `@examples` —— 展开所有 `examples/*.md`
  - `@entries` —— 展开所有 `entries/*.md`（按 `no` 排序）
  - `@pagebreak` —— 强制分页
  - `@split` —— 软分隔（视觉换行提示）
  - `Figure: name.jpg|8cm|caption` —— 插入图片
- **属性块**（Pandoc `attr_list` 风格）：单行 `{: .class }` 给前一段加 class；行尾 `{: .nonum }` 让标题不进编号。
- **Obsidian 嵌入**：`![[文件名]]` 或 `![[文件名|宽度]]`，从 `figures/` 或 `assets/` 解析。
- **卡片自动识别**：以 `Takeaway:` / `Adapted from:` / `No.` / `如何写一条 ... Qualified` 开头的 blockquote 自动套用对应样式。

## Note

由于脚本是在赶工中 AIGC 一次抽盲盒，因此没有设计一套(fixed)~~通用、可扩展~~稳定的 Markdown→PDF 渲染规则，具体表现为：

- ~~大量针对当前 .md 关键词硬编码：封面元数据靠行首 `Version:` / `Date:` / `Maintainers:` / `Status:` 解析；引文卡片靠 `Takeaway:` / `Adapted from:` / `No.` / `如何写一条...Qualified` 等特定前缀识别；章节升降级命中 `推荐列表` / `Food Integrity` 等具体章节名。换一份不同结构的文档，这些样式大概率不会触发。~~
- ~~章节编号、目录、表格 caption 等通用机制对常规 Markdown 是生效的；但一旦你新增"特殊卡片"类型（如 `Tip:` / `Warning:` 前缀），会被归到默认 `note` 样式，需要手动改 [postprocess_body](script.py) 与 CSS~~
简而言之：**欢迎师弟师妹提 PR 重构** 。
