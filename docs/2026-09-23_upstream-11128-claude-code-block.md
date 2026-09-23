# 上游按「内容」拦截 Claude Code（错误码 11128）

> 排查日期：2026-09-23 ｜ 相关：[文档索引](README.md) ｜ [Fork 变更记录](FORK-CHANGES.md) ｜ [Codex / Claude Code 接入](codex-integration.md)

## 一句话结论

`copilot.tencent.com` 的网关会**按请求内容识别客户端身份**：只要 `messages` 里带上 Claude Code
系统提示词的首句（`You are Claude Code, Anthropic's official CLI for Claude.`），上游就返回

```json
{"code":11128,"msg":"Illegal API invocation from an unapproved channel",
 "displayMsg":{"zh":"请求被安全策略拦截，请稍后重试或联系支持。"}}
```

**所以本项目不能给 Claude Code 用**——不是配置问题，换 header / API Key / 模型 / 入口都无用，
变量只在 `content` 里。Codex 与其他提示词中性的客户端不受影响。

## 现象与两个易误判点

```
INFO:     127.0.0.1:58296 - "POST /v1/chat/completions HTTP/1.1" 200 OK
[!] API 错误 400: {"code":11128,"msg":"Illegal API invocation from an unapproved channel", ...}
```

- **本地状态码是 200**：流式响应的响应头在收到上游结果前就已经发出去了，上游的 400 只能藏在流里
  （`codebuddy_direct_api.py` 的 `chat_completion_stream()` 打印到 stderr 并 yield 一个 error 事件）。
  非流式路径下则会被吞成 `502 {"detail":"Upstream API returned empty response"}`，完全看不出是风控——
  这也是本文开头被误判为「服务坏了」的原因。
- 两条报错的 `requestId` 相同：因为我们发给上游的 `X-Request-ID` 是**会话级**的
  （`ApiClient._session_id`），不是每请求一个；相同 ≠ 上游去重。

## 定位过程：单变量 A/B

固定 key、`model=deepseek-v4-pro`、`stream=true`、`max_tokens=16`，**只改 messages**，逐条直连上游：

| # | 请求内容（system / user） | 上游结果 |
|---|---|---|
| A | 无 system，user = `hi` | 200 |
| B | system = 中性中文（`你是一个乐于助人的助手。`） | 200 |
| C | system = 中性英文（`You are a helpful assistant.`） | 200 |
| D | 无 system + `Bash` 工具定义 | 200 |
| E | 中性 system + `Bash` 工具定义 | 200 |
| F | user 消息里提到 `Anthropic` | 200 |
| G | system 只有一个词：`Anthropic` | 200 |
| H | system = `你叫 Claude，由 Anthropic 开发。` | 200 |
| I | system = 含 `Anthropic` 的中性长句 | 200 |
| **J** | **system = `You are Claude Code, Anthropic's official CLI for Claude.`** | **400 / 11128** |

再固定内容、只换入口，确认与入口无关：

| 入口 | 中性提示词 | 带 J 那句身份串 |
|---|---|---|
| 代码直连上游（python） | 200 | **400 / 11128** |
| 经本地服务 `127.0.0.1:8000`（CC Switch 走同一条） | 200 | 上游 400，本地表现为 502 / 流内错误 |

补充：同一条 J 请求重复发送**每次都拦**，是确定性匹配，不是限流——上游提示语里的
「请稍后重试」具有误导性，等下去不会恢复。

## 结论

- **不是本项目的 bug，也不是 CC Switch 的 bug**：我们发出的上游请求根本不带 `User-Agent`
  （见 `_build_headers()` 注释），API Key、模型、并发、超时都不是变量。
- **是上游在按渠道策略拒绝**。`msg` 写的是「unapproved channel」；腾讯云治理公告明确把
  「经由 WorkBuddy / CodeBuddy 之外的客户端、SDK 或直连 HTTP 调用 AI 资源」列为违规，
  处置手段包括停用 AI 资源权限。
