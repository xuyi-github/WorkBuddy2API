# -*- coding: utf-8 -*-
"""真实上游探测脚本（需要 token：tokens.json 或 CODEBUDDY_AUTH_TOKEN）。

子命令：

  replay  思考回放 A/B 对比 —— 验证历史 reasoning_content 是否真的进入底座上下文
  models  扫描模型可用性（--scope 选扫描范围）

用法::

    python docs/probe_reasoning_replay.py replay
    python docs/probe_reasoning_replay.py models                  # 只扫 KNOWN_CHAT_MODELS
    python docs/probe_reasoning_replay.py models --scope catalog  # 扫「上游目录有、清单里没有」的候选
    python docs/probe_reasoning_replay.py models --scope all --probe-thinking

退出码：replay 通过为 0，未通过为 1；models 始终为 0，仅报告结果。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import codebuddy_direct_api as m  # noqa: E402

SECRET = "ZEBRA-9173"

# 明确收费的模型默认跳过，避免产生费用
# default-1.1 / default-1.2 是客户端目录里的 Claude-3.7 / 4.0-Sonnet 转售档，单价最高
PAID_MODELS = {"hy3-preview-agent", "default-1.1", "default-1.2"}


def _client() -> m.ApiClient:
    return m.ApiClient(m.DEFAULT_API_BASE, m.find_and_load_token(), safe_mode=False)


def _post(client: m.ApiClient, payload: dict) -> tuple[int, str]:
    headers = client._build_headers(stream=True, model=payload["model"])
    client.rate_limiter.wait()
    conn = client._get_connection()
    conn.request("POST", m.CHAT_COMPLETIONS_PATH, body=json.dumps(payload), headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    client._reset_connection()
    return resp.status, raw


def _parse_sse(raw: str) -> tuple[str, str, dict | None]:
    content = reasoning = ""
    usage = None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        for choice in (obj.get("choices") or []):
            delta = choice.get("delta") or {}
            content += delta.get("content") or ""
            reasoning += delta.get("reasoning_content") or ""
    return content, reasoning, usage


def cmd_replay(args: argparse.Namespace) -> int:
    """A/B 对比：同一暗号场景，折叠回放 vs 原始发送。"""
    client = _client()
    history = [
        {"role": "user", "content": "请记住一个暗号，我稍后会问你。"},
        {"role": "assistant", "content": "好的，请告诉我暗号。",
         "reasoning_content": "用户要我记住的暗号是 {}。".format(SECRET)},
    ]
    question = {"role": "user",
                "content": "我刚才让你记住的暗号是什么？只回答暗号本身，不要任何解释。"}

    cases = (
        ("A_折叠回放", m.replay_reasoning(history + [question])),
        ("B_原始发送", history + [question]),
    )

    results = {}
    for label, messages in cases:
        payload = {
            "model": args.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": args.max_tokens,
            "stream": True,
        }
        if args.model in m.THINKING_CAPABLE_MODELS:
            payload["reasoning_effort"] = m.THINKING_LEVELS["low"]
        status, raw = _post(client, payload)
        if status != 200:
            print("[!] {} 返回 HTTP {}: {}".format(label, status, raw[:300]))
            return 1
        content, reasoning, usage = _parse_sse(raw)
        prompt_tokens = (usage or {}).get("prompt_tokens")
        recalled = SECRET in content or SECRET in reasoning
        results[label] = (prompt_tokens, recalled)
        print("{:10s} prompt_tokens={!s:>5s}  答出暗号={}".format(label, prompt_tokens, recalled))
        print("           answer = {!r}".format(content.strip()[:120]))

    a_tokens, a_recalled = results["A_折叠回放"]
    b_tokens, b_recalled = results["B_原始发送"]
    print("-" * 64)
    if isinstance(a_tokens, int) and isinstance(b_tokens, int):
        print("prompt_tokens 差值 (A - B) = {}".format(a_tokens - b_tokens))
    if a_recalled and not b_recalled:
        print("判定：PASS —— 折叠后思考进入上下文，原始发送复现丢弃")
        return 0
    print("判定：FAIL —— A 答出={} B 答出={}".format(a_recalled, b_recalled))
    return 1


def _extract_error(raw: str) -> str:
    """从响应体里抠出上游错误信息（非 200 的 JSON 体，或 SSE 里的错误事件）。"""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("error"):
            err = obj["error"]
            return str(err.get("message") if isinstance(err, dict) else err)[:200]
        if obj.get("msg") or obj.get("displayMsg"):
            display = obj.get("displayMsg") or {}
            detail = display.get("zh") if isinstance(display, dict) else display
            return str(obj.get("msg") or detail)[:200]
    return raw.strip()[:120]


def _catalog_ids(client: m.ApiClient) -> set[str]:
    """上游 /v3/config 目录里的全部模型 id。"""
    return {c.get("id", "") for c in m.fetch_catalog(client) if c.get("id")}


def _probe(client: m.ApiClient, model: str,
           effort: str | None = None) -> tuple[bool, str, str]:
    """单次探测，返回 (是否可用, 失败说明, 收到的思考文本)。"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.0,
        "max_tokens": 64 if effort else 8,
        "stream": True,
    }
    if effort:
        payload["reasoning_effort"] = m.THINKING_LEVELS[effort]
    try:
        status, raw = _post(client, payload)
    except Exception as exc:  # noqa: BLE001
        return False, "EXC " + str(exc), ""
    if status != 200:
        return False, "http={} {}".format(status, _extract_error(raw)), ""
    content, reasoning, _ = _parse_sse(raw)
    if not content and not reasoning:
        return False, "空响应 {}".format(_extract_error(raw)), ""
    return True, "", reasoning


