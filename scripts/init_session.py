#!/usr/bin/env python3
"""
TRPG 跑团会话初始化器
创建完整的日志目录结构和可选的 SQLite 数据库。

Usage:
    python init_session.py <target_dir> [--with-db] [--gm] [--name <session_name>]

Examples:
    python init_session.py ./跑团日志                          # 基础初始化
    python init_session.py ./跑团日志 --with-db                # 含 SQLite
    python init_session.py ./跑团日志 --with-db --gm           # GM 模式
    python init_session.py ./跑团日志 --name "李锐光失明事件"   # 自定义团本名
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path


LOG_FILES = {
    "README.md": """# 跑团日志 — {session_name}

**跑团角色：** [角色名] — [身份/职位]
**团本：** {session_name}
**当前状态：** 🟡 进行中 — 第一幕

---

## 文件索引

| 文件 | 用途 | 何时查阅 |
|------|------|----------|
| `00_当前局势.md` | 🔴 **每轮必读** — 一页速览仪表盘 | 每轮回复前30秒 |
| `01_线索板.md` | 活跃追查中的线索 + 待验证项 | 调查中 |
| `01a_事实库.md` | 已确认基石事实（分类归档） | 深挖细节/结案时 |
| `02_人物关系.md` | NPC 人际关系图谱 | 分析人物动机时 |
| `03_时间线.md` | 案件时间线 | 推断因果/复盘时 |
| `04_行动日志.md` | 当前场景日志 | 追踪当前进展 |
| `04a_过往日志.md` | 已完成场景的归档 | 回顾过往细节 |
| `05_推测与假设.md` | 推理和假设（🟢🟡🔴三级） | 复查分析时 |
| `06_待办事项.md` | 下一步行动（按优先级） | 决定调查方向时 |
| `07_跑团规范手册.md` | 编写规范和证据标准 | 切换平台/AI时加载 |

---

## 角色关键信息速查

- **配枪/装备：** [待填写]
- **权限：** [待填写]
- **物理限制：** [待填写]
- **技能核心：** [待填写]
""",

    "00_当前局势.md": """# 当前局势 — 速览仪表盘

> 📍归档进度: Step 0/6 — 等待首轮聊天记录
> **更新：** {timestamp} | **当前状态：** 🟡 第一幕开始
> **用途：** 每次回复前 30 秒扫一遍

---

## 📍 当前位置 & 团队状态

| 角色 | 位置 | 当前任务 |
|------|------|----------|
| [玩家角色] | [位置] | [任务] |
| — | — | — |

---

## 🔴 当前最高优先级

| # | 事项 | 线索锚 |
|---|------|--------|
| 1 | [待填写] | — |

---

## 🟡 关键活跃线索

| 编号 | 一句话 | 状态 |
|------|--------|------|
| — | — | — |

---

## ⚠️ 已知但未解的核心问题

1. [待填写]
""",

    "01_线索板.md": """# 线索板（活跃版）

> **活跃线索 + 待验证项。已确认基石事实 → `01a_事实库.md`**
> **一页速览 → `00_当前局势.md`**

---

## 🔴 活跃追查中的主线线索

| 编号 | 内容 | 来源 | 可靠性 | 关联 |
|------|------|------|--------|------|
| CL-001 | [团本介绍 — 案件基本信息] | KP旁白 | ✅ 已确认 | — |

---

## 🔴 待验证 / 紧急 UV

| 编号 | 内容 | 验证方向 |
|------|------|----------|
| — | — | — |

---

## 支线线索

| 编号 | 内容 | 来源 | 可靠性 | 关联 |
|------|------|------|--------|------|
| — | — | — | — | — |

---

## 队友能力

| 编号 | 内容 | 状态 |
|------|------|------|
| — | — | — |

---

## 地点/物证

| 编号 | 内容 |
|------|------|
| — | — |
""",

    "01a_事实库.md": """# 已确认事实库

> **用途：** 已交叉验证、KP确认、不会改变的基石事实。平时不需要翻阅——只在深挖细节或写结案报告时查阅。
> **活跃线索请见 `01_线索板.md`，一页速览请见 `00_当前局势.md`。**

---

## 一、案件基础事实

| 编号 | 内容 |
|------|------|
| — | — |

---

## 二、已破解的 UV 问题

| 编号 | 问题 → 答案 |
|------|-----------|
| — | — |

> **完整活跃线索/待验证 → `01_线索板.md`**
""",

    "01b_已关闭线索.md": """# 已关闭/已排除线索归档

> 已完成调查或已被排除的线索，保留记录以供复盘。
> 活跃线索 → `01_线索板.md`
> 已确认事实 → `01a_事实库.md`

---

## 已关闭线索

| 编号 | 内容 | 关闭原因 | 关闭日期 |
|------|------|----------|----------|
| — | — | — | — |

---

