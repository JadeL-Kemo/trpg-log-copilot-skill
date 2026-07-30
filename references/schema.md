# SQLite 数据库 Schema

> 用于长团（>3场景）或多副本战役的结构化存储。AI 检索引擎，非人类阅读视图。
> **权威来源**：`scripts/db_manager.py cmd_init` 的 DDL。本文档与该函数保持同步。

---

## 初始化

```bash
# 推荐：直接用 db_manager（完整 schema）
python scripts/db_manager.py <db路径> init

# 备选：配合 init_session 使用（仅建 MD 文件模板，不加 --with-db）
python scripts/init_session.py <目录>
```

> **注意**：`init_session.py --with-db` 的 schema 不完整，建议单独运行 `db_manager.py init`。

---

## 表结构（v1.8.9 — 匹配 `db_manager.py cmd_init` DDL）

### clues — 线索表

```sql
CREATE TABLE IF NOT EXISTS clues (
    id         TEXT PRIMARY KEY,          -- CL-001
    content    TEXT NOT NULL,             -- 线索内容
    source     TEXT NOT NULL,             -- 来源（KP叙述/角色发言/骰子结果/场外OOC）
    confidence TEXT NOT NULL,             -- confirmed / pending / excluded
    priority   TEXT DEFAULT 'medium',     -- urgent / high / medium / low
    tags       TEXT DEFAULT '[]',         -- JSON 关键词数组
    category   TEXT DEFAULT 'core',       -- core / sideline / teammate / location
    status     TEXT DEFAULT 'active',     -- active / confirmed / closed
    scene_id   TEXT,                      -- 所属场景
    linked_ids TEXT DEFAULT '[]',         -- JSON 关联线索 ID 数组
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### clues_fts — 线索全文索引（FTS5 虚拟表）

```sql
CREATE VIRTUAL TABLE clues_fts USING fts5(
    content, source, tags, content=clues, content_rowid=rowid
);
-- 自动同步触发器：clues_ai / clues_ad / clues_au
```

### npcs — 人物表

```sql
CREATE TABLE IF NOT EXISTS npcs (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    role          TEXT,                   -- 身份/职位
    appearance    TEXT,                   -- 外貌描述
    stance        TEXT,                   -- 对调查员立场（友好/中立/敌对/未知）
    status        TEXT DEFAULT 'active',  -- active / deceased / left / unknown
    faction       TEXT,                   -- 所属派系
    key_facts     TEXT DEFAULT '[]',      -- JSON 关键事实数组
    relationships TEXT DEFAULT '[]',      -- JSON [{npc_id, relation_type, detail}]
    scene_id      TEXT,
    created_at    TEXT DEFAULT (datetime('now','localtime'))
);
```

### timeline_events — 时间线表

```sql
CREATE TABLE IF NOT EXISTS timeline_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time     TEXT NOT NULL,         -- 事件时间描述
    event          TEXT NOT NULL,
    participants   TEXT DEFAULT '[]',     -- JSON 参与人物数组
    scene_id       TEXT,
    related_clues  TEXT DEFAULT '[]',     -- JSON
    notes          TEXT,
    category       TEXT DEFAULT 'story',  -- chronicle / story / scene
    event_date     TEXT DEFAULT NULL,     -- YYYY / YYYY-MM / YYYY-MM-DD-{a-z}
    timeline_status TEXT DEFAULT 'canon', -- canon / altern / uncertain / dream
    created_at     TEXT DEFAULT (datetime('now','localtime'))
);
```

### char_base — 角色基础档案

```sql
CREATE TABLE IF NOT EXISTS char_base (
    char_name  TEXT PRIMARY KEY,
    char_type  TEXT NOT NULL DEFAULT 'pc', -- pc / npc
    base_stats TEXT NOT NULL DEFAULT '{}', -- JSON 键值池: {"hp":12,"san":60,"ac":15}
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### char_state_log — 角色状态变更日志（事件溯源）

```sql
CREATE TABLE IF NOT EXISTS char_state_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    char_name  TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    deltas     TEXT NOT NULL DEFAULT '{}', -- JSON: {"hp":-3,"san":-1}
    loc_new    TEXT DEFAULT NULL,
    status_new TEXT DEFAULT NULL,
    reason     TEXT NOT NULL,              -- 固定用语（见 state_reason_vocab.md）
    clue_ref   TEXT DEFAULT NULL,
    scene_ref  TEXT DEFAULT NULL,
    round      INTEGER DEFAULT NULL,
    game_time  TEXT DEFAULT NULL,
    game_date  TEXT DEFAULT NULL,
    note       TEXT DEFAULT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (char_name) REFERENCES char_base(char_name)
);
```

### npc_relations — NPC 关系边表

```sql
CREATE TABLE IF NOT EXISTS npc_relations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    npc_a      TEXT NOT NULL,
    npc_b      TEXT NOT NULL,
    rel_type   TEXT NOT NULL,
    direction  TEXT DEFAULT 'mutual',      -- mutual / oneway_a2b / oneway_b2a
    source_ref TEXT DEFAULT NULL,
    notes      TEXT DEFAULT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### narrative_chunks — 叙事段落存储

```sql
CREATE TABLE IF NOT EXISTS narrative_chunks (
    scene_id   TEXT NOT NULL,
    file_name  TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (scene_id, file_name)
);
```

### narrative_fts — 叙事全文索引（FTS5 虚拟表）

```sql
CREATE VIRTUAL TABLE narrative_fts USING fts5(
    scene_id, chunk_text, content=narrative_chunks, content_rowid=rowid
);
-- 自动同步触发器：nc_ai
```

### dict_labels — 显示词典

```sql
CREATE TABLE IF NOT EXISTS dict_labels (
    category TEXT NOT NULL,               -- 'pool' | 'reason' | 'status'
    key      TEXT NOT NULL,
    cn_name  TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (category, key)
);
```

---

## 常用查询示例

### FTS5 全文搜索线索
```sql
SELECT id, content, source, confidence, tags
FROM clues_fts WHERE clues_fts MATCH '关键词'
ORDER BY rank;
```

### 关系图谱查询
```sql
-- 查某 NPC 的所有关联
SELECT npc_a, npc_b, rel_type, direction
FROM npc_relations
WHERE npc_a = 'NPC-002' OR npc_b = 'NPC-002';
```

### 角色当前状态
```sql
SELECT char_name, deltas, reason, clue_ref, created_at
FROM char_state_log
WHERE char_name = '林芷'
ORDER BY seq DESC LIMIT 10;
```

### 叙事场景检索
```sql
SELECT scene_id, file_name, chunk_text
FROM narrative_fts
WHERE narrative_fts MATCH '李锐光'
ORDER BY rank;
```

### 时间线按类别过滤
```sql
SELECT event_time, event, category, timeline_status
FROM timeline_events
WHERE category = 'scene' AND timeline_status = 'canon'
ORDER BY event_date;
```

---

## 写入时机

每次执行归档时，**同步双写**：
- Markdown 文件（人类可读）
- SQLite 表（AI FTS5 检索）

`scripts/db_manager.py` 提供完整命令行接口：`init` / `search` / `graph` / `state` / `relations` / `events` / `stats`。

`tools/import_md.py` 解析 MD 表 → INSERT SQL（单向桥）。