def _resolve_targets(client: m.ApiClient, scope: str) -> set[str]:
    """按 scope 决定要探测哪些模型。"""
    known = set(m.KNOWN_CHAT_MODELS)
    if scope == "known":
        return known
    # 目录里减掉已收录的全部模型（含生图模型），剩下的才是「找漏」候选
    candidates = _catalog_ids(client) - set(m.ALL_SUPPORTED_MODELS)
    return candidates if scope == "catalog" else (candidates | known)


def cmd_models(args: argparse.Namespace) -> int:
    """扫描模型可用性；默认跳过收费模型。

    scope=catalog 用来给手工清单「找漏」：把上游目录里尚未收录的候选逐个实测，
    通过的才值得补进 KNOWN_CHAT_MODELS。
    """
    client = _client()
    try:
        targets = _resolve_targets(client, args.scope)
    except Exception as exc:  # noqa: BLE001
        print("[!] 读取上游模型目录失败: {}".format(exc))
        return 1

    usable, unavailable, skipped, thinking = [], [], [], []
    for model in sorted(targets):
        if model in PAID_MODELS and not args.include_paid:
            skipped.append(model)
            print("{:32s} SKIP  收费模型".format(model))
            continue

        ok, detail, _ = _probe(client, model)
        if not ok:
            unavailable.append((model, detail))
            print("{:32s} FAIL  {}".format(model, detail))
            continue

        usable.append(model)
        note = ""
        if args.probe_thinking:
            ok2, detail2, reasoning = _probe(client, model, "low")
            if not ok2:
                note = "thinking 探测失败: {}".format(detail2)
            elif reasoning:
                thinking.append(model)
                note = "thinking ✓"
            else:
                note = "thinking -"
        print("{:32s} OK    {}".format(model, note))

    print("=" * 64)
    print("可用 {} / 不可用 {} / 跳过 {}".format(len(usable), len(unavailable), len(skipped)))
    for model, detail in unavailable:
        print("  x {} -> {}".format(model, detail))
    if thinking:
        print("reasoning_content 实测非空 {} 个:".format(len(thinking)))
        for model in thinking:
            print("  + {}".format(model))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="真实上游探测")
    sub = parser.add_subparsers(dest="command")

    p_replay = sub.add_parser("replay", help="思考回放 A/B 对比")
    p_replay.add_argument("--model", default="deepseek-v3")
    p_replay.add_argument("--max-tokens", type=int, default=256)
    p_replay.set_defaults(func=cmd_replay)

    p_models = sub.add_parser("models", help="扫描模型可用性")
    p_models.add_argument(
        "--scope", choices=("known", "catalog", "all"), default="known",
        help="known=已收录清单（默认）/ catalog=上游有但未收录的候选 / all=两者",
    )
    p_models.add_argument("--probe-thinking", action="store_true",
                          help="对可用模型补一次 reasoning_effort=low 的调用，判断是否真出思考")
    p_models.add_argument("--include-paid", action="store_true", help="包含收费模型")
    p_models.set_defaults(func=cmd_models)

    # 不传子命令时默认执行 replay
    parser.set_defaults(func=cmd_replay, model="deepseek-v3",
                        max_tokens=256, include_paid=False,
                        scope="known", probe_thinking=False)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
