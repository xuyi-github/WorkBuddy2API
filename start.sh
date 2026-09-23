#!/usr/bin/env bash
# 一键启动 WorkBuddy2API（Linux / macOS / Docker）。
#
#   ./start.sh              # 默认 8000 端口
#   PORT=9000 ./start.sh
#   API_KEY=my-key CODEBUDDY_AUTH_TOKEN=<token> ./start.sh
#
# token 来源：CODEBUDDY_AUTH_TOKEN 环境变量，或项目根目录的 tokens.json。
# API_KEY 来源：环境变量，或项目根目录 apikey.local（文件不存在则自动生成一个随机 key 写入）。
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

step() { printf '\033[36m[*]\033[0m %s\n' "$1"; }
ok()   { printf '\033[32m[+]\033[0m %s\n' "$1"; }
warn() { printf '\033[33m[!]\033[0m %s\n' "$1"; }

# 1. 定位 Python
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "未找到 python3，请先安装 Python 3.10+" >&2
    exit 1
fi
ok "Python: $("$PY" --version 2>&1)"

# 2. 检查依赖
if ! "$PY" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
    warn "缺少依赖 fastapi / uvicorn，正在安装..."
    "$PY" -m pip install fastapi uvicorn
fi
ok "依赖检查通过 (fastapi / uvicorn)"

# 3. 预检 token
if "$PY" -c 'import codebuddy_direct_api as m; m.find_and_load_token()' >/dev/null 2>&1; then
    ok "token 加载成功"
else
    warn "未能加载 token：请设置 CODEBUDDY_AUTH_TOKEN 环境变量，或在项目根目录放置 tokens.json"
    warn "服务仍会启动，但 /v1/chat/completions 会返回 503"
fi

# 4. 兜底 API_KEY
# 优先级：环境变量 API_KEY > 项目根目录 apikey.local > 自动生成并写入 apikey.local
API_KEY_FILE="apikey.local"
if [ -n "${API_KEY:-}" ]; then
    ok "API_KEY 来自环境变量"
    echo "    （环境变量优先，apikey.local 会被忽略；想改用它先 unset API_KEY）"
else
    if [ -f "$API_KEY_FILE" ]; then
        # 去掉 BOM / CR 与首尾空白，避免把不可见字符带进 HTTP header
        API_KEY="$(tr -d '\357\273\277\r' < "$API_KEY_FILE" | head -n 1 \
            | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    fi
    if [ -n "$API_KEY" ]; then
        ok "API_KEY 来自 $API_KEY_FILE"
    else
        API_KEY="sk-wb-$(od -An -tx1 -N16 /dev/urandom | tr -d ' \n')"
        printf '%s' "$API_KEY" > "$API_KEY_FILE"
        ok "已生成随机 API_KEY 并写入 $API_KEY_FILE"
    fi
fi
export API_KEY
echo "    API_KEY: $API_KEY"
echo "    （CC Switch 里该 provider 的 apiKey 填同一个值；改 key 后需重启服务）"

# 5. 启动
export PORT
echo
ok "启动中：http://127.0.0.1:${PORT}"
echo "    健康检查   http://127.0.0.1:${PORT}/health"
echo "    模型列表   http://127.0.0.1:${PORT}/v1/models"
echo "    OpenAI 兼容 base_url   http://127.0.0.1:${PORT}/v1"
echo
echo "    接入 CC Switch：新增 provider，base_url 填上面的地址，apiFormat 选 openai_chat"
echo "    详见 docs/codex-integration.md   （Ctrl+C 停止服务）"
echo

exec "$PY" -m uvicorn server:app --host "$HOST" --port "$PORT" --log-level info