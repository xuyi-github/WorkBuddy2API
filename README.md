# 🚀 WorkBuddy2API

把 WorkBuddy 的内部 API 包装成 **OpenAI 兼容的 REST API**，一行部署，随处调用。

> English version: [README.en.md](README.en.md)
>
> 这是 [Tom6814/WorkBuddy2API](https://github.com/Tom6814/WorkBuddy2API) 的 fork，
> 本 fork 相对上游的改动见 [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md)。

---

## 这是什么？

一个超轻量的代理服务：你在 WorkBuddy 里能用的所有模型（DeepSeek、Kimi、GLM、混元、MiniMax……），现在都能通过标准的 OpenAI 接口调出来。任何支持 OpenAI API 的工具（Claude Code、各类客户端、脚本……）都能直接用上 WorkBuddy 的模型。

## 特性一览

- ✨ **OpenAI 完全兼容** — `/v1/chat/completions`、`/v1/models`、tools/tool_calls 透传
- 🧠 **思考内容输出** — 支持 `reasoning_content`（推理过程）透传
- 🔁 **多轮思考回放** — 上游会丢弃历史 `reasoning_content`，发送前自动折叠进 `content`
- 🚀 **默认最高深度思考** — 不传参数也能拿到深度推理结果
- ⚡ **默认流式输出** — SSE 边想边答，延迟更低
- 🖼️ **AI 生图** — 文生图 `/v1/images/generations`、图生图 `/v1/images/edits`
- 🔄 **Token 自动刷新** — 过期自动刷新，无需手动干预
- 🛡️ **反封号保护** — 内置限速、随机延迟、UA 轮换、指数退避
- 🐳 **一行部署** — Docker / Zeabur / Railway 随便放

## 快速开始

### 1. 拿到 WodeBuddy Token

登录 WorkBuddy 后，token 会自动存在本地：

```bash
cat ~/Library/Application\ Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info
```

### 2. 本地运行

一键启动（自动装依赖、预检 token，推荐）：

```powershell
# Windows
.\start.ps1                     # 默认 8000 端口
.\start.ps1 -Port 9000          # 换端口
```

```bash
# Linux / macOS
./start.sh                      # 默认 8000 端口
PORT=9000 ./start.sh
```

也可以手动启动：

```bash
# 安装依赖
pip install fastapi uvicorn

# 设置环境变量并启动
export CODEBUDDY_AUTH_TOKEN="你的token"
export API_KEY="你自定的key"
python server.py
```

### 3. 部署到 Zeabur / Railway / 任意 Docker 平台

只需设置两个环境变量：

| 变量 | 必填 | 说明 |
|------|------|------|
| `CODEBUDDY_AUTH_TOKEN` | ✅ | WorkBuddy 的 Bearer Token |
| `API_KEY` | ✅ | 调用本 API 所需的密钥 |
| `DEFAULT_MODEL` | ❌ | 默认模型，默认 `deepseek-v3` |
| `DEFAULT_THINKING` | ❌ | 默认思考深度，默认 `max` |
| `REPLAY_REASONING` | ❌ | 是否把历史思考折叠进 `content` 回放给上游，默认开启（设为 `0` 关闭） |
| `WORKBUDDY_TOKENS_FILE` | ❌ | 指定 `tokens.json` 路径，默认取项目根目录的 `tokens.json` |
| `PORT` | ❌ | 监听端口，默认 `8000` |

> Token 加载优先级：`CODEBUDDY_AUTH_TOKEN` 环境变量 > `--auth-file` > 项目根目录 `tokens.json` > 本地 WorkBuddy auth 文件。
> `tokens.json` 结构见 [tokens.example.json](tokens.example.json)（`tokens[].token_info.access_token`）；
> 该文件已在 `.gitignore` 中，**不要提交真实 token**。

## 多轮思考回放

上游 `/v2/chat/completions` 反序列化 `messages` 时只读取 `role` / `content` /
`tool_calls` 等白名单字段，assistant 历史消息上的 `reasoning_content` 会被静默丢弃：

- 在上一轮 assistant 消息中注入 500 字思考，下一轮 `prompt_tokens` 增量恒为 0；
- 上一轮思考中植入的暗号，下一轮模型完全无法感知。

因此本项目在发送前把 assistant 历史消息的思考折叠进 `content`，让它随历史消息一起
进入底座模型的 Chat Template：

```text
<thinking>
上一轮的思考内容
</thinking>

上一轮的正式回答
```

行为说明：

- 仅处理 `assistant` 消息，`user` / `system` 消息原样透传
- 兼容 `reasoning_content` / `reasoning` / `thinking`（含 Anthropic 风格 thinking 块）
- 已内联相同思考的 `content` 不会重复注入（幂等）
- 非字符串 `content`（多模态块）保持原样
- 只想下行透传、不回放历史思考时，设置 `REPLAY_REASONING=0` 关闭

## 调用示例

**聊天（流式，默认最高思考）：**

```bash
curl https://your-domain/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kimi-k3-1",
    "messages": [{"role": "user", "content": "用 Python 写一个快速排序"}]
  }'
```

**指定思考深度：**

```bash
-d '{
  "model": "deepseek-v3",
  "messages": [...],
  "reasoning_effort": "high"
}'
```

`reasoning_effort` 可选值：`low` | `medium` | `high` | `max` | `off`

**工具调用（tools 透传）：**

```bash
-d '{
  "model": "glm-5.2",
  "messages": [{"role": "user", "content": "今天天气怎么样？"}],
  "tools": [{"type": "function", "function": {"name": "get_weather", "description": "查天气", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}}]
}'
```

**文生图：**

```bash
curl https://your-domain/v1/images/generations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cute orange cat, cartoon style", "model": "hunyuan-image-v3.0"}'
```

**图生图：**

```bash
curl https://your-domain/v1/images/edits \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "make it blue", "image": "data:image/png;base64,..."}'
```

`image` 支持：data URL / http(s) URL / raw base64 / 本地路径。

## 可用模型

```
# DeepSeek
deepseek-v3  deepseek-v3-0324  deepseek-v3-0324-lkeap
deepseek-v3-1-lkeap  deepseek-r1  deepseek-r1-0528-lkeap
deepseek-v4-flash  deepseek-v4-pro  deepseek-v3-2-volc

# Kimi
kimi-k2.5          kimi-k2.6               kimi-k2.7
kimi-k3-1

# Hunyuan
hunyuan-chat       hunyuan-2.0-instruct    hunyuan-2.0-thinking

# MiniMax
minimax-m2.7

# GLM
glm-5.1  glm-5.2  glm-5.0-turbo  glm-5v-turbo

# HY
hy3                hy3-preview（免费）    hy3-preview-agent（收费）
hy4-preview（免费体验 0.00，超额 0.04/次）

# 生图
hunyuan-image-v3.0                        （文生图）
hunyuan-image-v3.0-art                    （文生图·艺术风格）
hunyuan-image-v2.0-general-edit           （图生图）
```

> 也可以通过 `GET /v1/models` 实时获取完整模型列表。

> 模型清单已按 2026-09-18 的上游实测校正：移除了已下架的 4 个模型
> （`deepseek-r1-0528`、`deepseek-v3-1`、`glm-4.7`、`glm-5.0`），详见 [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md)。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/v1/models` | 列出所有支持的模型 |
| `POST` | `/v1/chat/completions` | 聊天补全（支持 SSE 流式） |
| `POST` | `/v1/images/generations` | 文生图 |
| `POST` | `/v1/images/edits` | 图生图 |

## 项目结构

```
codebuddy-api-server/
├── server.py                 # OpenAI 兼容 REST API 服务器
├── codebuddy_direct_api.py   # CodeBuddy 直连客户端（token 管理/SSE/生图）
├── start.ps1 / start.bat     # 一键启动（Windows）
├── start.sh                  # 一键启动（Linux / macOS）
├── Dockerfile                # Python 3.11 容器
├── docs/                     # 交接文档与自检脚本
└── README.md
```

## 在 Codex / Claude Code 中使用

**可以接入，本项目不需要改代码。**

Codex 0.155.0 只支持 Responses API（`wire_api = "responses"`），本项目只提供
`/v1/chat/completions`。协议差异由 **CC Switch 的本地代理**承担：把本项目作为
`apiFormat = openai_chat` 的 provider 加进 CC Switch，CC Switch 就会把 Codex 的 Responses
请求 / Claude Code 的 Anthropic 请求转换成 Chat Completions 再转发给本项目。

```text
启动本项目 ( .\start.ps1 )
        |
        v
CC Switch 新增 provider:  apiFormat = openai_chat
                          base_url = http://127.0.0.1:8000/v1
        |
        v
切换供应商  ->  Codex (走 127.0.0.1:10001) / Claude Code 即可使用
```

字段填法、验证步骤与排错见 [docs/codex-integration.md](docs/codex-integration.md)。

其他 OpenAI 兼容客户端（Cherry Studio、Open WebUI、各类 SDK、脚本）把 `base_url` 指向本服务的
`/v1` 即可直接使用。

## 文档

- [docs/README.md](docs/README.md) —— 文档索引
- [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md) —— 本 fork 相对上游的改动记录
- [思考回放交接文档](docs/2026-09-18_reasoning-replay-handoff.md) —— 根因、修复、真实上游验证与待办
- [Codex / Claude Code 接入说明](docs/codex-integration.md) —— 经 CC Switch 协议转换接入
- 自检：`python docs/verify_reasoning_replay.py`（离线）、`python docs/probe_reasoning_replay.py replay|models`（真实链路）

---

*Happy coding!* 🎉
