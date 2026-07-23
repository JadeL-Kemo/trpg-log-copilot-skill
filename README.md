# TRPG Log Copilot — 跑团副官

[![CodeBuddy](https://img.shields.io/badge/CodeBuddy-SKILL-blue)](https://www.codebuddy.ai) [![Version](https://img.shields.io/badge/version-1.7.0-green)](https://github.com/JadeL-Kemo/trpg-log-copilot-skill/releases) [![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

**让 AI 成为你的跑团副官。** 车卡辅助、日志归档、线索图谱查询、防超游——零额外配置，解压即用。

---

## 为什么需要这个？

跑团时你需要关注剧情、扮演角色、做决策。但混乱的线索板、遗漏的 NPC 关系、模糊的时间线会拖垮体验。

这个 SKILL 让 AI 帮你：
- **自动归档** — 每轮结束发聊天记录，AI 自动分拣到 6 类文件
- **智能检索** — SQLite FTS5 + CLI 命令（graph/events/search），一条命令出完整关系图谱
- **信息茧房** — 三轴验证体系（证实性+紧急性+来源），角色视角过滤，防超游/OOC
- **骰子集成** — CoC/DND 检定一键调用，骰子结果自动溯源
- **HTML 面板** — 自动生成 5 标签页仪表盘，手机浏览器友好

---

## 快速开始

```bash
# 1. 安装
git clone https://github.com/JadeL-Kemo/trpg-log-copilot-skill.git \
  ~/.codebuddy/skills/trpg-log-copilot

# 2. AI 自动建立项目 Rule（角色身份+技能速查+检索指令）

# 3. 每轮结束后：AI 写 MD 表格 + 行内标注 → import_md.py 同步 SQL

# 4. 下次继续：
#    "继续跑团" → AI 从断点恢复（CLI 精准查询，零 token 遍历）
```

**零依赖即可使用**（纯 Markdown 工作流）。Python 工具可选增强：骰子、SQLite、规则书导入。

---

## 核心功能

### 九步归档

| Step | 产出 | 作用 |
|------|------|------|
| 0 | `00_当前局势.md` | 仪表盘 + 断点恢复 |
| 1 | `01_线索.md` | 新线索（MD 表格，自动同步 SQL） |
| 2 | `02_人物.md` | NPC/实体表格 + 叙事分析 + 关系边表 |
| 2a | `02_人物.md` | NPC 关系更新（`npc_relations` 边表） |
| 3 | `03_时间线.md` | 事件速记表（story/scene 层） |
| 3a | `03a_大纪事.md` | 世界观年表（chronicle 层） |
| 4 | `04_行动日志.md` | 场景原文 + 骰子结果 + `<!-- state: -->` 标注 |
| 4a | SQL | `state add` HP/SAN/资源变更 |
| 5 | `06_待办.md` | 下一步行动 + 优先级 + 关联线索 |
| 6 | 同步 | `import_md.py` → SQL + 渲染 panel.html |
| 7 | 面板 | `serve.py` 启动 localhost 面板 |
| 8 | 回复 | 副官身份总结 |

### CLI 查询引擎

```bash
# 关系图谱 — 一次查出 NPC+线索+时间线+状态变更
db_manager.py graph <实体> [--as 角色]
db_manager.py relations [npc]              # NPC 关系边表
db_manager.py events [--char] [--since]    # 双轨时间线
db_manager.py search "<关键词>"            # FTS5 全文搜索
db_manager.py state current                # 角色状态速览
db_manager.py state query <角色>            # 角色变更历史
db_manager.py trace <线索编号>              # 事件链溯源
db_manager.py npcs [name]                  # NPC 查询
db_manager.py timeline [--since] [--char]  # 时间线视图
db_manager.py stats                        # 数据库统计
file_ops.py append-table / replace-scene / append-scene    # 增删改
narrative_search.py scenes / scene / grep                  # 精准检索
```

### HTML 面板

自动生成暗色主题 5 标签页仪表盘（线索/人物/时间线/角色/待办），移动端适配，每轮自动刷新。

---

## 文件结构

```
trpg-log-copilot/
├── SKILL.md                     ← AI 注入的完整工作流
├── CHANGELOG.md
├── LICENSE                      ← Apache 2.0
├── scripts/                     ← CLI 命令
│   ├── dice_roller.py
│   ├── db_manager.py            ← graph/events/search/state/trace
│   └── init_session.py
├── tools/                       ← 辅助工具
│   ├── import_md.py             ← MD 表 → SQL 同步
│   ├── file_ops.py              ← 大文件零 token 读写
│   ├── narrative_search.py      ← 叙事文件精准检索
│   ├── render_views.py          ← SQL → HTML 面板
│   ├── export_dashboard.py      ← SQL → 角色面板
│   ├── check_env.py
│   └── rule_reader.py
├── references/                  ← 规范文档
│   ├── evidence_standards.md    ← 三轴验证体系
│   ├── md_schema_standard.md    ← MD/SQL 架构标准
│   ├── rule_template.md         ← Rule 自举模板
│   ├── state_reason_vocab.md    ← 状态变更词表
│   ├── file_specs.md
│   ├── schema.md
│   └── coc7_quickref.md
└── rule_lib/
    └── _quickref_template.md
```

---

## 许可

Apache License 2.0 — 自由使用、修改、分发。
