#!/usr/bin/env python3
"""
TRPG SQLite 数据库管理器 — FTS5 + 角色状态追踪 + 交叉引用 + 导出。

Usage:
    python db_manager.py <db_path> search <keywords>              # 全文搜索
    python db_manager.py <db_path> clue add [JSON]                # 添加线索
    python db_manager.py <db_path> clue link <id> <id>            # 交叉引用
    python db_manager.py <db_path> export [--limit 50]            # 导出→Markdown
    python db_manager.py <db_path> stats                          # 统计概览
    python db_manager.py <db_path> state init <name> <type> <hp_max> <san_max> [--dex N]
    python db_manager.py <db_path> state add <name> [--hp N] [--san N] [--loc S] [--status S] --reason S
    python db_manager.py <db_path> state query <name>             # 变更历史
    python db_manager.py <db_path> state current [name]           # 当前状态(可选过滤)
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

        -- ★ v1.6.0: 角色状态追踪 (事件溯源·JSON键值池——兼容CoC/DND/泛规则系统)
        DROP TABLE IF EXISTS char_state_log;
        DROP TABLE IF EXISTS char_base;
        CREATE TABLE IF NOT EXISTS char_base (
            char_name   TEXT PRIMARY KEY,
            char_type   TEXT NOT NULL DEFAULT 'pc',
            base_stats  TEXT NOT NULL DEFAULT '{}',  -- JSON: {"hp":12,"san":60,"ac":15}
            created_at  TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS char_state_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            char_name   TEXT NOT NULL,
            seq         INTEGER NOT NULL,
            deltas      TEXT NOT NULL DEFAULT '{}',  -- JSON: {"hp":-3,"san":-1}
            loc_new     TEXT DEFAULT NULL,
            status_new  TEXT DEFAULT NULL,
            reason      TEXT NOT NULL,
            clue_ref    TEXT DEFAULT NULL,
            scene_ref   TEXT DEFAULT NULL,
            round       INTEGER DEFAULT NULL,
            note        TEXT DEFAULT NULL,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (char_name) REFERENCES char_base(char_name)
        );
        CREATE INDEX IF NOT EXISTS idx_csl_name ON char_state_log(char_name);
        CREATE INDEX IF NOT EXISTS idx_csl_scene ON char_state_log(scene_ref);

        -- ★ v1.6.2: 显示词典 — 键值→中文名（AI可用作枚举查询）
        CREATE TABLE IF NOT EXISTS dict_labels (
            category TEXT NOT NULL,   -- 'pool' | 'reason' | 'status'
            key      TEXT NOT NULL,
            cn_name  TEXT NOT NULL,
            PRIMARY KEY (category, key)
        );
        INSERT OR IGNORE INTO dict_labels VALUES
            ('pool','hp','生命值'),('pool','san','理智值'),('pool','mp','魔力值'),
            ('pool','luck','幸运'),('pool','ac','护甲等级'),
            ('pool','spell_l1','1环法术位'),('pool','spell_l2','2环法术位'),
            ('pool','spell_l3','3环法术位'),('pool','spell_l4','4环法术位'),
            ('pool','spell_l5','5环法术位'),('pool','spell_l6','6环法术位'),
            ('pool','spell_l7','7环法术位'),('pool','spell_l8','8环法术位'),
            ('pool','spell_l9','9环法术位'),('pool','ki','气'),('pool','rage','狂暴'),
            ('reason','combat_melee','近战伤害'),('reason','combat_weapon','武器伤害'),
            ('reason','combat_fire','火焰伤害'),('reason','combat_fall','坠落伤害'),
            ('reason','env_cold','寒冷'),('reason','env_heat','高温'),
            ('reason','env_poison','中毒'),('reason','sanity_pass','SAN检定通过'),
            ('reason','sanity_fail','SAN检定失败'),('reason','spell_consume','法术消耗'),
            ('reason','rest_short','短休恢复'),('reason','rest_long','长休恢复'),
            ('reason','death_save','死亡豁免'),('reason','heal_natural','自然恢复'),
            ('reason','heal_magic','法术恢复'),('reason','attr_change','属性变更'),
            ('reason','status_add','状态施加'),('reason','status_remove','状态解除'),
            ('reason','init','初始注册'),
            ('status','unconscious','昏迷'),('status','active','正常'),
            ('status','ko','击倒'),('status','dead','死亡'),
            ('status','mad','疯狂'),('status','stable','稳定');
    """)
    conn.commit()
    conn.close()
    print("Database initialized (FTS5 + char_state + dict_labels).")


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

