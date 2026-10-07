#!/usr/bin/env bash
# bootstrap.sh — 一键安装 script.py 的全部依赖（最低入侵）
#
# 入侵性说明：
#   Python 依赖  → 项目内 .venv/                （完全本地，可删即净）
#   Pandoc       → 项目内 .tools/pandoc/        （静态二进制，不动系统）
#   Node 依赖    → 项目内 converter/node_modules/（npm 本地安装）
#   Chromium     → ~/.cache/ms-playwright/      （用户级缓存，非系统）
#   CJK 字体     → ~/.local/share/fonts/        （用户级字体，不动 /usr/share/fonts）
#   Chromium 系统库（libgbm1 等）→ 唯一需 sudo 的部分；先 --dry-run 检测，
#                   只在缺失时装，且只装 playwright 列出的最小集合。
#
# 已有部分依赖的主机会被自动检测并跳过对应步骤（增量安装）。
#
# 用法：
#   ./bootstrap.sh            # 安装依赖
#   ./bootstrap.sh --run      # 安装后顺带跑 script.py 819.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 直连外网，不依赖主机代理（PySocks/代理服务常缺失，会让脚本卡死）。
# 如需走代理，请在运行前 export 对应变量并自行确保代理可用。
unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy

VENV_DIR="$SCRIPT_DIR/.venv"
TOOLS_DIR="$SCRIPT_DIR/.tools"
FONTS_DIR="${HOME}/.local/share/fonts"
PANDOC_VERSION="3.6.4"

log()  { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[bootstrap]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 0. 基本检测 ----------
command -v curl >/dev/null 2>&1 || die "需要 curl：sudo apt install -y curl"
command -v tar   >/dev/null 2>&1 || die "需要 tar"

# ---------- 1. Python venv ----------
if ! command -v python3 >/dev/null 2>&1; then
    die "未找到 python3，请先：sudo apt install -y python3 python3-venv"
fi

if [ ! -d "$VENV_DIR" ]; then
    log "创建 Python venv（.venv/，--system-site-packages 复用系统已装包）"
    python3 -m venv "$VENV_DIR" --system-site-packages || \
        die "venv 创建失败；若提示 ensurepip 缺失：sudo apt install -y python3-venv"
fi

log "升级 pip 并安装 beautifulsoup4 / lxml（仅当缺失）"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -c "import bs4, lxml" 2>/dev/null || \
    "$VENV_DIR/bin/pip" install --quiet beautifulsoup4 lxml

# ---------- 2. Pandoc（静态二进制到 .tools/）----------
need_pandoc=0
if ! command -v pandoc >/dev/null 2>&1 && [ ! -x "$TOOLS_DIR/pandoc/bin/pandoc" ]; then
    need_pandoc=1
fi
if [ "$need_pandoc" = "1" ]; then
    arch="$(uname -m)"
    case "$arch" in
        x86_64)  tb="pandoc-${PANDOC_VERSION}-linux-amd64.tar.gz" ;;
        aarch64|arm64) tb="pandoc-${PANDOC_VERSION}-linux-arm64.tar.gz" ;;
        *) die "不支持的架构：$arch" ;;
    esac
    log "下载 Pandoc $PANDOC_VERSION 静态二进制 → .tools/pandoc/"
    mkdir -p "$TOOLS_DIR"
    tmp="$(mktemp -d)"
    curl -fsSL "https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/${tb}" \
        -o "$tmp/pandoc.tar.gz" || die "Pandoc 下载失败"
    tar -xzf "$tmp/pandoc.tar.gz" -C "$tmp"
    rm -rf "$TOOLS_DIR/pandoc"
    mv "$tmp/pandoc-${PANDOC_VERSION}" "$TOOLS_DIR/pandoc"
    rm -rf "$tmp"
else
    log "Pandoc 已存在，跳过"
fi

# ---------- 3. Node ----------
if ! command -v node >/dev/null 2>&1; then
    warn "未检测到 Node.js。Chromium 渲染需要 Node（>=18）。"
    warn "建议：sudo apt install -y nodejs npm  （Ubuntu 22.04 自带 node 18）"
    die "请安装 Node.js 后重跑本脚本。"
fi
log "Node: $(node --version)"

# ---------- 4. converter/ 的 npm 依赖 ----------
log "安装 converter/ 的 npm 依赖（项目内 node_modules/）"
cd "$SCRIPT_DIR/converter"
if [ ! -d node_modules ] || [ ! -d node_modules/playwright ]; then
    npm install --silent --no-audit --no-fund
else
    log "node_modules 已存在，跳过 npm install"
fi

# ---------- 5. Chromium（用户级缓存）----------
log "确保 Chromium 可用（playwright 装到 ~/.cache/ms-playwright/）"
npx --prefix "$SCRIPT_DIR/converter" playwright install chromium 2>/dev/null \
    || npx playwright install chromium

# Chromium 运行所需的系统库（libgbm1 等）。先 dry-run 看缺不缺。
log "检测 Chromium 系统库依赖（缺失时才 sudo apt 装最小集合）"
missing="$(npx playwright install-deps --dry-run chromium 2>&1 | \
           grep -oE 'apt-get install -y [^ ]+' | head -1 || true)"
