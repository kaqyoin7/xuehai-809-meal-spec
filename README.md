# Handbook of The Deadline-Driven and Starving of Hunger

将 Markdown 渲染为 RFC / ISO / IETF 风格的 PDF。


## Get Started
```bash
git clone https://github.com/kaqyoin7/xuehai-819-meal-spec.git
cd xuehai-819-meal-spec
./bootstrap.sh             # 依赖安装（首次运行）
./run.sh 819.md            # 生成 *.pdf
```

指定输出名：

```bash
./run.sh 819.md -o out.pdf
```

图片默认从项目根 `assets/` 目录解析；自定义目录：

```bash
./run.sh 819.md --asset-dir ./my-images
```

## How It Works

整体是 `Markdown → HTML → PDF` 两段式：

1. **md → html**（[script.py](script.py)）：Pandoc 将 Markdown 转 HTML5，Python 后处理做章节编号、目录、表格 caption、引文卡片化、图片路径解析
2. **html → pdf**（[converter/html_to_pdf.js](converter/html_to_pdf.js)）：Node + Playwright/Chromium + Paged.js 完成分页与 PDF 导出

中间产物是一份自包含 HTML（含完整 CSS / 封面 / 目录 / 正文），可独立浏览。**这意味着你可以先生成 HTML，手动调整后再转 PDF：**

```bash
# 1) 同时输出 HTML 和 PDF
./run.sh 819.md --keep-html          # 得到 819-RFC风格.html

# 2) 手动编辑

# 3) 改好的 HTML 直接转 PDF
node converter/html_to_pdf.js 819-RFC风格.html --output 最终.pdf
```

> 适合在 md 表达力不足、需要微调样式或临时插入富 HTML 的场景。

## 目录结构

```
.
├── 819.md            # 主源文档（示例）
├── appendix.md       # 附录文档（示例）
├── assets/           # 图片资源目录（Obsidian 格式图片 ![[...]] 引用从这里解析）
├── script.py         # 转换脚本：md → html → pdf
├── bootstrap.sh      # 依赖安装
├── converter/        # HTML→PDF 工具链（感谢 Kimi，依赖 Playwright + Paged.js）
│   ├── html_to_pdf.js
│   ├── browser_helper.js
│   ├── paged.polyfill.js
│   └── package.json
└── .gitignore
```

## Note

由于脚本是在赶工中 AIGC 一次抽盲盒，因此没有设计一套通用、可扩展的 Markdown→PDF 渲染规则。具体表现：

- **大量针对当前 .md 关键词硬编码**：封面元数据靠行首 `Version:` / `Date:` / `Maintainers:` / `Status:` 解析；引文卡片靠 `Takeaway:` / `Adapted from:` / `No.` / `如何写一条...Qualified` 等特定前缀识别；章节升降级命中 `推荐列表` / `Food Integrity` 等具体章节名。换一份不同结构的文档，这些样式大概率不会触发。
- **封面字段写死**：`Request: 819` / `Maintainers: XueHai 819ers` / `Organization: WHUT Xuehai Building` 等默认值硬编码在 [script.py 的 meta 字典](script.py) 里；`month_year` 失败时兜底 `October 2026`。
- **章节编号、目录、表格 caption 等通用机制**对常规 Markdown 是生效的；但一旦你新增"特殊卡片"类型（如 `Tip:` / `Warning:` 前缀），会被归到默认 `note` 样式，需要手动改 [postprocess_body](script.py) 与 CSS。

简而言之：**欢迎师弟师妹提 PR 重构** 。