## 已排除线索

| 编号 | 内容 | 排除原因 |
|------|------|----------|
| — | — | — |
""",

    "02_人物关系.md": """# 人物关系

> 格式：`[人物] 身份 | 立场 | 已知动机 | 与我的关系 | 备注`

---

## 核心人物

### [受害者/委托人]
- **身份：** [待填写]
- **立场：** [待填写]
- 🔴/🟡/🟢 **当前状态：** [待填写]
- **关键事实：**
  - [待填写]

---

## 调查员同伴

### [队友1]
- **身份：** [待填写]
- 🔴/🟡/🟢 **当前状态：** [待填写]

---

## 关键人物

### [待填写]
- **身份：** [待填写]

---

## 超自然实体

（空——待发现后填写）

---

## 地点

| 地点 | 意义 |
|------|------|
| — | — |

---

## 关系图谱

```
（待绘制）
```
""",

    "02a_人物档案.md": """# 完整人物档案

> 已离开/已故 NPC 的完整档案归档。
> 活跃 NPC → `02_人物关系.md`

---

（空——待归档）
""",

    "03_时间线.md": """# 时间线

> 格式：`[日期时间] 事件 | 参与人物 | 备注`

---

## 案件前

| 时间 | 事件 |
|------|------|
| — | — |

---

## 调查开始

| 时间 | 事件 |
|------|------|
| — | — |
""",

    "03a_详细时间线.md": """# 详细时间线

> 含所有骰子结果、详细对话片段。超过 `03_时间线.md` 内容量时迁移至此。

---

（空——待迁移）
""",

    "04_行动日志.md": """# 行动日志（当前场景）

---

## 第一幕：开始

### 📍 [地点] | [时间]

[待填写]
""",

    "04a_过往日志.md": """# 行动日志 — 过往场景归档

> **内容：** 已完成场景
> **当前场景见** `04_行动日志.md`

---

（空——待归档）
""",

    "05_推测与假设.md": """# 推测与假设

> **双维标签:** [来源: 场内/场外/推测/铁证] [确信: 高/中/低/确定]
> 来源标签不可越级变更。推测→场内需新证据，推测→铁证禁止。
> 证据标准详见 `references/evidence_standards.md`。

---

## 🟢 [确信: 高/确定] — 已证实或强证据

> 以下假设已有KP直接确认或多源交叉验证，在后续分析中视为**事实基底**。

（空——待填充）

---

## 🟡 [确信: 中] — 需证实

> 以下基于已证事实的合逻辑推断，需进一步验证后方可升级。

（空——待填充）

---

## 🔴 [确信: 低] — 仅推测

> 以下缺乏直接事实支撑，仅为角色行为解读或直觉假设。**不可作为决策依据。**

（空——待填充）

---

## 已排除

（空——待填充）
""",

    "05a_推测档案.md": """# 推测档案

> 已证实/已排除推测的完整归档。
> 活跃推测 → `05_推测与假设.md`

---

（空——待归档）
""",

    "06_待办事项.md": """# 待办事项

> 优先级: 🔴 紧急 | 🟡 重要 | 🟢 可延迟

---

## 🔴🔴🔴 紧急

- [ ] [待填写]

---

## 🔴 高优

| 编号 | 任务 | 详情 |
|------|------|------|
| A-1 | [待填写] | [细节] |

---

## 🟡 重要

- [ ] [待填写]

---

## 🟢 可延迟

- [ ] [待填写]
""",

    "07_跑团规范手册.md": """# 跑团规则手记与编写规范

> **版本：** v1.0 | **最后更新：** {timestamp}
> **用途：** 跨平台迁移时的规则速查和编写标准。

---

## 一、角色与身份

### 1.1 跑团角色

| 项目 | 内容 |
|------|------|
| **姓名** | [待填写] |
| **职位** | [待填写] |
| **年龄** | [待填写] |
| **团本** | {session_name} |

### 1.2 AI助手角色

| 项目 | 内容 |
|------|------|
| **身份** | [待填写] |
| **称呼** | [待填写] |
| **职责** | 情报整理、档案调取、线索分析、后勤保障 |
| **风格** | 专业、简洁、以角色身份提供分析和建议。主动找矛盾、挖遗漏、拦死路。 |

### 1.3 回复格式要求

- 每轮收到聊天记录后，执行六步归档（见第二节）
- 先扫 `00_当前局势.md`（30秒）
- 回复开头用角色称呼
- 关键发现用分级标记：🔴 > 🟡 > 🟢
- 每条分析附行动建议
- 超自然方向的推测留在推测文件中，现场对话按角色内视角

---

## 二、六步归档流程

