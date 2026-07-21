# TRPG Log Copilot — 跑团副官

[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-SKILL-blue)](https://www.codebuddy.ai) [![Version](https://img.shields.io/badge/version-1.5.0-green)](https://github.com/JadeL-Kemo/trpg-log-copilot-skill/releases) [![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE) 





**让 AI 成为你的跑团副官。** 车卡辅助、日志归档、线索分析、防超游——零额外配置，解压即用。

---

## 为什么需要这个？

跑团时你需要关注剧情、扮演角色、做决策。但混乱的线索板、遗漏的 NPC 关系、模糊的时间线会拖垮体验。

这个 SKILL 让 AI 帮你：
- 📋 **自动归档** — 每轮结束发聊天记录，AI 自动分拣到 6 类文件
- 🔍 **智能检索** — SQLite FTS5 全文搜索，2000 条线索查询 <10ms
- 🛡️ **防超游** — 双维证据标签（来源×确信度），场外信息绝不混入场内
- 🎲 **骰子集成** — CoC/DND 检定一键调用，骰子结果自动溯源为独立证据

---

## 快速开始

```bash
# 1. 安装
git clone https://github.com/JadeL-Kemo/trpg_log_copilot_skill.git \
  ~/.codebuddy/skills/trpg_log_copilot

# 2. 启动跑团会话，告知 Agent：
#    "我在跑 CoC 7 版团，角色是警探李锐光"

# 3. 每轮结束后发聊天记录，Agent 自动归档

# 4. 下次继续：
#    "继续跑团" → Agent 从断点恢复
```

**零依赖即可使用**（纯 Markdown 工作流）。Python 工具可选增强：骰子、SQLite、规则书导入。

---

## 核心功能

### 六步归档

| Step | 产出 | 作用 |
|------|------|------|
| 0 | `00_当前局势.md` | 仪表盘 + 断点恢复 |
| 1 | `01_线索板.md` | 新线索，双维标签溯源 |
| 2 | `02_人物关系.md` | NPC/实体关系图谱 |
| 3 | `03_时间线.md` | 事件时序排列 |
| 4 | `04_行动日志.md` | 场景行动 + 骰子结果 |
| 5 | `05_推测与假设.md` | 交叉关联分析（唯一允许推理的环节） |
| 6 | `06_待办事项.md` | 下一步行动 + 优先级 |

### 双维证据标签

```
[来源: 场内 / 检定 / 场外 / 推测 / 铁证] [确信: 高 / 中 / 低 / 确定]
```

来源不可越级变更。推测永远是推测，除非有证据补强。场外闲聊绝不混入场内记录。

### FTS5 全文搜索

```bash
# 搜任意关键词，自动带出交叉引用的关联线索
python scripts/db_manager.py trpg_data.db search "<关键词>"

# 统计概览
python scripts/db_manager.py trpg_data.db stats
```

### 多规则支持

`rule_lib/` 下每规则一套：
```
rule_lib/[规则名]/quickref.md   ← Agent 优先读 (≤ 200 行)
rule_lib/[规则名]/full.md       ← 完整规则
```

---

## 文件结构

```
trpg_log_copilot_skill/
├── SKILL.md                     ← Agent 注入的完整工作流
├── README.md                    ← 本文档
├── LICENSE                      ← Apache 2.0
├── scripts/                     ← Agent 运行时调用
│   ├── dice_roller.py
│   ├── init_session.py
│   └── db_manager.py
├── tools/                       ← 用户手动运行
│   ├── check_env.py
│   └── rule_reader.py
├── references/                  ← 规范文档
│   ├── evidence_standards.md
│   ├── file_specs.md
│   ├── schema.md
│   └── coc7_quickref.md
├── rule_lib/
│   └── _quickref_template.md
└── demo/                        ← 示例跑团日志
```

---

## 演示

[`demo/`](demo/) 包含完整的示例跑团日志——展示实际使用效果。

---

## 许可

Apache License 2.0 — 自由使用、修改、分发。
