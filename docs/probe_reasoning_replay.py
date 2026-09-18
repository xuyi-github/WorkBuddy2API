# -*- coding: utf-8 -*-
"""真实上游探测脚本（需要 token：tokens.json 或 CODEBUDDY_AUTH_TOKEN）。

子命令：

  replay  思考回放 A/B 对比 —— 验证历史 reasoning_content 是否真的进入底座上下文
  models  扫描 KNOWN_CHAT_MODELS 在上游的可用性

用法::

    python docs/probe_reasoning_replay.py replay
    python docs/probe_reasoning_replay.py models

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
PAID_MODELS = {"hy3-preview-agent"}


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


def cmd_models(args: argparse.Namespace) -> int:
    """扫描模型可用性；默认跳过收费模型。"""
    client = _client()
    usable, unavailable, skipped = [], [], []
    for model in sorted(m.KNOWN_CHAT_MODELS):
        if model in PAID_MODELS and not args.include_paid:
            skipped.append(model)
            print("{:26s} SKIP  收费模型".format(model))
            continue
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.0,
            "max_tokens": 8,
            "stream": True,
        }
        try:
            status, raw = _post(client, payload)
        except Exception as exc:  # noqa: BLE001
            unavailable.append((model, "EXC " + str(exc)))
            print("{:26s} EXC   {}".format(model, exc))
            continue
        if status == 200:
            usable.append(model)
            print("{:26s} OK".format(model))
        else:
            try:
                err = json.loads(raw)
                detail = err.get("msg") or err.get("displayMsg", {}).get("zh") or raw[:100]
            except json.JSONDecodeError:
                detail = raw[:100]
            unavailable.append((model, detail))
            print("{:26s} FAIL  http={} {}".format(model, status, detail))

    print("=" * 64)
    print("可用 {} / 不可用 {} / 跳过 {}".format(len(usable), len(unavailable), len(skipped)))
    for model, detail in unavailable:
        print("  x {} -> {}".format(model, detail))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="真实上游探测")
    sub = parser.add_subparsers(dest="command")

    p_replay = sub.add_parser("replay", help="思考回放 A/B 对比")
    p_replay.add_argument("--model", default="deepseek-v3")
    p_replay.add_argument("--max-tokens", type=int, default=256)
    p_replay.set_defaults(func=cmd_replay)

    p_models = sub.add_parser("models", help="扫描模型可用性")
    p_models.add_argument("--include-paid", action="store_true", help="包含收费模型")
    p_models.set_defaults(func=cmd_models)

    # 不传子命令时默认执行 replay
    parser.set_defaults(func=cmd_replay, model="deepseek-v3",
                        max_tokens=256, include_paid=False)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
