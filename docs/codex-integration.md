# 在 Codex 中使用这些模型

## 结论（先看这里）

**目前不能直接接入。** Codex 0.155.0 只支持 Responses API（`wire_api` 的合法取值只有
`responses`），而本项目只提供 Chat Completions（`/v1/chat/completions`）。要接入需要先给
`server.py` 增加 `POST /v1/responses` 适配层，实现清单见下文。

其他 OpenAI 兼容客户端（Cherry Studio、Open WebUI、各类 SDK、脚本）不受此限制，把
`base_url` 指到本服务的 `/v1` 即可直接用。

## 实测证据（2026-09-18）

`wire_api` 的合法取值（用一个临时 `CODEX_HOME` 把值写成非法即可看到枚举）：

```text
$ codex exec --skip-git-repo-check "hi"
Error loading config.toml: unknown variant `bogus`, expected `responses`
in `model_providers.custom.wire_api`
```

本机 `127.0.0.1:10001` 上跑的是 **CC Switch** 的本地代理（不是本项目），它转发到的上游
provider 目前返回 401，所以 Codex 现在这条链路是断的：

```text
GET  http://127.0.0.1:10001/v1/models      -> {"models":[]}
GET  http://127.0.0.1:10001/health         -> {"status":"healthy",...}
POST http://127.0.0.1:10001/v1/responses   -> HTTP 401
     "CC Switch local proxy failed while handling Codex endpoint /responses.
      Provider: agent-hx-ds-v4 copy; model: deepseek-v4-flash;
      upstream_status: HTTP 401; cause: unauthorized client detected, ..."
```

## 适配完成后的 Codex 配置

1. 启动本服务：

```bash
export CODEBUDDY_AUTH_TOKEN="<your token>"   # 或把 token 放进 tokens.json
export API_KEY="<your own key>"
python server.py                             # 默认 8000 端口
```

2. 在 `~/.codex/config.toml` 里**新增**一个 provider 和 profile（不要覆盖你已有的 CC Switch 配置，
   两者可以并存），把 `wire_api` 设成 `responses`：

```toml
[model_providers.workbuddy]
name = "WorkBuddy"
base_url = "http://127.0.0.1:8000/v1"
wire_api = "responses"
env_key = "WORKBUDDY_API_KEY"

[profiles.workbuddy]
model = "deepseek-v4-pro"          # 实测有 reasoning_content 下行
model_provider = "workbuddy"
model_reasoning_effort = "high"
```

3. 设置密钥并启动：

```bash
export WORKBUDDY_API_KEY="<your API_KEY>"
codex --profile workbuddy
# 或临时覆盖：codex -c model_provider=workbuddy -m deepseek-v4-pro
```

模型名直接用 `/v1/models` 返回的名字（如 `deepseek-v4-pro`、`glm-5.1`、`kimi-k2.7`）。
想看到思考过程，优先选实测有 `reasoning_content` 下行的模型；`deepseek-v3` 与 `hy3-preview`
本身没有独立思考通道。另有 4 个模型上游已下架，见交接文档 F-004。

## `server.py` 需要新增什么

Responses API 与 Chat Completions 的差异需要翻译，建议复用现有
`ApiClient.chat_completion()`（已包含 token 管理与思考折叠），只在 `server.py` 做协议层。

| 方向 | 处理要点 |
|------|----------|
| 请求 | `input`（字符串或 item 数组）→ `messages`；`instructions` → `system`；`max_output_tokens` → `max_tokens`；`reasoning.effort` → `reasoning_effort` |
| 请求（工具） | Responses 的扁平 `tools[]` → Chat Completions 的 `{type, function: {...}}` |
| 请求（有状态） | 关注 `store` / `previous_response_id`；本项目无服务端状态，需忽略或按无状态回退 |
| 响应（流式） | 至少实现 `response.created`、`response.output_item.added`、`response.content_part.added`、`response.output_text.delta`、`response.completed`；思考内容走 reasoning 相关 item 事件（以 `codex` 实际请求为准） |
| 响应（非流式） | 组装 `{id, object: "response", status: "completed", output: [{type: "message", content: [{type: "output_text", text}]}], usage}` |
| 错误 | 用 Responses 的错误结构返回，HTTP 状态码保持一致 |
| usage | 上游每个 SSE chunk 都带 `usage`，适配层可顺带把它透出 |

## 回归验证步骤

1. `python docs/verify_reasoning_replay.py` —— 确认适配没有破坏思考折叠逻辑。
2. 先测非流式 `POST /v1/responses` 的返回结构，再测流式事件序列。
3. `codex exec --skip-git-repo-check "say hi"` 走通最小闭环。
4. `python docs/probe_reasoning_replay.py replay` —— 多轮思考仍然生效。