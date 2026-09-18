# -*- coding: utf-8 -*-
"""验证 codebuddy_direct_api.replay_reasoning 的思考回放行为。

用法（在项目根目录执行）::

    python docs/verify_reasoning_replay.py

不需要 token，也不访问网络：上游 HTTP 层在用例 9 中被替换为内存 fake。
退出码 0 表示全部通过，1 表示有用例失败。
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import codebuddy_direct_api as m  # noqa: E402

CASES = []


def case(func):
    CASES.append(func)
    return func


@case
def folds_reasoning_into_content():
    """assistant 思考被折叠进 content，扩展字段被移除，入参不被修改。"""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "答案是 4", "reasoning_content": "暗号是 ZEBRA"},
        {"role": "user", "content": "暗号是什么"},
    ]
    out = m.replay_reasoning(messages)
    assert out[0] is messages[0], "system 消息不应被改动"
    assert out[2] is messages[2], "user 消息不应被改动"
    folded = out[1]
    assert "reasoning_content" not in folded, folded
    expected = "<thinking>\n暗号是 ZEBRA\n</thinking>\n\n答案是 4"
    assert folded["content"] == expected, repr(folded["content"])
    assert messages[1]["content"] == "答案是 4", "入参不应被修改"
    assert messages[1]["reasoning_content"] == "暗号是 ZEBRA", "入参不应被修改"
    return repr(folded["content"])


@case
def idempotent_when_already_inlined():
    """content 已内联相同思考时不重复注入。"""
    dup = {"role": "assistant", "content": "C", "reasoning_content": "C"}
    assert m.replay_reasoning([dup])[0] is dup
    return "same object returned"


@case
def keeps_tool_calls_with_null_content():
    """纯思考 + tool_calls 的轮次：content 变成思考块，tool_calls 保留。"""
    tc = {"role": "assistant", "content": None,
          "tool_calls": [{"id": "call_1"}], "reasoning_content": "R"}
    out = m.replay_reasoning([tc])[0]
    assert out["content"] == "<thinking>\nR\n</thinking>", repr(out["content"])
    assert out["tool_calls"] == [{"id": "call_1"}], out.get("tool_calls")
    return repr(out["content"])


@case
def supports_anthropic_style_thinking_blocks():
    """兼容 Anthropic 风格 thinking 块与 reasoning 别名。"""
    blk = {"role": "assistant", "content": "C",
           "thinking": [{"type": "thinking", "thinking": "T1"},
                        {"type": "text", "text": "T2"}]}
    out = m.replay_reasoning([blk])[0]
    assert out["content"] == "<thinking>\nT1\n\nT2\n</thinking>\n\nC", repr(out["content"])
    assert "thinking" not in out

    alias = {"role": "assistant", "content": "C", "reasoning": "  "}
    assert m.replay_reasoning([alias])[0] is alias, "空白思考不应触发折叠"
    return repr(out["content"])


@case
def leaves_multimodal_content_untouched():
    """非字符串 content（多模态块）保持原样，避免破坏结构。"""
    mm = {"role": "assistant", "content": [{"type": "text", "text": "x"}],
          "reasoning_content": "R"}
    assert m.replay_reasoning([mm])[0] is mm
    return "list content preserved"


@case
def toggle_disables_replay():
    """REPLAY_REASONING=0 语义：关闭后原样透传。"""
    tc = {"role": "assistant", "content": "A", "reasoning_content": "R"}
    m.REPLAY_REASONING = False
    try:
        assert m.replay_reasoning([tc])[0] is tc
    finally:
        m.REPLAY_REASONING = True
    assert m.replay_reasoning([]) == []
    return "replay off -> passthrough"


@case
def chat_completion_sends_folded_messages():
    """端到端：chat_completion 发出的请求体里思考已在 content、扩展字段已消失。"""
    class FakeResponse:
        status = 200

        def read(self, *args):
            payload = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
            return json.dumps(payload).encode("utf-8")

    class FakeConnection:
        def __init__(self):
            self.body = None

        def request(self, method, path, body=None, headers=None):
            self.body = json.loads(body)

        def getresponse(self):
            return FakeResponse()

    client = m.ApiClient.__new__(m.ApiClient)
    client._conversation_id = None
    client.rate_limiter = types.SimpleNamespace(wait=lambda: 0.0)
    client.ensure_valid_token = lambda: None
    client._reset_connection = lambda: None
    conn = FakeConnection()
    client._get_connection = lambda: conn
    client._build_headers = lambda stream=True, model=None: {}

    result = client.chat_completion(
        messages=[{"role": "assistant", "content": "A", "reasoning_content": "RC"},
                  {"role": "user", "content": "U"}],
        model="deepseek-v3",
        stream=False,
    )
    sent = conn.body["messages"]
    assert sent[0]["content"] == "<thinking>\nRC\n</thinking>\n\nA", repr(sent[0])
    assert "reasoning_content" not in sent[0], sent[0]
    assert sent[1] == {"role": "user", "content": "U"}, sent[1]
    assert result == {"content": "ok", "reasoning_content": "",
                      "tool_calls": None, "finish_reason": "stop"}, result
    return repr(sent[0]["content"])


def main() -> int:
    failed = 0
    for func in CASES:
        name = func.__name__
        try:
            detail = func()
        except AssertionError as exc:
            failed += 1
            print("[FAIL] {}: {}".format(name, exc))
        else:
            print("[ OK ] {}{}".format(name, " -> " + detail if detail else ""))
    print("\n{}/{} passed".format(len(CASES) - failed, len(CASES)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())