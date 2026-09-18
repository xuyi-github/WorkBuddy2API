# 文档索引

| 文档 | 内容 |
|------|------|
| [FORK-CHANGES.md](FORK-CHANGES.md) | **这是 fork**：上游仓库、两轮会话相对上游的全部改动 |
| [codex-integration.md](codex-integration.md) | 在 Codex / Claude Code 中使用：经 CC Switch 协议转换接入（含字段填法） |
| [2026-09-18_reasoning-replay-handoff.md](2026-09-18_reasoning-replay-handoff.md) | 交接文档：根因、修复、真实上游验证、证据链、待办 |
| [verify_reasoning_replay.py](verify_reasoning_replay.py) | 离线自检，9 个用例，不需要 token、不访问网络 |
| [probe_reasoning_replay.py](probe_reasoning_replay.py) | 真实链路探测：`replay` A/B 对比、`models` 可用性扫描 |

## 怎么用

- 想知道这个 fork 改了上游哪些东西：[FORK-CHANGES.md](FORK-CHANGES.md)
- 只想确认代码没坏：`python docs/verify_reasoning_replay.py`
- 接手继续做：先读交接文档的「一句话结论 → 快速自检 → 下一步待办」
- 想在 Codex / Claude Code 里用这些模型：[codex-integration.md](codex-integration.md)
- 接口用法与部署：项目根目录 [README.md](../README.md)