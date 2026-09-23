# Fork 说明与变更记录

> 最后更新：2026-09-23

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
| 第二轮 | `df26a8c` | 一键启动脚本；移除 4 个上游已下架模型；文档校正（CC Switch 接入路线） |
| 第三轮 | `197218b` | 真流式转发（不再整体缓冲）；`usage` 透出（token 级可观测） |
| 第四轮 | `187b0e0` | `API_KEY` 兜底（`apikey.local`）；模型清单全量复测（补 `auto`、思考表 16→23） |
| 第五轮 | 本次 | **上游按内容拦截 Claude Code（11128）**：定位过程、A/B 证据、结论与替代方案 |

> 第四轮的文档校正（`README` / `docs/codex-integration.md` 等）与第五轮同批提交：
> 那批工作树改动按「代码 / 文档」拆成了两个提交。

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

## 第二轮：一键启动 + 模型清单校正 + 文档修正（`df26a8c`）

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

## 第三轮：真流式 + `usage` 透出（本次）

上游本项目自身的两个表现层问题（不是上游腾讯的），本轮修掉。

### 1. 真流式转发

**修复前**：`server.py` 用 `run_in_executor` 等 `chat_completion()` 收完**整个**上游响应，
再按空白切块、每块 `sleep(0.02)` 假装流式 —— 表现为「首字很慢，然后整段一次性刷出」。

**修复后**：上游增量一到就转发。

| 文件 | 位置 | 改动 |
|---|---|---|
| `codebuddy_direct_api.py` | `:417` | `_accumulate_tool_calls()`：流式 tool_calls 增量聚合（两条路径共用） |
| `codebuddy_direct_api.py` | `:577` | `_build_chat_body()`：请求体构造抽出，流式 / 非流式共用 |
| `codebuddy_direct_api.py` | `:735` | `chat_completion_stream()`：边收边 yield 的真流式接口 |
| `codebuddy_direct_api.py` | `:1106` | `_iter_sse_events()`：纯 SSE 解析器，产出 delta / usage / done 事件 |
| `codebuddy_direct_api.py` | `:1196` | `_parse_sse_stream()` 改为消费事件流，新增 `echo` 参数 |
| `server.py` | `:236` | 上游读取移入后台线程 + `asyncio.Queue`，事件到达即写 SSE |

重试只在「尚未产出任何增量」时进行（401 刷新 token / 429 / 5xx 退避）；
已经吐过内容再重试会导致重复，因此直接报错收尾。

**实测**（`deepseek-v4-pro`，裸 socket 计时）：69 次 TCP 推送、跨度 2.95s，
首个增量 1.408s、末次 2.952s —— 确认不再整体缓冲。

### 2. `usage` 透出

上游每个 SSE chunk 都带 `usage`，但原实现丢弃了它，`/v1/chat/completions` 永远返回
`{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}`。

现在：

- 非流式：`usage` 直接透出
- 流式：`finish_reason` 收尾块带 `usage`；`stream_options.include_usage` 为真时，
  按 OpenAI 规范再补一个 `choices: []` 的纯 usage 块（`server.py:174` 的 `normalize_usage()`，
  缺失时回退为 0，保持旧行为）

**顺带收益**：多轮思考回放现在可以做 token 级断言 —— A/B 的 `prompt_tokens`
70（无 reasoning）vs 90（带 reasoning），差值 20 正是折叠进去的思考。

### 3. 顺手修的既有 bug

`DEFAULT_THINKING` 环境变量此前被 `server.py` 读取却从未生效（流式路径默认值写死 `"max"`），
现已改为使用 `DEFAULT_THINKING_ENV`。

## 第四轮：`API_KEY` 兜底 + 模型清单全量复测（`187b0e0`）

### 背景问题

1. `API_KEY` 只在启动时从环境变量读，没设就**完全没有鉴权**。而服务默认绑 `0.0.0.0`，
   同局域网任何人都能白嫖 token 额度；设了又要每次手动 `$env:API_KEY=...`。