| 步骤 | 写入文件 | 核心任务 |
|------|----------|----------|
| 0 | `00_当前局势.md` | 🔴 先扫30秒 |
| 1 | `01_线索板.md` | 提取新线索，编号归档 |
| 2 | `02_人物关系.md` | 提取新NPC，更新关系图谱 |
| 3 | `03_时间线.md` | 提取事件，按时间排列 |
| 4 | `04_行动日志.md` | 记录当前场景行动+骰子结果 |
| 5 | `05_推测与假设.md` | 交叉关联分析（严格分三级） |
| 6 | `06_待办事项.md` | 更新下一步行动建议 |

### 每条线索必须标注

- **【来源】**：场内 / 场外 / 推测 / 铁证
- **【确信】**：高 / 中 / 低 / 确定
- **【关联编号】**：引用已有关联线索编号 (linked_ids)

> 详细标准见 `references/evidence_standards.md`。来源不可越级变更。

---

## 三、文件结构

```
跑团日志/
├── 00_当前局势.md             每轮必读
├── README.md                  总索引
├── 01_线索板.md               活跃线索
├── 01a_事实库.md              已确认事实
├── 02_人物关系.md             NPC图谱
├── 03_时间线.md               时间轴
├── 04_行动日志.md             当前场景
├── 04a_过往日志.md            过往归档
├── 05_推测与假设.md           推理分级
├── 06_待办事项.md             行动清单
└── 07_跑团规范手册.md         本文档
```

---

## 四、证据标准（铁律）

### 双维标签

| 来源 | 含义 |
|------|------|
| `场内` | 游戏内NPC/场景给的信息 (有证据) |
| `检定` | 骰子/技能检定结果 |
| `场外` | KP闲聊/暗示 (有真相无证据) |
| `推测` | 玩家/副官推理 (无证据无真相) |
| `铁证` | 参考资料+人证+KP明示 (固定确信=确定) |

| 确信 | 适用来源 | 含义 |
|------|----------|------|
| `高` | 场内/场外/推测 | 可靠信息源或强逻辑 |
| `中` | 场内/场外/推测 | 有一定依据但不确凿 |
| `低` | 场内/场外/推测 | 直觉或弱线索 |
| `确定` | 铁证 | 无可争议 |

**来源不可越级。** 推测→铁证 ❌ | 推测→场内 ✅ (需证据) | 场内→铁证 ✅ | 确信度可升降。

---

## 五、角色技能速查

[待填写]

---

## 六、当前案件概要

[待填写]

---

## 七、编写规范速查卡

### 禁止
- ❌ 未标注来源的线索
- ❌ 推测与事实混放
- ❌ 删除已被推翻的假设

### 必须
- ✅ 每条新线索给唯一编号
- ✅ 每个假设标注状态标签
- ✅ 推测升级后更新标签
- ✅ 线索与假设互引

---

## 八、切换平台加载方式

将以下指令粘贴给新AI的System Prompt或记忆：

```
用户正在进行[规则系统]跑团，角色名[玩家角色]，[身份]。[设定简要]。
助手角色为[AI角色]，是[玩家角色]的直属[副官/秘书]，负责情报整理、档案调取、线索分析等后勤工作，对[玩家角色]绝对忠诚。
团本为[团本名称]。
跑团日志存放于 [路径]\跑团日志\，包含多个分类文件。
当用户告知跑团进展时，以[AI角色]身份回复（称呼用户为"[称呼]"），执行：
(1)扫描线索归档至01_线索板，(2)新NPC归档至02_人物关系，(3)更新03_时间线，(4)行动写入04_行动日志，(5)交叉关联分析写入05_推测，(6)更新06_待办事项。
每条线索标注【来源】【可靠性】【关联编号】。全程以[副官/秘书]口吻提供分析和建议。
```
""",

    "_index.md": """# 关键词检索索引

> 人工维护的关键词→ 文件映射，用于快速定位信息。
> 如已启用 SQLite，优先使用数据库查询。

---

## 人物索引

| 关键词 | 文件 | 备注 |
|--------|------|------|
| — | — | — |

---

## 地点索引

| 关键词 | 文件 | 备注 |
|--------|------|------|
| — | — | — |

---

## 物品/证据索引

| 关键词 | 文件 | 备注 |
|--------|------|------|
| — | — | — |

---

## 事件/主题索引

| 关键词 | 文件 | 备注 |
|--------|------|------|
| — | — | — |
"""
}


GM_EXTRA_FILES = {
    "08_NPC管理.md": """# NPC 管理（GM 模式）

> ⚠️ GM 专用 — 含 PC 不可见的隐藏信息

---

## 活跃 NPC

| NPC | 身份 | PC已知 | GM已知 | 剧情状态 |
|-----|------|--------|--------|----------|
| — | — | — | — | — |

---

## NPC 隐藏信息

### [NPC名称]
- **PC 已知：** [玩家已知的公开信息]
- **GM 已知：** [实际身份、隐藏动机、秘密]
- **触发条件：** [什么情况下 PC 可以发现隐藏信息]
""",

    "09_遭遇设计.md": """# 遭遇设计（GM 模式）

