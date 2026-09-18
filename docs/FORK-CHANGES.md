# Fork 说明与变更记录

> 最后更新：2026-09-19

## 这是什么

本仓库是 **[Tom6814/WorkBuddy2API](https://github.com/Tom6814/WorkBuddy2API)** 的
**个人 fork**（GitHub 上 `fork: true`，parent 为 `Tom6814/WorkBuddy2API`），
用于个人自用与实验，**不是上游官方版本**。

| 项 | 值 |
|---|---|
| 上游（原始仓库） | https://github.com/Tom6814/WorkBuddy2API |
| 本 fork | https://github.com/xuyi-github/WorkBuddy2API |
| 同步基线 | 上游 `297516f`（docs: clarify hy4-preview dual pricing） |
| 分支 | `main` |

上游的通用部署说明请直接看上游 README；本文件只记录**本 fork 相对上游做了什么**。

## 变更总览

| 轮次 | 提交 | 主题 |
|---|---|---|
| 第一轮 | `bcf7650` | 修复多轮对话中历史思考被丢弃；接入 `tokens.json`；Windows 桌面端 auth 路径 |
| 第二轮 | 本次 | 一键启动脚本；移除 4 个上游已下架模型；文档校正（CC Switch 接入路线） |

---

## 第一轮：思考回放修复 + `tokens.json` 接入（`bcf7650`）

### 背景问题

把本项目作为支持思考链的客户端（DeepSeek Harness、OpenCode、Claude Code、Cherry Studio 等）
的反代接入时，多轮对话会出现「上一轮的思考过程被丢弃」：

- **下行正常**：流式 SSE 能输出思考过程，客户端正常渲染折叠块（`reasoning_content` 透传没问题）。
- **上行丢失**：下一轮客户端回传的 `reasoning_content` 被上游静默丢弃。

### 真实环境验证

直连 `copilot.tencent.com/v2/chat/completions` 做 A/B 对比（上一轮 assistant 历史里植入暗号 `ZEBRA-9173`）：

| 组 | 发给上游的 assistant content | `prompt_tokens` | 模型回答 |
|---|---|---|---|
| A 折叠回放（修复后） | `<thinking>` + 暗号 + `</thinking>` + 原文 | **64** | `ZEBRA-9173` ✅ |
| B 原始发送（修复前） | 仅原文 | 44 | 「你刚才没有告诉我任何暗号。」❌ |

`prompt_tokens` 差值 20 ⇒ 折叠后的思考确实进入了底座编码；B 组复现了原始缺陷。

### 根因

上游网关在向底座模型组装 Jinja / Chat Template 时，只读取 `role` / `content` / `tool_calls`
等白名单字段，消息上的 `reasoning_content` 不参与渲染。

### 改动

| 文件 | 位置 | 改动 |
|---|---|---|
| `codebuddy_direct_api.py` | `:125` | `REPLAY_REASONING` / `REASONING_TAG` / `REASONING_FIELDS` 配置 |
| `codebuddy_direct_api.py` | `:352` | `extract_reasoning()`：兼容 `reasoning_content` / `reasoning` / `thinking`（含 Anthropic thinking 块） |
| `codebuddy_direct_api.py` | `:373` | `replay_reasoning()`：把 assistant 历史思考折叠进 `content`，幂等、不改入参、多模态块跳过 |
| `codebuddy_direct_api.py` | `:577` | 唯一调用点（`ApiClient.chat_completion()` 组装请求体处），流式 / 非流式共用 |
| `codebuddy_direct_api.py` | `:1092` | CLI 多轮历史保留 `reasoning_content`，下一轮由同一逻辑回放 |
| `codebuddy_direct_api.py` | `:91` | `TOKENS_FILE`（默认项目根目录 `tokens.json`，可用 `WORKBUDDY_TOKENS_FILE` 覆盖） |
| `codebuddy_direct_api.py` | `:257` | `extract_token_from_tokens_file()` 并从 JWT 推导 `user_id` / `domain` / 过期时间 |
| `codebuddy_direct_api.py` | `:308` | `find_and_load_token()` 接入 `tokens.json`，加载优先级：env > `--auth-file` > `tokens.json` > 桌面端 auth 文件 |
| `codebuddy_direct_api.py` | `:67` / `:74` | `AUTH_FILE_PATHS` 补 Windows 桌面端路径（`%APPDATA%` / `%LOCALAPPDATA%`） |
| `server.py` | `:82` / `:93` | 改为懒初始化，不再因缺少 `CODEBUDDY_AUTH_TOKEN` 而放弃初始化客户端 |
| `server.py` | `:309` | `/health` 的 `codebuddy_configured` 改为反映真实客户端状态 |
| `docs/` | 新增 | 交接文档、Codex 接入说明、`verify_reasoning_replay.py`、`probe_reasoning_replay.py` |

### 为什么必须动 `tokens.json` 相关代码

改动前 `find_and_load_token()` 只认 `CODEBUDDY_AUTH_TOKEN` 环境变量和桌面端
`workbuddy-desktop.info`，仓库里的 `tokens.json` **从未被任何代码读取**；`server.py` 还用环境变量
做了前置判断。所以「填好 `tokens.json` 就能跑」在原代码下不成立（表现为 503 或
`codebuddy_configured: false`）。

`tokens.json` 结构（取第一个带 `token_info` 的条目，`name` 任意）：

```json
{
  "tokens": [{"name": "any-name", "token_info": {"access_token": "<YOUR_TOKEN>"}}],
  "updated_at": "1970-01-01T00:00:00"
}
```

该文件已在 `.gitignore` 中，**不要提交真实 token**。

---

## 第二轮：一键启动 + 模型清单校正 + 文档修正（本次）

### 1. 一键启动脚本

上游只有「手装依赖 + `python server.py`」的手动流程，本 fork 补了三个入口：

| 文件 | 平台 | 说明 |
|---|---|---|
| `start.ps1` | Windows | 自动定位 `python` / `py`，检查并按需安装 `fastapi`+`uvicorn`，预检 token，启动 uvicorn；支持 `-Port` / `-BindHost` / `-SkipInstall` |
| `start.bat` | Windows | 双击入口，转调 `start.ps1` |
| `start.sh` | Linux / macOS | 同上逻辑；支持 `PORT` / `HOST` 环境变量 |

用法：

```powershell
.\start.ps1                 # 默认 8000
.\start.ps1 -Port 9000
```

```bash
./start.sh
PORT=9000 ./start.sh
```

### 2. 移除 4 个上游已下架的模型

2026-09-18 用 `python docs/probe_reasoning_replay.py models` 实测，
以下 4 个模型上游返回 `model [...] service info not found`，已从
`THINKING_CAPABLE_MODELS` 与 `KNOWN_CHAT_MODELS` 中移除：

`deepseek-r1-0528`、`deepseek-v3-1`、`glm-4.7`、`glm-5.0`

> 注意保留了 `deepseek-r1-0528-lkeap`、`deepseek-v3-1-lkeap`、`glm-5.0-turbo`，
> 这几个名字相近但**实测可用**。
>
> 实测结果：可用 24 / 不可用 4 / 跳过 1（`hy3-preview-agent` 收费未测）。
> `/v1/models` 现在返回 28 个模型。

### 3. 文档校正：Codex 接入路线

原 `docs/codex-integration.md` 的结论是「Codex 无法接入，需要先给 `server.py`
实现 `/v1/responses`」。该结论只考虑直连场景，**没有考虑 CC Switch 的协议转换能力**，
现已重写为「本项目 + CC Switch 本地代理」路线：

> CC Switch 支持把 `apiFormat` 为 `openai_chat` 的服务当作上游，自动把 Codex 的
> Responses 请求 / Claude Code 的 Anthropic 请求转换成 Chat Completions 再转发。
> 因此本项目**不需要**实现 `/v1/responses`。

详见 [codex-integration.md](codex-integration.md)。

### 4. 新增本文件

`README.md` / `README.en.md` 的模型清单段落改为引用本文件，便于后来者一眼看出
「这是 fork，改了哪些东西」。

---

## 与上游同步时注意

- `codebuddy_direct_api.py` 的改动集中在 `replay_reasoning()` 及其调用点，
  上游若重构 `chat_completion()` 的请求体组装，需重新确认折叠逻辑仍在发送前生效。
- `KNOWN_CHAT_MODELS` / `THINKING_CAPABLE_MODELS` 是单一数据源（`/v1/models` 与 CLI 共用），
  上游新增模型时直接合并即可，注意别把已下架的 4 个模型带回来。
- 自检：`python docs/verify_reasoning_replay.py`（离线，期望 `7/7 passed`）。