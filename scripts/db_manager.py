#!/usr/bin/env python3
"""
TRPG SQLite 数据库管理器 — FTS5 全文搜索 + 交叉引用 + 导出。

Usage:
    python db_manager.py <db_path> search <keywords>         # 全文搜索(自动带出交叉引用)
    python db_manager.py <db_path> clue add [JSON]            # 添加线索
    python db_manager.py <db_path> clue link <id> <id>        # 建立交叉引用
    python db_manager.py <db_path> export [--limit 50]        # 导出活跃线索→Markdown
    python db_manager.py <db_path> stats                      # 统计概览
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path


def get_conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)  # ponytail: FTS5 needs extension loading
    return conn


# ==================== 初始化 (含 FTS5) ====================

def cmd_init(db_path):
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clues (
            id TEXT PRIMARY KEY, content TEXT NOT NULL,
            source TEXT NOT NULL, confidence TEXT NOT NULL,
            category TEXT DEFAULT 'core', status TEXT DEFAULT 'active',
            scene_id TEXT, linked_ids TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS npcs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT, appearance TEXT,
            stance TEXT, status TEXT DEFAULT 'active', faction TEXT,
            key_facts TEXT DEFAULT '[]', relationships TEXT DEFAULT '[]',
            scene_id TEXT, created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT NOT NULL,
            event TEXT NOT NULL, participants TEXT DEFAULT '[]',
            scene_id TEXT, related_clues TEXT DEFAULT '[]', notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS speculations (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
            basis_clues TEXT DEFAULT '[]', confidence TEXT NOT NULL,
            status TEXT DEFAULT 'active', scene_id TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS scenes (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT,
            status TEXT DEFAULT 'in_progress', started_at TEXT, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
            content TEXT NOT NULL, priority TEXT NOT NULL,
            status TEXT DEFAULT 'pending', scene_id TEXT,
            related_clues TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ★ FTS5 全文索引 (自动同步, 零维护)
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
    """)
    conn.commit()
    conn.close()
    print("Database initialized (FTS5 enabled).")


# ==================== 线索 CRUD ====================

def cmd_clue_add(db_path, clue_json=None):
    if clue_json is None:
        clue_json = sys.stdin.buffer.read().decode('utf-8-sig')
    data = json.loads(clue_json)
    conn = get_conn(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO clues
        (id, content, source, confidence, category, status, scene_id, linked_ids)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data.get('id'), data.get('content'), data.get('source', ''),
          data.get('confidence', '低'), data.get('category', 'core'),
          data.get('status', 'active'), data.get('scene_id'),
          data.get('linked_ids', '[]')))
    conn.commit()
    conn.close()
    print(f"Clue {data.get('id')} added.")


def cmd_clue_link(db_path, id_a, id_b):
    """建立双向交叉引用。"""
    conn = get_conn(db_path)
    for cid, lid in ((id_a, id_b), (id_b, id_a)):
        row = conn.execute("SELECT linked_ids FROM clues WHERE id=?", (cid,)).fetchone()
        if not row:
            print(f"Clue {cid} not found.")
            continue
        ids = json.loads(row['linked_ids'])
        if lid not in ids:
            ids.append(lid)
        conn.execute("UPDATE clues SET linked_ids=? WHERE id=?",
                     (json.dumps(ids, ensure_ascii=False), cid))
    conn.commit()
    conn.close()
    print(f"Linked: {id_a} ↔ {id_b}")


# ==================== FTS5 全文搜索 (带交叉引用) ====================