- 外界旁证：OmniRoute 的 [#12702](https://github.com/diegosouzapw/OmniRoute/issues/12702) /
  [PR #13264](https://github.com/diegosouzapw/OmniRoute/pull/13264) 报告了同码错误，
  他们那条触发路径是 **User-Agent 不一致**（OAuth 与 chat 用了不同版本号）；我们这条是**内容指纹**。
  同一个 11128 之下可能有多套判定，但都指向「识别非官方客户端」。
- Claude Code 的**每一个**请求都会带那句身份（它是 CC 系统提示词的第一行），
  因此无论经 CC Switch、直连本地服务还是直连上游，都会被拦。

## 本项目不做什么

**不做「改写 / 删掉身份句」之类的伪装绕过。** 那是规避上游风控，且按上述公告可能被停用
AI 资源权限——风险落在使用者自己的账号上。本文只记录排查与结论，不提供绕过手法。

## 替代方案

| 目标 | 建议 |
|---|---|
| 在 Claude Code 里用模型 | 选一个支持第三方接入的 provider，**不要**经由本项目 |
| 就是想要 WorkBuddy 的模型 | 官方客户端；或腾讯官方 OpenAPI（`api.copilot.tencent.com`，API key 通道） |
| 用本项目 | Codex / 其他 OpenAI 兼容客户端 / 自己的脚本都可以——前提是 messages 里不含上面那句身份串 |

> 注意第三行仍是同一灰色地带：风控是内容指纹式的，今天匹配的是 Claude Code 的身份串，
> 随时可能扩到别的 harness（Codex、droid、Kimi Code 等各自的提示词），也可能按调用量收紧。
> 不要把关键流程压在这上面。

## 复现方法

把下面的脚本存成临时文件跑（需要项目根目录有可用 token；会真实调用上游，注意额度）：

```python
import json, ssl, sys, time, http.client
sys.path.insert(0, ".")                     # 项目根目录
import codebuddy_direct_api as m

client = m.ApiClient(m.DEFAULT_API_BASE, m.find_and_load_token())

def probe(label, system=None, text="hi"):
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": text}]
    body = {"model": "deepseek-v4-pro", "messages": msgs, "max_tokens": 16, "stream": True}
    conn = http.client.HTTPSConnection(client.hostname, 443,
                                       context=ssl.create_default_context(), timeout=60)
    conn.request("POST", m.CHAT_COMPLETIONS_PATH, body=json.dumps(body),
                 headers=client._build_headers(stream=True, model="deepseek-v4-pro"))
    resp = conn.getresponse()
    print(f"[{label}] -> {resp.status} | {resp.read(400).decode('utf-8','replace')[:160]}")
    conn.close(); time.sleep(m.MIN_REQUEST_INTERVAL + 1)

probe("对照：中性 system", system="你是一个乐于助人的助手。")
probe("命中：CC 身份 system", system="You are Claude Code, Anthropic's official CLI for Claude.")
```

预期：第一条 `200`，第二条 `400`（`code: 11128`）。

## 来源

- OmniRoute [issue #12702](https://github.com/diegosouzapw/OmniRoute/issues/12702) /
  [PR #13264](https://github.com/diegosouzapw/OmniRoute/pull/13264)：同码 11128，UA 不一致路径
- 腾讯云云开发[《关于「小程序成长计划 AI 资源包」使用范围的专项治理公告》](https://docs.cloudbase.net/ai/ai-inspire-plan-rules)：
  把 WorkBuddy / CodeBuddy 之外渠道的调用列为违规，可停用 AI 资源权限
- 腾讯云 [CodeBuddy 防火墙配置](https://cloud.tencent.cn/document/product/1831/134363)：`copilot.tencent.com` 域名与端口
- 腾讯开发者问答「[codebuddy 对话总是报 request illegal](https://developer.cloud.tencent.cn/ask/2211596)」

> 本文结论是 **2026-09-23 的快照**。上游策略可能双向变化（收紧到更多签名，或放开）；
> 复现脚本可以随时重跑验证当时的实际行为。