2. `/v1/models` 的清单是手工维护的，长期没复测，且和 WorkBuddy 客户端里的模型列表
   对不上——需要搞清哪一份可信。

### 1. `API_KEY` 兜底（`start.ps1` / `start.sh`）

优先级：**环境变量 `API_KEY` > 项目根目录 `apikey.local` > 自动生成并写入 `apikey.local`**。

- 文件不存在时生成 `sk-wb-<32 位随机>`；读取时去掉 BOM / CR / 首尾空白，
  避免不可见字符混进 HTTP header（PowerShell 的 `Set-Content -Encoding UTF8` 带 BOM，
  `[IO.File]::WriteAllText` + `UTF8Encoding($false)` 不带）。
- 启动 banner 每次都打印最终 key，方便抄进 CC Switch 的 apiKey 字段。
- `apikey.local` 已加入 `.gitignore`（与 `tokens.json` 同组）。

**实测**（8123 端口）：首次启动生成 → 二次启动复用同一 key → 无 key `401` /
错 key `403` / 对 key `200`；`/health` 的 `api_key_configured` 翻为 `true`。
注意 `/v1/models` 现在也走鉴权，用浏览器直接打开会 `401`（浏览器不发
`Authorization` 头），要 curl 带 key 或看 `/health`。

### 2. 模型清单全量复测：客户端那份目录才是陈旧的

`fetch_catalog()` 从 `list_models()` 里抽出来（读上游 `/v3/config`），探测脚本新增：

```bash
python docs/probe_reasoning_replay.py models --scope known --probe-thinking     # 复测已收录
python docs/probe_reasoning_replay.py models --scope catalog --probe-thinking   # 找漏
```

**实测结论（与直觉相反）**：

- 已收录的 25 个聊天模型 **24/24 可用，无一失效**（`hy3-preview-agent` 收费跳过）。
  「客户端有、本项目没有」的那 12 个（`deepseek-v4-pro`、`hy4-preview`、`kimi-k2.7`、
  `glm-5.2`…）是好的，该保留。
- 上游 `/v3/config`（客户端模型选择器读的同一份目录）里的 21 个未收录候选：
  **17 个已下架**（`glm-4.6`/`4.6v`、`glm-5.0`、`kimi-k2-thinking`、`minimax-m2.5`、
  `deepseek-v3-1`、`default-1.1/1.2` 等，返回 `model service info not found`）、
  **3 个是代码补全类非对话模型**（`codewise-jump`/`codewise-rewrite`/`codewise-nes-a4-027-aide`，
  对聊天请求只回一个空代码块），**只有 `auto` 可用**（由上游路由，实测落到混元、会出思考）。
- 所以清单只补了 `auto`（28 → 29），没收录 `codewise-*`。
- 顺带用 `reasoning_effort=low` 复测思考通道，`THINKING_CAPABLE_MODELS` 16 → 23：
  新增 `deepseek-r1-0528-lkeap`、`deepseek-v3-1-lkeap`、`glm-5.0-turbo`、`glm-5v-turbo`、
  `hy3`、`minimax-m2.7`、`auto`。这三个 `codewise-*` 与 `auto` 的实测明细写在
  `codebuddy_direct_api.py` 的注册表注释里。

> 之前文档把 `hy3-preview` 归为「无独立思考通道」，实测它会出 `reasoning_content`，
> 已在第三轮文档校正中一并修正。

### 3. 文档

- `README.md` / `README.en.md`：模型清单补 `auto`；把「2026-09-18 校正」的说明换成
  本次复测结论 + 「`/v3/config` 比可调用清单陈旧」的提醒；快速开始加 `API_KEY` 兜底说明。
- `docs/codex-integration.md`：模型推荐表按 2026-09-23 实测重写（三类：会思考 / 未见思考 /
  已下架）；API Key 填写说明改为「抄 banner」；第四节验证命令补鉴权；排错表加浏览器 401 一行。

