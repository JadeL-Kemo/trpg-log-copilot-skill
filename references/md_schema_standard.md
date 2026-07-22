# MD 架构标准 — JSON-only YAML frontmatter

> **AI 只写 JSON frontmatter，不写正文表格。** 正文仅用于叙事文件。
> 前端元数据即唯一源——无重复信息，AI 不浪费 token 读两份相同数据。

## 文件规范

### `01_线索板.md`（JSON-only）

```yaml
---
clues: [{"id":"CL-001","content":"内容","source":"KP旁白","confidence":"✅已确认","linked":[]}]
---
```

| 字段 | 必填 | 值域 |
|------|:--:|------|
| id | ✅ | CL-XXX 格式 |
| content | ✅ | 字符串 |
| source | ✅ | KP旁白/KP场景/角色名/骰子/场外 |
| confidence | ✅ | ✅已确认/🟡待验证/🔴紧急/⚠️低可靠/ℹ️背景 |
| linked | ✅ | 数组，无关联为 [] |

### `02_人物关系.md`（JSON + 叙事）

```yaml
---
npcs: [{"id":"NPC-01","name":"","role":"","stance":"","faction":"","key_facts":[],"relationships":[]}]
---

## 赵婉清
叙事分析正文——仅此文件保留正文（NPC背景不可自动生成）。
```

### `03_时间线.md`（JSON-only）

```yaml
---
events: [{"time":"07-21 09:00","event":"","participants":[],"related_clues":[]}]
---
```

### `04_行动日志.md`（叙事 + 行内标注）

```markdown
藤堂被火焰击中...
<!-- state: 藤堂咲 hp -8 combat_fire CL-F01 S01_R02 1 -->
随后被送入ICU。
```

格式：`<!-- state: <角色> <池> <delta> <reason> [clue] [scene] [round] -->`

### `05_推测与假设.md`（叙事）

纯正文，不导入 SQL。推测变更用留痕原则（`[!更正]`/`[!废弃]`）。

### `06_待办事项.md`（叙事）

纯正文，不导入 SQL。

## MD ↔ SQL 权责边界

```
MD                            SQL                          auto
──                            ───                          ────
01 JSON ← AI写入               clues(✅) ← 导入              —
02 JSON+叙事 ← AI写入           npcs ← 导入                   —
03 JSON ← AI写入                timeline_events ← 导入        —
04 标注 ← AI写入                char_state_log ← 导入         —
05 叙事 ← AI写入                —                            —
06 叙事 ← AI写入                —                            —
00 叙事 ← AI写入                —                            —
角色面板 —                       ← 导出                       角色面板.md
词典 —                          dict_labels(唯一源)            —
```

- **AI 写**：JSON frontmatter（01/02/03）+ 叙事正文（02/04/05/06/00）
- **import_from_md.py 做**：JSON→SQL 导入 + FTS 重建
- **SQL 管**：全部查询（search/trace/npcs/timeline/links/state）
- **export_dashboard.py 做**：SQL→角色面板.md

## SQL 分层策略

| 置信度 | 入 SQL？ | 原因 |
|:--|:--:|------|
| ✅已确认 | ✅ | 稳定数据，无限低修改频率 |
| 🟡待验证 | ❌ | 高频修改，存 MD |
| 🔴紧急 | ❌ | 同🟡 |
| ⚠️低可靠 | ❌ | 同🟡 |
| ℹ️背景 | ❌ | 同🟡 |

## 导入

```bash
python tools/import_from_md.py <日志目录> <trpg_data.db>
```

读取 01/02/03/04 → 导入 SQL → 重建 FTS索引。
