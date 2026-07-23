# SQLite 数据库 Schema

> 用于长团（>3场景）或多副本战役的结构化存储。AI 检索引擎，非人类阅读视图。

---

## 初始化

```bash
python scripts/init_session.py --with-db
```

或在已有目录中：
```bash
python scripts/db_manager.py init
```

---

## 表结构

### clues — 线索表

```sql
CREATE TABLE IF NOT EXISTS clues (
    id TEXT PRIMARY KEY,              -- CL-001
    content TEXT NOT NULL,             -- 线索内容
    source TEXT NOT NULL,              -- 来源（KP叙述/角色发言/骰子结果/场外OOC）
    reliability TEXT NOT NULL,         -- 可靠性：confirmed/unverified/urgent/meta/unreliable
    category TEXT DEFAULT 'core',     -- 类别：core/sideline/teammate/location
    status TEXT DEFAULT 'active',     -- 状态：active/confirmed/closed
    scene_id TEXT,                     -- 所属场景
    tags TEXT DEFAULT '[]',           -- JSON 关键词数组
    related_clues TEXT DEFAULT '[]',  -- JSON 关联线索 ID 数组
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### npcs — 人物表

```sql
CREATE TABLE IF NOT EXISTS npcs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT,                         -- 身份/职位
    appearance TEXT,                   -- 外貌描述
    stance TEXT,                       -- 对调查员立场
    status TEXT DEFAULT 'active',     -- active/deceased/left/unknown
    faction TEXT,                      -- 所属派系
    key_facts TEXT DEFAULT '[]',      -- JSON 关键事实数组
    relationships TEXT DEFAULT '[]',  -- JSON [{npc_id, relation_type, detail}]
    scene_id TEXT,
    tags TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### timeline_events — 时间线表

```sql
CREATE TABLE IF NOT EXISTS timeline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time TEXT NOT NULL,          -- 事件时间描述
    event TEXT NOT NULL,
    participants TEXT DEFAULT '[]',   -- JSON 参与人物数组
    scene_id TEXT,
    related_clues TEXT DEFAULT '[]',  -- JSON
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### speculations — 推测表

```sql
CREATE TABLE IF NOT EXISTS speculations (
    id TEXT PRIMARY KEY,               -- H-001
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    basis_clues TEXT DEFAULT '[]',    -- JSON ["CL-001","CL-005"]
    confidence TEXT NOT NULL,          -- confirmed/need_verify/speculation
    status TEXT DEFAULT 'active',     -- active/confirmed/excluded
    scene_id TEXT,
    tags TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### scenes — 场景/幕次表

```sql
CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,               -- act1, act2_scene1
    title TEXT NOT NULL,
    summary TEXT,
    status TEXT DEFAULT 'in_progress',-- in_progress/completed/archived
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

### todos — 待办事项表

```sql
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,                      -- A-1, B-2
    content TEXT NOT NULL,
    priority TEXT NOT NULL,            -- urgent/high/normal/low
    status TEXT DEFAULT 'pending',    -- pending/done/cancelled
    scene_id TEXT,
    related_clues TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
```

---

## 常用查询示例

### 按关键词搜索线索
```sql
SELECT id, content, source, reliability
FROM clues
WHERE tags LIKE '%[关键词]%' AND status = 'active'
ORDER BY created_at DESC;
```

### 搜索与某NPC相关的所有线索
```sql
SELECT id, content, source, reliability
FROM clues
WHERE related_clues LIKE '%CL-XXX%'
   OR content LIKE '%[NPC名称]%';
```

### 获取某场景的所有时间线事件
```sql
SELECT event_time, event, participants
FROM timeline_events
WHERE scene_id = '[scene_id]'
ORDER BY event_time;
```

### 查找所有涉及某个关键词的推测
```sql
SELECT id, title, content, confidence, status
FROM speculations
WHERE content LIKE '%[关键词]%' OR title LIKE '%[关键词]%';
```

### 跨来源交叉验证
```sql
SELECT c1.id, c1.content, c1.source, c2.id, c2.content, c2.source
FROM clues c1 JOIN clues c2
ON c1.id != c2.id
WHERE (c1.content LIKE '%[共同关键词]%' AND c2.content LIKE '%[共同关键词]%')
  AND c1.source != c2.source
  AND c1.reliability != 'unreliable'
  AND c2.reliability != 'unreliable';
```

### 获取当前活跃待办事项（按优先级排序）
```sql
SELECT task_id, content, priority
FROM todos
WHERE status = 'pending'
ORDER BY
  CASE priority
    WHEN 'urgent' THEN 1
    WHEN 'high' THEN 2
    WHEN 'normal' THEN 3
    WHEN 'low' THEN 4
  END;
```

---

## 写入时机

每次执行六步归档时，**同步双写**：
- Markdown 文件（人类可读）
- SQLite 表（AI 检索）

`scripts/db_manager.py` 提供命令行接口执行数据库操作。
