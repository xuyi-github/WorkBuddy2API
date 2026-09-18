# 🚀 WodeBuddy2API

Wrap WorkBuddy's internal API into an **OpenAI-compatible REST API** — deploy in one line, call from anywhere.

> 中文版: [README.md](README.md)
>
> This is a fork of [Tom6814/WorkBuddy2API](https://github.com/Tom6814/WorkBuddy2API).
> See [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md) for what this fork changes.

---

## What is this?

A featherweight proxy that turns WorkBuddy's internal API into a standard **OpenAI-compatible REST API**. Every model you can use in WorkBuddy — DeepSeek, Kimi, GLM, Hunyuan, MiniMax and more — becomes available through the familiar OpenAI interface. Any tool that speaks OpenAI API (Claude Code, custom clients, scripts…) can now drive WorkBuddy models directly.

## Highlights

- ✨ **Fully OpenAI-compatible** — `/v1/chat/completions`, `/v1/models`, tools/tool_calls passthrough
- 🧠 **Reasoning content** — `reasoning_content` (thinking process) exposed
- 🔁 **Multi-turn reasoning replay** — the upstream drops historical `reasoning_content`, so it is folded into `content` before sending
- 🚀 **Max thinking by default** — deep reasoning even with zero extra params
- ⚡ **True streaming** — SSE deltas forwarded as they arrive; first-token latency = upstream
- 📊 **Usage reporting** — `usage` in responses and in the streaming final chunk
- 🖼️ **Image generation** — text-to-image `/v1/images/generations`, image editing `/v1/images/edits`
- 🔄 **Auto token refresh** — no manual intervention
- 🛡️ **Anti-ban protection** — rate limiting, jitter, UA rotation, exponential backoff
- 🐳 **One-line deploy** — Docker / Zeabur / Railway ready

## Quick Start

### 1. Get the WodeBuddy Token

After logging into WorkBuddy, the token is stored locally:

```bash
cat ~/Library/Application\ Support/CodeBuddyExtension/Data/Public/auth/workbuddy-desktop.info
```

### 2. Run locally

One-command start (installs deps if needed, pre-checks the token):

```powershell
# Windows
.\start.ps1                     # defaults to port 8000
.\start.ps1 -Port 9000          # custom port
```

```bash
# Linux / macOS
./start.sh                      # defaults to port 8000
PORT=9000 ./start.sh
```

Or start it manually:

```bash
pip install fastapi uvicorn
export CODEBUDDY_AUTH_TOKEN="your-token"
export API_KEY="your-own-key"
python server.py
```

### 3. Deploy to Zeabur / Railway / any Docker platform

Only two env vars are required:

| Variable | Required | Description |
|----------|----------|-------------|
| `CODEBUDDY_AUTH_TOKEN` | ✅ | WorkBuddy Bearer Token |
| `API_KEY` | ✅ | Key for calling this API |
| `DEFAULT_MODEL` | ❌ | Default model, default `deepseek-v3` |
| `DEFAULT_THINKING` | ❌ | Default thinking level, default `max` |
| `REPLAY_REASONING` | ❌ | Fold historical reasoning into `content` for replay, on by default (set to `0` to disable) |
| `PORT` | ❌ | Listen port, default `8000` |

> Token resolution order: `CODEBUDDY_AUTH_TOKEN` env var > `--auth-file` > `tokens.json` in the project root > local WorkBuddy auth file.
> See [tokens.example.json](tokens.example.json) for the `tokens.json` shape (`tokens[].token_info.access_token`);
> the file is already in `.gitignore` — **never commit a real token**.

## Multi-turn Reasoning Replay

The upstream `/v2/chat/completions` gateway only deserializes whitelisted fields
(`role` / `content` / `tool_calls`) from `messages`, so `reasoning_content` on
historical assistant messages is silently dropped:

- Injecting 500 characters of thinking into the previous assistant message adds exactly 0
  `prompt_tokens` on the next turn;
- A passphrase planted in the previous turn's thinking is completely invisible to the model.

This proxy therefore folds historical assistant reasoning into `content` before sending, so
it reaches the base model's Chat Template along with the rest of the history:

```text
<thinking>
previous turn reasoning
</thinking>

previous turn answer
```

Behavior:

- Only `assistant` messages are touched; `user` / `system` messages pass through untouched
- Accepts `reasoning_content` / `reasoning` / `thinking` (including Anthropic-style thinking blocks)
- Idempotent: a `content` that already inlines the same reasoning is not injected twice
- Non-string `content` (multimodal blocks) is left as-is
- Set `REPLAY_REASONING=0` if you want downlink-only reasoning without replay

## Usage Examples

**Chat (streaming, max thinking by default):**

```bash
curl https://your-domain/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kimi-k3-1",
    "messages": [{"role": "user", "content": "Write a quicksort in Python"}]
  }'
```

**Custom thinking level:**

```bash
-d '{"model": "deepseek-v3", "messages": [...], "reasoning_effort": "high"}'
```

`reasoning_effort`: `low` | `medium` | `high` | `max` | `off`

**Streaming with token usage:**

```bash
-d '{
  "model": "deepseek-v4-pro",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": true,
  "stream_options": {"include_usage": true}
}'
```

With `stream_options.include_usage` set, an extra chunk with `choices: []` and only `usage` is emitted before `[DONE]` (OpenAI spec).

**Tool calling:**

```bash
-d '{
  "model": "glm-5.2",
  "messages": [{"role": "user", "content": "What is the weather today?"}],
  "tools": [{"type": "function", "function": {"name": "get_weather", "description": "Get weather", "parameters": {...}}}]
}'
```

**Text-to-image:**

```bash
curl https://your-domain/v1/images/generations \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a cute orange cat, cartoon style", "model": "hunyuan-image-v3.0"}'
```

**Image editing:**

```bash
curl https://your-domain/v1/images/edits \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "make it blue", "image": "data:image/png;base64,..."}'
```

`image` accepts: data URL / http(s) URL / raw base64 / local file path.

## Available Models

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
hy3                hy3-preview (free)      hy3-preview-agent (paid)
hy4-preview (free trial 0.00, 0.04/use beyond quota)

# Image
hunyuan-image-v3.0                        (text-to-image)
hunyuan-image-v3.0-art                    (text-to-image, artistic style)
hunyuan-image-v2.0-general-edit           (image-to-image)
```

> You can also get the full model list anytime via `GET /v1/models`.

> The list was corrected against a live upstream check on 2026-09-18: four models no longer served
> upstream were removed (`deepseek-r1-0528`, `deepseek-v3-1`, `glm-4.7`, `glm-5.0`). See
> [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/v1/models` | List all supported models |
| `POST` | `/v1/chat/completions` | Chat completion (SSE streaming) |
| `POST` | `/v1/images/generations` | Text-to-image |
| `POST` | `/v1/images/edits` | Image editing |

## Project Structure

```
codebuddy-api-server/
├── server.py                 # OpenAI-compatible REST API server
├── codebuddy_direct_api.py   # Direct CodeBuddy client (token/SSE/image)
├── start.ps1 / start.bat     # one-command start (Windows)
├── start.sh                  # one-command start (Linux / macOS)
├── Dockerfile                # Python 3.11 container
├── docs/                     # Handoff docs and self-check scripts
└── README.md
```

## Using with Codex / Claude Code

**It works, and this project needs no code changes.**

Codex 0.155.0 only speaks the Responses API (`wire_api = "responses"`), while this project only
exposes `/v1/chat/completions`. The gap is bridged by **CC Switch's local proxy**: add this server
as a provider with `apiFormat = openai_chat`, and CC Switch converts Codex's Responses requests /
Claude Code's Anthropic requests into Chat Completions before forwarding them here.

```text
Start this server ( .\start.ps1 )
        |
        v
CC Switch: add provider  apiFormat = openai_chat
                         base_url = http://127.0.0.1:8000/v1
        |
        v
Switch provider  ->  Codex (via 127.0.0.1:10001) / Claude Code are ready to use
```

Field-by-field setup, verification and troubleshooting: [docs/codex-integration.md](docs/codex-integration.md).

Any other OpenAI-compatible client (Cherry Studio, Open WebUI, SDKs, scripts) can point its
`base_url` at this server's `/v1` and work right away.

## Documentation

- [docs/README.md](docs/README.md) — documentation index
- [docs/FORK-CHANGES.md](docs/FORK-CHANGES.md) — what this fork changes vs. upstream
- [Reasoning replay handoff](docs/2026-09-18_reasoning-replay-handoff.md) — root cause, fix, real-upstream verification, todos
- [Codex / Claude Code integration](docs/codex-integration.md) — via CC Switch protocol translation
- Self-checks: `python docs/verify_reasoning_replay.py` (offline), `python docs/probe_reasoning_replay.py replay|models` (live)

---

*Happy coding!* 🎉