# ==================== 角色状态追踪 v1.6.0 (JSON键值池) ====================

def cmd_state_init(db_path, name, ctype, base_stats):
    """base_stats: dict of pool->max, e.g. {"hp":12,"san":60,"ac":15}"""
    conn = get_conn(db_path)
    conn.execute("INSERT OR REPLACE INTO char_base VALUES (?,?,?,datetime('now','localtime'))",
                 (name, ctype, json.dumps(base_stats, ensure_ascii=False)))
    conn.commit(); conn.close()
    pools = ", ".join(f"{k}={v}" for k,v in base_stats.items())
    print(f"state_init: {name} [{ctype}] {pools}")

def cmd_state_add(db_path, name, deltas, loc, status, reason, clue_ref, scene_ref, round_n, note):
    """deltas: dict of pool->delta, e.g. {"hp":-3,"san":-1}"""
    conn = get_conn(db_path)
    seq_row = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM char_state_log WHERE char_name=?", (name,)).fetchone()
    seq = seq_row[0]
    conn.execute("""INSERT INTO char_state_log
        (char_name,seq,deltas,loc_new,status_new,reason,clue_ref,scene_ref,round,note)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (name, seq, json.dumps(deltas, ensure_ascii=False), loc, status, reason, clue_ref, scene_ref, round_n, note))
    conn.commit(); conn.close()
    delta_str = " ".join(f"{k}{v:+d}" for k,v in deltas.items())
    print(f"state_add: {name} seq={seq} {delta_str} reason={reason}")

def _load_dict(conn, category):
    rows = conn.execute("SELECT key, cn_name FROM dict_labels WHERE category=?", (category,)).fetchall()
    return {r['key']: r['cn_name'] for r in rows}

def cmd_state_query(db_path, name):
    conn = get_conn(db_path)
    pool_dict = _load_dict(conn, 'pool')
    reason_dict = _load_dict(conn, 'reason')
    rows = conn.execute("SELECT seq,deltas,reason,clue_ref,scene_ref,round FROM char_state_log WHERE char_name=? ORDER BY seq", (name,)).fetchall()
    if not rows: print(f"No changes for {name}"); conn.close(); return
    print(f"\n=== {name} ===")
    for r in rows:
        deltas = json.loads(r['deltas'])
        d_str = " ".join("{0}{1:+d}".format(pool_dict.get(k,k), v) for k,v in deltas.items())
        parts = ["#{0}".format(r['seq']), d_str, "{0}".format(reason_dict.get(r['reason'], r['reason']))]
        if r['clue_ref']: parts.append("[{0}]".format(r['clue_ref']))
        print(" ".join(parts))
    conn.close()

def cmd_state_current(db_path, name=None):
    """Show current state. Vertical per character, Chinese labels from dict_labels."""
    conn = get_conn(db_path)
    pool_dict = _load_dict(conn, 'pool')
    status_dict = _load_dict(conn, 'status')
    if name:
        bases = conn.execute("SELECT char_name,char_type,base_stats FROM char_base WHERE char_name=?", (name,)).fetchall()
    else:
        bases = conn.execute("SELECT char_name,char_type,base_stats FROM char_base ORDER BY char_name").fetchall()
    if not bases: print("No characters tracked."); conn.close(); return

    char_data = []
    for b in bases:
        base = json.loads(b['base_stats'])
        delta_rows = conn.execute("SELECT deltas FROM char_state_log WHERE char_name=? ORDER BY seq", (b['char_name'],)).fetchall()
        totals = dict(base)
        for dr in delta_rows:
            for k, v in json.loads(dr['deltas']).items():
                totals[k] = totals.get(k, 0) + v
        last = conn.execute("SELECT loc_new,status_new FROM char_state_log WHERE char_name=? AND (loc_new IS NOT NULL OR status_new IS NOT NULL) ORDER BY seq DESC LIMIT 1", (b['char_name'],)).fetchone()
        char_data.append({
            'name': b['char_name'], 'type': b['char_type'],
            'base': base, 'totals': totals,
            'loc': last['loc_new'] if last and last['loc_new'] else '-',
            'status': status_dict.get(last['status_new'], last['status_new']) if last and last['status_new'] else '-',
        })

    for cd in char_data:
        fixed = []; floating = []
        for k in sorted(cd['base'].keys()):
            mx = cd['base'][k]; cur = cd['totals'].get(k,'?')
            cn = pool_dict.get(k, k); net = cur - mx if isinstance(cur,int) and isinstance(mx,int) else 0
            fixed.append("{0}: {1}".format(cn, mx))
            if net != 0: floating.append("{0}: {1:+d}".format(cn, net))
        print("=== {0} ({1}) ===".format(cd['name'], cd['type']))
        if floating: print("  浮动: " + " | ".join(floating))
        print("  固定: " + " | ".join(fixed))
        print("  位置: {0} | 状态: {1}".format(cd['loc'], cd['status']))
        print()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="TRPG Database (FTS5)")
    parser.add_argument("db_path", help="Path to trpg_data.db")
    parser.add_argument("command", choices=["init", "search", "clue", "stats", "export", "state"])
    parser.add_argument("args", nargs=argparse.REMAINDER)

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

    elif ns.command == "state":
        if len(ns.args) < 1:
            print("Usage: state init|add|query|current|list")
            return
        sub = ns.args[0]; rest = ns.args[1:]
        if sub == "init":
            # state init <name> <type> [--hp N] [--san N] [--ac N] [--any N ...]
            if len(rest) < 2: print("Usage: state init <name> <type> [--hp N] [--san N] [--ac N] ..."); return
            name, ctype = rest[0], rest[1]
            base_stats = {}; i = 2
            while i < len(rest):
                if rest[i].startswith('--') and i+1 < len(rest) and not rest[i+1].startswith('--'):
                    try:
                        base_stats[rest[i][2:]] = int(rest[i+1])
                    except ValueError:
                        base_stats[rest[i][2:]] = rest[i+1]
                    i += 2
                else: i += 1
            if not base_stats: print("Need at least one --pool value (e.g. --hp 12)"); return
            cmd_state_init(ns.db_path, name, ctype, base_stats)
        elif sub == "add":
            # state add <name> [--hp N] [--san N] [--any N ...] --reason S [--loc S] [--status S] [--clue S] [--scene S] [--round N] [--note S]
            if len(rest) < 1: print("Usage: state add <name> --reason S [--hp N] ..."); return
            name = rest[0]
            deltas = {}; reason = None; loc = None; status = None; clue = None; scene = None; round_n = None; note = None
            i = 1
            while i < len(rest):
                if rest[i] == '--reason' and i+1 < len(rest): reason = rest[i+1]; i += 2
                elif rest[i] == '--loc' and i+1 < len(rest): loc = rest[i+1]; i += 2
                elif rest[i] == '--status' and i+1 < len(rest): status = rest[i+1]; i += 2
                elif rest[i] == '--clue' and i+1 < len(rest): clue = rest[i+1]; i += 2
                elif rest[i] == '--scene' and i+1 < len(rest): scene = rest[i+1]; i += 2
                elif rest[i] == '--round' and i+1 < len(rest): round_n = int(rest[i+1]); i += 2
                elif rest[i] == '--note' and i+1 < len(rest): note = rest[i+1]; i += 2
                elif rest[i].startswith('--') and i+1 < len(rest):
                    try: deltas[rest[i][2:]] = int(rest[i+1])
                    except ValueError: deltas[rest[i][2:]] = rest[i+1]
                    i += 2
                else: i += 1
            if not reason: print("Usage: state add <name> --reason S [--hp N] [--any N] ..."); return
            cmd_state_add(ns.db_path, name, deltas, loc, status, reason, clue, scene, round_n, note)
        elif sub == "query":
            if not rest: print("Usage: state query <name>"); return
            cmd_state_query(ns.db_path, rest[0])
        elif sub == "current":
            cmd_state_current(ns.db_path, rest[0] if rest else None)
        elif sub == "list":
            cmd_state_current(ns.db_path, None)
        else:
            print(f"Unknown state sub: {sub!r} rest={rest!r}; Usage: state init|add|query|current|list")

    elif ns.command == "export":
        limit = 50
        if ns.args and ns.args[0].startswith("--limit="):
            limit = int(ns.args[0].split("=")[1])
        cmd_export(ns.db_path, limit)


if __name__ == "__main__":
    main()
