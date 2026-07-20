#!/usr/bin/env python3
"""
TRPG SQLite 数据库管理器 — 命令行接口。

Usage:
    python db_manager.py <db_path> init                  # 初始化数据库
    python db_manager.py <db_path> clue add [JSON]       # 添加线索
    python db_manager.py <db_path> clue search <keyword> # 搜索线索
    python db_manager.py <db_path> npc list              # 列出所有NPC
    python db_manager.py <db_path> timeline [scene_id]   # 按场景查看时间线
    python db_manager.py <db_path> todo list [priority]  # 查看待办事项
    python db_manager.py <db_path> crossref <keyword>    # 跨线索交叉检索
"""

import sys
import json
import sqlite3
import argparse
from pathlib import Path


def get_conn(db_path):
    """Get a database connection."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def cmd_init(db_path):
    """Initialize database tables."""
    conn = get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clues (
            id TEXT PRIMARY KEY, content TEXT NOT NULL, source TEXT NOT NULL,
            reliability TEXT NOT NULL, category TEXT DEFAULT 'core',
            status TEXT DEFAULT 'active', scene_id TEXT,
            tags TEXT DEFAULT '[]', related_clues TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS npcs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT, appearance TEXT,
            stance TEXT, status TEXT DEFAULT 'active', faction TEXT,
            key_facts TEXT DEFAULT '[]', relationships TEXT DEFAULT '[]',
            scene_id TEXT, tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
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
            status TEXT DEFAULT 'active', scene_id TEXT, tags TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS scenes (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT,
            status TEXT DEFAULT 'in_progress', started_at TEXT, completed_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
            content TEXT NOT NULL, priority TEXT NOT NULL,
            status TEXT DEFAULT 'pending', scene_id TEXT,
            related_clues TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()
    print("Database initialized successfully.")


def cmd_clue_add(db_path, clue_json=None):
    """Add a clue from JSON string (or stdin if None)."""
    if clue_json is None:
        clue_json = sys.stdin.buffer.read().decode('utf-8-sig')
    data = json.loads(clue_json)
    conn = get_conn(db_path)
    conn.execute("""
        INSERT OR REPLACE INTO clues (id, content, source, reliability, category, status, scene_id, tags, related_clues)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('id'), data.get('content'), data.get('source', ''),
        data.get('reliability', 'unverified'), data.get('category', 'core'),
        data.get('status', 'active'), data.get('scene_id'), data.get('tags', '[]'),
        data.get('related_clues', '[]')
    ))
    conn.commit()
    conn.close()
    print(f"Clue {data.get('id')} added.")


