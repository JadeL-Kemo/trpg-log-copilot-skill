# MD / SQL 架构标准 v1.7

> **v1.7**：JSON 废弃。AI 写 MD 表格（本能格式）→ `import_md.py` 解析入库。SQL 是唯一查询入口。

## 权责

```
AI 写              import_md 自动做      SQL 管查询       HTML 管看
───────             ────────────────      ──────────       ─────────
MD表格(1行/条)   →  INSERT clues/npcs    graph <实体>      跑团面板.html
<!-- state: -->  →  INSERT state_log     search <词>      角色面板.md
叙事正文(05/04)   (不处理)                state current
                                         trace <线索>
```

## 文件规范

### `01_线索.md`（MD表格，AI追加行）

```
| id | content | source | verified | priority | tags | linked |
|------|------|------|------|------|------|------|
| CL-001 | NPC失明住院 | KP旁白 | confirmed | high | blindness,shiming | |
```

| 列 | 值 |
|------|------|
| `id` | 线索编号 CL-XXX |
| `content` | 线索内容 |
| `source` | KP旁白 / 角色名 / 骰子 / 场外 |
| `verified` | `confirmed`(已证实) / `pending`(待验证) / `excluded`(已排除) |
| `priority` | `high`(优先) / `medium`(普通) / `low`(延后) |
| `tags` | 逗号分隔英文/拼音关键词（FTS5检索桥） |
| `linked` | 逗号分隔关联CL编号 |

**入 SQL 条件**：`verified=confirmed`。

### `02_人物.md`（表格+叙事）

```
| id | name | role | stance | faction | key_facts | relationships |
|------|------|------|------|------|------|------|
| NPC-01 | NPC名称 | 身份/角色 | 立场 | 势力 | 事实1,事实2 | 关联角色1,关联角色2 |

## 叙事分析
（AI自由书写，仅用于人类阅读）
```

### `03_时间线.md`

```
| time | event | participants | related_clues |
|------|------|------|------|
| 07-21 09:00 | 团队集结 | NPC1,NPC2 | CL-002 |
```

### `04_行动日志.md`（叙事+行内标注）

```
藤堂被火焰击中...
<!-- state: 角色名 hp -8 combat_fire CL-F01 S01_R02 1 -->
随后被送入ICU。
```

## AI 工作流

```
1. 写叙事 → 04/00/05
2. 追加线索 → 01 表末行（读最后3行取最新编号）
3. 追加标记 → 04 行内 <!-- state: -->
4. 同步 → import_md.py（1次CLI，解析MD→SQL+HTML+面板）
5. 查询 → graph <实体>（1次CLI，完整关系图谱）
```

## 容错

| 情况 | 行为 |
|------|------|
| 某行缺少列 | 该行跳过 + WARN |
| tags为空 | 空数组，FTS无影响 |
| verified≠confirmed | 不导入SQL，但行保留在MD中 |
| 整文件不可解析 | 报错退出 |