if [ -n "$missing" ]; then
    warn "Chromium 缺少系统库，需要 sudo 安装：$missing"
    sudo apt-get update -qq
    sudo apt-get install -y libgbm1 libasound2t64 libatk-bridge2.0-0 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libatspi2.0-0 libcups2 libnss3 libnspr4 libxshmfence1
else
    log "Chromium 系统库已齐备"
fi
cd "$SCRIPT_DIR"

# ---------- 6. CJK 字体（用户级字体目录）----------
log "检测 CJK 字体"
if fc-list 2>/dev/null | grep -qi "noto.*cjk.*sc\|noto sans cjk sc\|noto serif cjk sc"; then
    log "CJK 字体已存在"
else
    log "下载 Noto CJK SC 字体 → ~/.local/share/fonts/（用户级）"
    mkdir -p "$FONTS_DIR"
    # 用 notofonts noto-cjk 的 Sans/OTF/SimplifiedChinese 子集；如失败再用 GoogleFonts 包。
    # 这些是单语言 OTF，体积小，不需要 subset。
    base_cjk="https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese"
    base_cjk_serif="https://github.com/notofonts/noto-cjk/raw/main/Serif/OTF/SimplifiedChinese"
    get_font() {  # url dest
        [ -f "$2" ] && return 0
        curl -fsSL --retry 3 -o "$2" "$1" 2>/dev/null || \
            curl -fsSL --retry 3 -o "$2" "$1" 2>/dev/null || \
            warn "下载失败：$2 ← $1"
    }
    get_font "$base_cjk/NotoSansCJKsc-Regular.otf" \
        "$FONTS_DIR/NotoSansCJKsc-Regular.otf"
    get_font "$base_cjk/NotoSansCJKsc-Bold.otf" \
        "$FONTS_DIR/NotoSansCJKsc-Bold.otf"
    get_font "$base_cjk_serif/NotoSerifCJKsc-Regular.otf" \
        "$FONTS_DIR/NotoSerifCJKsc-Regular.otf"
    get_font "$base_cjk_serif/NotoSerifCJKsc-Bold.otf" \
        "$FONTS_DIR/NotoSerifCJKsc-Bold.otf"
    # Liberation Sans（若系统未装 fonts-liberation）。下载失败也无碍：
    # CSS 中 Liberation 后还跟着 DejaVu Sans、Noto Sans CJK SC 作为兜底。
    fc-list 2>/dev/null | grep -qi "liberation sans" || \
        get_font "https://github.com/liberationfonts/liberation-fonts/raw/main/src/LiberationSans-Regular.ttf" \
            "$FONTS_DIR/LiberationSans-Regular.ttf" || true
    fc-cache -f "$FONTS_DIR" 2>/dev/null || fc-cache -f 2>/dev/null || true
fi

# ---------- 7. 生成运行器 ----------
log "生成 run.sh（用项目内 venv + 项目内 pandoc 调用 script.py）"
# 用 quoted heredoc 避免变量被外层 shell 误展开；用占位符 sed 替换实际路径。
cat > "$SCRIPT_DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
# run.sh — 用项目本地 venv 与 pandoc 运行 script.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export PATH="__TOOLS_DIR__/pandoc/bin:$PATH"

# 确保 Chromium 能找到字体
export HOME="${HOME:-__HOME__}"

PY="__VENV_DIR__/bin/python"
MD="${1:-819.md}"
OUT="${2:-}"
ASSET_DIR="$SCRIPT_DIR/assets"

# 默认从项目根 assets/ 解析图片，可用 --asset-dir 覆盖。
# 若用户第二个参数以 - 开头（视作 flag），则不强制 -o。
# 用 bash 数组避免空 "${@:3}" 被 argparse 当成空位置参数。
if [ -n "$OUT" ] && [[ "$OUT" != -* ]]; then
    set -- "$MD" -o "$OUT" --asset-dir "$ASSET_DIR" "${@:3}"
else
    set -- "$MD" --asset-dir "$ASSET_DIR" $OUT "${@:3}"
fi
"$PY" script.py "$@"
EOF
sed -i \
    -e "s#__TOOLS_DIR__#$TOOLS_DIR#g" \
    -e "s#__VENV_DIR__#$VENV_DIR#g" \
    -e "s#__HOME__#$HOME#g" \
    "$SCRIPT_DIR/run.sh"
chmod +x "$SCRIPT_DIR/run.sh"

log "完成。运行方式："
echo "    ./run.sh 819.md                  # 默认输出 819-RFC风格.pdf"
echo "    ./run.sh 819.md -o out.pdf        # 指定输出"
echo
echo "本次安装位置（卸载直接删即可）："
echo "    $VENV_DIR"
echo "    $TOOLS_DIR"
echo "    $SCRIPT_DIR/converter/node_modules"
echo "    ~/.cache/ms-playwright/"
echo "    $FONTS_DIR  (CJK 字体)"

# 可选：安装后直接跑一次
if [ "${1:-}" = "--run" ]; then
    log "运行 script.py 819.md"
    "$SCRIPT_DIR/run.sh" 819.md
fi