def cmd_search(db_path, keywords):
    """FTS5 全文搜索 → 自动带出 linked_ids 的关联线索。"""
    conn = get_conn(db_path)

    # FTS5 MATCH (支持 AND/OR/NOT 语法)
    query = " AND ".join(keywords.split())
    rows = conn.execute("""
        SELECT c.id, c.content, c.source, c.confidence, c.status, c.linked_ids
        FROM clues_fts f JOIN clues c ON f.rowid = c.rowid
        WHERE clues_fts MATCH ?
        ORDER BY rank
        LIMIT 30
    """, (query,)).fetchall()

    if not rows:
        print(f"No clues matching '{keywords}'")
        conn.close()
        return

    # 收集所有 linked_ids
    linked_set = set()
    for r in rows:
        linked_set.update(json.loads(r['linked_ids'] or '[]'))

    # 查关联线索
    linked_rows = {}
    if linked_set:
        placeholders = ','.join('?' * len(linked_set))
        lr = conn.execute(
            f"SELECT id, content, confidence FROM clues WHERE id IN ({placeholders})",
            list(linked_set)
        ).fetchall()
        linked_rows = {row['id']: row for row in lr}

    conn.close()

    print(f"\n{'='*60}")
    print(f"全文搜索: '{keywords}' — {len(rows)} 条匹配")
    print(f"{'='*60}")
    for r in rows:
        src_tag = f"[来源: {r['source']}]" if r['source'] else ""
        conf_tag = f"[确信: {r['confidence']}]" if r['confidence'] else ""
        print(f"\n  [{r['id']}] {src_tag} {conf_tag} | {r['status']}")
        print(f"  {r['content']}")

        # 带出交叉引用
        lids = json.loads(r['linked_ids'] or '[]')
        for lid in lids:
            if lid in linked_rows:
                lr = linked_rows[lid]
                print(f"    ↳ [{lr['id']}] [{lr['confidence']}] {lr['content'][:60]}")


# ==================== 导出 Markdown 视图 ====================

def cmd_export(db_path, limit=50):
    """导出活跃线索为 Markdown 视图 (01_线索板.md 格式)。"""
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT id, content, source, confidence, linked_ids
        FROM clues WHERE status='active'
        ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    if not rows:
        print("（无活跃线索）")
        return

    print(f"## 线索板 (最近 {len(rows)} 条)\n")
    print("| 编号 | 内容 | 来源 | 确信 | 关联 |")
    print("|------|------|------|------|------|")
    for r in rows:
        lids = json.loads(r['linked_ids'] or '[]')
        linked = ', '.join(lids[:3]) if lids else '—'
        content = r['content'][:60] + ('…' if len(r['content']) > 60 else '')
        print(f"| {r['id']} | {content} | {r['source']} | {r['confidence']} | {linked} |")


# ==================== 统计概览 ====================

def cmd_stats(db_path):
    conn = get_conn(db_path)
    clues_total = conn.execute("SELECT COUNT(*) FROM clues").fetchone()[0]
    clues_active = conn.execute("SELECT COUNT(*) FROM clues WHERE status='active'").fetchone()[0]
    npcs = conn.execute("SELECT COUNT(*) FROM npcs WHERE status='active'").fetchone()[0]
    events = conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0]
    specs = conn.execute("SELECT COUNT(*) FROM speculations WHERE status='active'").fetchone()[0]
    scenes = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]

    # 按确信度分布
    conf_dist = conn.execute("""
        SELECT confidence, COUNT(*) FROM clues GROUP BY confidence
    """).fetchall()
    conf_str = ' | '.join(f"{r[0]}:{r[1]}" for r in conf_dist)

    conn.close()

    print(f"线索 {clues_active}活跃/{clues_total}总计 | NPC {npcs} | 事件 {events}")
    print(f"推测 {specs}活跃 | 场景 {scenes}")
    print(f"确信度: {conf_str}")


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="TRPG Database (FTS5)")
    parser.add_argument("db_path", help="Path to trpg_data.db")
    parser.add_argument("command", choices=["init", "search", "clue", "stats", "export"])
    parser.add_argument("args", nargs="*")

    ns = parser.parse_args()

    if ns.command == "init":
        cmd_init(ns.db_path)

    elif ns.command == "search":
        if ns.args:
            cmd_search(ns.db_path, " ".join(ns.args))
        else:
            print("Usage: db_manager.py <db> search <keywords>")

    elif ns.command == "clue":
        if len(ns.args) >= 2:
            sub = ns.args[0]
            if sub == "add":
                cmd_clue_add(ns.db_path, " ".join(ns.args[1:]) if len(ns.args) > 1 else None)
            elif sub == "link" and len(ns.args) >= 3:
                cmd_clue_link(ns.db_path, ns.args[1], ns.args[2])
            else:
                print("Usage: db_manager.py <db> clue add '<json>' | clue link <id1> <id2>")
        else:
            print("Usage: db_manager.py <db> clue add|link ...")

    elif ns.command == "stats":
        cmd_stats(ns.db_path)

    elif ns.command == "export":
        limit = 50
        if ns.args and ns.args[0].startswith("--limit="):
            limit = int(ns.args[0].split("=")[1])
        cmd_export(ns.db_path, limit)


if __name__ == "__main__":
    main()