## 第五轮：上游按内容拦截 Claude Code（11128）

### 现象

```
INFO:     127.0.0.1:58296 - "POST /v1/chat/completions HTTP/1.1" 200 OK
[!] API 错误 400: {"code":11128,"msg":"Illegal API invocation from an unapproved channel", ...}
```

两个容易误判的点：本地 HTTP 状态已是 200（流式响应头早就发出去了，上游的 400 只能藏在流里）；
非流式路径会被吞成 `502 {"detail":"Upstream API returned empty response"}`，完全看不出是风控。

### 定位：单变量 A/B

固定 key / `model=deepseek-v4-pro` / `stream=true`，**只改 messages**，逐条直连上游：

| 请求内容 | 上游结果 |
|---|---|
| 裸 `hi`；中性中/英文 system；带 `Bash` 工具定义；中文提问 | 200 |
| system 里单独出现 `Anthropic`、或 `你叫 Claude，由 Anthropic 开发。` | 200 |
| **system = `You are Claude Code, Anthropic's official CLI for Claude.`** | **400 / 11128** |

再固定内容只换入口：同一句从**代码直连**、**经本地服务 `127.0.0.1:8000`**（CC Switch 走的同一条）
都被拦；中性提示词两条入口都通。

**结论**：上游按**内容指纹**识别客户端身份，与 header / API Key / 模型 / 入口无关；
同一条请求重复发每次都拦，不是限流，`retry later` 那句提示有误导性。

### 影响与处置

- **本项目不能给 Claude Code 用**（Claude Code 的每个请求都带那句身份）；Codex 与提示词中性的
  客户端不受影响。`README` / `docs/codex-integration.md` 的 Claude Code 相关表述已全部更正。
- 11128 的 msg 是「unapproved channel」：这是上游在执行「非官方渠道不得调用订阅额度」的策略，
  腾讯云治理公告明确可停用 AI 资源权限 —— 风险落在使用者账号上。
- **本仓库明确不做**「改写 / 删除身份句」之类的伪装绕过（规避上游风控），只记录结论与替代方案。

### 文档

- 新增 [2026-09-23_upstream-11128-claude-code-block.md](2026-09-23_upstream-11128-claude-code-block.md)：
  完整证据表、复现脚本、来源链接、替代方案。
- `docs/codex-integration.md`：一句话结论改为「Codex 可以，Claude Code 不行」+ 警示框，
  排错表加 11128 两行；`docs/README.md` 索引加新文档。

## 与上游同步时注意

- **不要把本项目接到 Claude Code**：上游按内容指纹识别客户端身份，见到 Claude Code 的系统提示词
  首句就返回 `11128`（见上面的第五轮）。这不是本项目的缺陷，也不要为它做提示词伪装——
  那属于规避上游风控，风险在账号上。
- `codebuddy_direct_api.py` 的改动集中在 `replay_reasoning()` 及其调用点，
  上游若重构 `chat_completion()` 的请求体组装，需重新确认折叠逻辑仍在发送前生效。
- `KNOWN_CHAT_MODELS` / `THINKING_CAPABLE_MODELS` 是单一数据源（`/v1/models` 与 CLI 共用），
  上游新增模型时直接合并即可。**别信 `/v3/config`**（客户端目录，已下架的 17 个模型仍在其中），
  候选一律先跑 `python docs/probe_reasoning_replay.py models --scope catalog --probe-thinking`
  实测，通过的才收录。
- `API_KEY` 兜底只实现在两个启动脚本里；直接 `python server.py` 或走 Docker 时仍只有环境变量
  一条路径，`apikey.local` 不会被读取。
- `chat_completion()` 仍是「收完再返回」的兼容接口；服务端流式走 `chat_completion_stream()`。
  上游若改了 SSE 事件名（`event: conversationId`）或 `[DONE]` 语义，改 `_iter_sse_events()` 一处即可。
- 自检：`python docs/verify_reasoning_replay.py`（离线，期望 `9/9 passed`）。