---

## 计划中的遭遇

| 编号 | 名称 | 预期时间 | 线索产出 | 难度 | 状态 |
|------|------|----------|----------|------|------|
| ENC-001 | — | — | — | — | 🟡 待设计 |

---

## 已发生的遭遇

| 编号 | 名称 | 实际时间 | 结果 | PC 反应 |
|------|------|----------|------|---------|
| — | — | — | — | — |
"""
}


def create_directory_structure(target_dir, session_name, gm_mode=False):
    """Create the full log directory structure with template files."""
    log_dir = Path(target_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    created = []
    for filename, template in LOG_FILES.items():
        filepath = log_dir / filename
        if not filepath.exists():
            content = template.format(session_name=session_name, timestamp=timestamp)
            filepath.write_text(content, encoding='utf-8')
            created.append(filename)

    if gm_mode:
        for filename, template in GM_EXTRA_FILES.items():
            filepath = log_dir / filename
            if not filepath.exists():
                filepath.write_text(template, encoding='utf-8')
                created.append(filename)

    return created, log_dir


def init_database(log_dir):
    """Initialize SQLite database for the session."""
    try:
        import sqlite3
    except ImportError:
        print("⚠️  Python sqlite3 module not available. Skipping database initialization.")
        return None

    db_path = Path(log_dir) / "trpg_data.db"

    if db_path.exists():
        print(f"⚠️  Database already exists: {db_path}")
        return db_path

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS clues (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL,
            category TEXT DEFAULT 'core',
            status TEXT DEFAULT 'active',
            scene_id TEXT,
            linked_ids TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- FTS5 全文搜索 (自动同步触发器, 零维护)
        CREATE VIRTUAL TABLE IF NOT EXISTS clues_fts USING fts5(
            content, source, confidence, content=clues, content_rowid=rowid
        );
        CREATE TRIGGER IF NOT EXISTS clues_ai AFTER INSERT ON clues BEGIN
            INSERT INTO clues_fts(rowid, content, source, confidence)
            VALUES (new.rowid, new.content, new.source, new.confidence);
        END;
        CREATE TRIGGER IF NOT EXISTS clues_ad AFTER DELETE ON clues BEGIN
            INSERT INTO clues_fts(clues_fts, rowid, content, source, confidence)
            VALUES ('delete', old.rowid, old.content, old.source, old.confidence);
        END;
        CREATE TRIGGER IF NOT EXISTS clues_au AFTER UPDATE ON clues BEGIN
            INSERT INTO clues_fts(clues_fts, rowid, content, source, confidence)
            VALUES ('delete', old.rowid, old.content, old.source, old.confidence);
            INSERT INTO clues_fts(rowid, content, source, confidence)
            VALUES (new.rowid, new.content, new.source, new.confidence);
        END;

        CREATE TABLE IF NOT EXISTS npcs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT,
            appearance TEXT,
            stance TEXT,
            status TEXT DEFAULT 'active',
            faction TEXT,
            key_facts TEXT DEFAULT '[]',
            relationships TEXT DEFAULT '[]',
            scene_id TEXT,
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_time TEXT NOT NULL,
            event TEXT NOT NULL,
            participants TEXT DEFAULT '[]',
            scene_id TEXT,
            related_clues TEXT DEFAULT '[]',
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS speculations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            basis_clues TEXT DEFAULT '[]',
            confidence TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            scene_id TEXT,
            tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS scenes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            status TEXT DEFAULT 'in_progress',
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            content TEXT NOT NULL,
            priority TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            scene_id TEXT,
            related_clues TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)

    conn.commit()
    conn.close()

    return db_path


def main():
    parser = argparse.ArgumentParser(description="Initialize a TRPG session directory")
    parser.add_argument("target_dir", help="Target directory for log files")
    parser.add_argument("--with-db", action="store_true", help="Also initialize SQLite database")
    parser.add_argument("--gm", action="store_true", help="GM mode (includes extra files)")
    parser.add_argument("--name", default="未命名团本", help="Session/campaign name")
    args = parser.parse_args()

    mode_str = " (GM Mode)" if args.gm else ""
    print(f"Creating TRPG session: {args.name}{mode_str}")
    print(f"Target: {args.target_dir}")
    print()

    created, log_dir = create_directory_structure(args.target_dir, args.name, args.gm)
    print(f"Created {len(created)} files:")
    for f in created:
        print(f"  ✅ {f}")

    if args.with_db:
        db_path = init_database(log_dir)
        if db_path:
            print(f"  ✅ trpg_data.db (SQLite)")

    print(f"\nSession initialized at: {log_dir.resolve()}")
    print("Edit the files to fill in character details, then start the first scene.")


if __name__ == "__main__":
    main()