def cmd_clue_search(db_path, keyword):
    """Search clues by keyword."""
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT id, content, source, reliability, status, tags
        FROM clues
        WHERE content LIKE ? OR tags LIKE ?
        ORDER BY created_at DESC
    """, (f'%{keyword}%', f'%{keyword}%')).fetchall()
    conn.close()

    if not rows:
        print(f"No clues found matching '{keyword}'")
        return

    print(f"\n{'='*60}")
    print(f"Search results for: '{keyword}' ({len(rows)} found)")
    print(f"{'='*60}")
    for r in rows:
        print(f"\n[{r['id']}] {r['reliability']} | {r['status']}")
        print(f"  {r['content']}")
        print(f"  Source: {r['source']}  Tags: {r['tags']}")


def cmd_npc_list(db_path):
    """List all active NPCs."""
    conn = get_conn(db_path)
    rows = conn.execute("""
        SELECT id, name, role, stance, status
        FROM npcs WHERE status = 'active'
        ORDER BY name
    """).fetchall()
    conn.close()

    print(f"\nActive NPCs ({len(rows)}):")
    print("-" * 60)
    for r in rows:
        print(f"  [{r['id']}] {r['name']} — {r['role']} ({r['stance']})")


def cmd_timeline(db_path, scene_id=None):
    """View timeline events, optionally filtered by scene."""
    conn = get_conn(db_path)
    if scene_id:
        rows = conn.execute(
            "SELECT event_time, event, participants FROM timeline_events WHERE scene_id=? ORDER BY event_time",
            (scene_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT event_time, event, participants, scene_id FROM timeline_events ORDER BY event_time"
        ).fetchall()
    conn.close()

    print(f"\nTimeline ({len(rows)} events):")
    print("-" * 60)
    for r in rows:
        scene = f" [{r.get('scene_id', '')}]" if not scene_id else ""
        print(f"  {r['event_time']}{scene}: {r['event']}")


def cmd_todo_list(db_path, priority=None):
    """List todos, optionally filtered by priority."""
    conn = get_conn(db_path)
    if priority:
        rows = conn.execute(
            "SELECT task_id, content, priority FROM todos WHERE status='pending' AND priority=?",
            (priority,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT task_id, content, priority FROM todos WHERE status='pending' "
            "ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 "
            "WHEN 'normal' THEN 3 WHEN 'low' THEN 4 END"
        ).fetchall()
    conn.close()

    print(f"\nPending Todos ({len(rows)}):")
    print("-" * 60)
    for r in rows:
        emoji = {"urgent": "🔴🔴", "high": "🔴", "normal": "🟡", "low": "🟢"}.get(r['priority'], "⚪")
        print(f"  {emoji} [{r['task_id']}] {r['content']}")


def cmd_crossref(db_path, keyword):
    """Cross-reference search across clues and speculations."""
    conn = get_conn(db_path)

    clues = conn.execute(
        "SELECT id, content, source FROM clues WHERE content LIKE ?",
        (f'%{keyword}%',)
    ).fetchall()

    specs = conn.execute(
        "SELECT id, title, confidence FROM speculations WHERE content LIKE ? OR title LIKE ?",
        (f'%{keyword}%', f'%{keyword}%')
    ).fetchall()

    timeline = conn.execute(
        "SELECT event_time, event FROM timeline_events WHERE event LIKE ?",
        (f'%{keyword}%',)
    ).fetchall()

    npcs = conn.execute(
        "SELECT id, name, role FROM npcs WHERE name LIKE ? OR key_facts LIKE ?",
        (f'%{keyword}%', f'%{keyword}%')
    ).fetchall()

    conn.close()

    print(f"\nCross-reference for: '{keyword}'")
    print("=" * 60)

    if clues:
        print(f"\n📋 Clues ({len(clues)}):")
        for c in clues:
            print(f"  [{c['id']}] {c['content'][:80]}...")

    if specs:
        print(f"\n💡 Speculations ({len(specs)}):")
        for s in specs:
            print(f"  [{s['id']}] [{s['confidence']}] {s['title']}")

    if timeline:
        print(f"\n🕐 Timeline ({len(timeline)}):")
        for t in timeline:
            print(f"  {t['event_time']}: {t['event'][:80]}...")

    if npcs:
        print(f"\n👤 NPCs ({len(npcs)}):")
        for n in npcs:
            print(f"  [{n['id']}] {n['name']} — {n['role']}")

    if not (clues or specs or timeline or npcs):
        print("No results found.")


def main():
    parser = argparse.ArgumentParser(description="TRPG Database Manager")
    parser.add_argument("db_path", help="Path to trpg_data.db")
    parser.add_argument("command", choices=[
        "init", "clue", "npc", "timeline", "todo", "crossref"
    ])
    parser.add_argument("args", nargs="*", help="Additional arguments")

    args_ns = parser.parse_args()

    if args_ns.command == "init":
        cmd_init(args_ns.db_path)
    elif args_ns.command == "clue":
        if len(args_ns.args) >= 1 and args_ns.args[0] == "add":
            json_data = " ".join(args_ns.args[1:]) if len(args_ns.args) > 1 else None
            cmd_clue_add(args_ns.db_path, json_data)
        elif len(args_ns.args) >= 2 and args_ns.args[0] == "search":
            cmd_clue_search(args_ns.db_path, args_ns.args[1])
        else:
            print("Usage: db_manager.py <db> clue add [<json>] | clue search <keyword>")
    elif args_ns.command == "npc":
        cmd_npc_list(args_ns.db_path)
    elif args_ns.command == "timeline":
        scene = args_ns.args[0] if args_ns.args else None
        cmd_timeline(args_ns.db_path, scene)
    elif args_ns.command == "todo":
        priority = args_ns.args[0] if args_ns.args else None
        cmd_todo_list(args_ns.db_path, priority)
    elif args_ns.command == "crossref":
        if args_ns.args:
            cmd_crossref(args_ns.db_path, args_ns.args[0])
        else:
            print("Usage: db_manager.py <db> crossref <keyword>")


if __name__ == "__main__":
    main()
