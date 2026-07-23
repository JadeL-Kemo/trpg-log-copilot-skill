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
            priority TEXT DEFAULT 'medium',
            tags TEXT DEFAULT '[]',
            category TEXT DEFAULT 'core', status TEXT DEFAULT 'active',
            scene_id TEXT, linked_ids TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        -- v1.7.0: 'confidence' column now stores 'verified' value (confirmed/pending/excluded)
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
            category TEXT DEFAULT 'story',
            event_date TEXT DEFAULT NULL,
            timeline_status TEXT DEFAULT 'canon',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- ★ FTS5 全文索引 (v1.7.1: tags列支持中文→拼音/英文多词搜索)
        DROP TABLE IF EXISTS clues_fts;
        CREATE VIRTUAL TABLE clues_fts USING fts5(
            content, source, tags, content=clues, content_rowid=rowid
        );
        CREATE TRIGGER IF NOT EXISTS clues_ai AFTER INSERT ON clues BEGIN
            INSERT INTO clues_fts(rowid, content, source, tags)
            VALUES (new.rowid, new.content, new.source, new.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS clues_ad AFTER DELETE ON clues BEGIN
            INSERT INTO clues_fts(clues_fts, rowid, content, source, tags)
            VALUES ('delete', old.rowid, old.content, old.source, old.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS clues_au AFTER UPDATE ON clues BEGIN
            INSERT INTO clues_fts(clues_fts, rowid, content, source, tags)
            VALUES ('delete', old.rowid, old.content, old.source, old.tags);
            INSERT INTO clues_fts(rowid, content, source, tags)
            VALUES (new.rowid, new.content, new.source, new.tags);
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
            game_time   TEXT DEFAULT NULL,
            game_date   TEXT DEFAULT NULL,
            note        TEXT DEFAULT NULL,
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (char_name) REFERENCES char_base(char_name)
        );
        CREATE INDEX IF NOT EXISTS idx_csl_name ON char_state_log(char_name);
        CREATE INDEX IF NOT EXISTS idx_csl_scene ON char_state_log(scene_ref);

        CREATE TABLE IF NOT EXISTS npc_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_a TEXT NOT NULL,
            npc_b TEXT NOT NULL,
            rel_type TEXT NOT NULL,
            direction TEXT DEFAULT 'mutual',
            source_ref TEXT DEFAULT NULL,
            notes TEXT DEFAULT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_nrel_a ON npc_relations(npc_a);
        CREATE INDEX IF NOT EXISTS idx_nrel_b ON npc_relations(npc_b);

        CREATE TABLE IF NOT EXISTS narrative_chunks (
            scene_id   TEXT NOT NULL,
            file_name  TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (scene_id, file_name)
        );
        DROP TABLE IF EXISTS narrative_fts;
        CREATE VIRTUAL TABLE narrative_fts USING fts5(scene_id, chunk_text, content=narrative_chunks, content_rowid=rowid);
        CREATE TRIGGER IF NOT EXISTS nc_ai AFTER INSERT ON narrative_chunks BEGIN
            INSERT INTO narrative_fts(rowid, scene_id, chunk_text) VALUES (new.rowid, new.scene_id, new.chunk_text);
        END;

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
            ('status','mad','疯狂'),('status','stable','稳定'),
            ('verified','confirmed','已证实'),('verified','pending','待验证'),
            ('verified','excluded','已排除'),
            ('confidence','high','高置信'),('confidence','medium','中置信'),
            ('confidence','low','低置信'),('confidence','none','无置信'),
            ('confidence','axiom','铁律');
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
        # Fallback: LIKE search for CJK when FTS5 tokenizer fails
        rows = conn.execute("""SELECT id, content, source, confidence, status, linked_ids
            FROM clues WHERE content LIKE ? OR source LIKE ? OR tags LIKE ? LIMIT 30""",
            (f"%{keywords}%",)*3).fetchall()
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
    chars = conn.execute("SELECT COUNT(*) FROM char_base").fetchone()[0]
    states = conn.execute("SELECT COUNT(*) FROM char_state_log").fetchone()[0]

    # 按确信度分布
    conf_dist = conn.execute("""
        SELECT confidence, COUNT(*) FROM clues GROUP BY confidence
    """).fetchall()
    conf_str = ' | '.join(f"{r[0]}:{r[1]}" for r in conf_dist)

    conn.close()

    print(f"线索 {clues_active}活跃/{clues_total}总计 | NPC {npcs} | 事件 {events}")
    print(f"角色 {chars} | 状态变更 {states}")
    print(f"确信度: {conf_str}")


# ==================== CLI ====================

# ==================== 角色状态追踪 v1.6.0 (JSON键值池) ====================

def cmd_state_init(db_path, name, ctype, base_stats):
    """base_stats: dict of pool->max, e.g. {"hp":12,"san":60,"ac":15}"""
    if not name or not ctype:
        print("ERROR: name and type required"); return
    for k, v in list(base_stats.items()):
        if not _validate_pool(k): return
        iv = _validate_int(v, k); 
        if iv is None or iv <= 0: print("ERROR: pool '{0}' value must be positive integer".format(k)); return
    conn = get_conn(db_path)
    conn.execute("INSERT OR REPLACE INTO char_base VALUES (?,?,?,datetime('now','localtime'))",
                 (name, ctype, json.dumps(base_stats, ensure_ascii=False)))
    conn.commit(); conn.close()
    pools = ", ".join(f"{k}={v}" for k,v in base_stats.items())
    print(f"state_init: {name} [{ctype}] {pools}")

def cmd_state_add(db_path, name, deltas, loc, status, reason, clue_ref, scene_ref, round_n, game_time, game_date, note, do_export=False):
    """deltas: dict of pool->delta, e.g. {"hp":-3,"san":-1}"""
    # Validate
    if not name: print("ERROR: name required"); return
    if not deltas: print("ERROR: at least one --pool delta required"); return
    if not _validate_snake(reason, "reason"): return
    for k, v in deltas.items():
        if not _validate_pool(k): return
        iv = _validate_int(v, k)
        if iv is None: return
    # Check character exists (graceful on uninitialized DB)
    conn = get_conn(db_path)
    try:
        exists = conn.execute("SELECT 1 FROM char_base WHERE char_name=?", (name,)).fetchone()
    except:
        print("ERROR: database not initialized — run 'init' first")
        conn.close(); return
    if not exists:
        print("ERROR: '{0}' not in char_base — use 'state init' first".format(name))
        conn.close(); return
    seq_row = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM char_state_log WHERE char_name=?", (name,)).fetchone()
    seq = seq_row[0]
    conn.execute("""INSERT INTO char_state_log
        (char_name,seq,deltas,loc_new,status_new,reason,clue_ref,scene_ref,round,game_time,game_date,note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, seq, json.dumps(deltas, ensure_ascii=False), loc, status, reason, clue_ref, scene_ref, round_n, game_time, game_date, note))
    conn.commit(); conn.close()
    delta_str = " ".join(f"{k}{v:+d}" for k,v in deltas.items())
    print(f"state_add: {name} seq={seq} {delta_str} reason={reason}")
    if do_export:
        _run_export(db_path)

def cmd_trace(db_path, clue_id):
    """Trace event chain from a clue: linked clues + state changes + NPCs."""
    conn = get_conn(db_path)
    clue = conn.execute("SELECT * FROM clues WHERE id=?", (clue_id,)).fetchone()
    if not clue:
        print("Clue {0} not found".format(clue_id)); conn.close(); return

    print("=== {0} ===".format(clue_id))
    print("  {0}".format(clue['content']))
    print("  source: {0} | confidence: {1}".format(clue['source'], clue['confidence']))
    linked = json.loads(clue['linked_ids'] or '[]')
    if linked:
        print("\n  Direct links:")
        for lid in linked:
            lc = conn.execute("SELECT content, confidence FROM clues WHERE id=?", (lid,)).fetchone()
            if lc:
                print("    {0} [{1}] {2}".format(lid, lc['confidence'], lc['content']))
            else:
                print("    {0} (MD only)".format(lid))

    # State changes referencing this clue
    states = conn.execute("SELECT char_name, deltas, reason, scene_ref, round FROM char_state_log WHERE clue_ref=?", (clue_id,)).fetchall()
    if states:
        print("\n  State changes:")
        for s in states:
            d = json.loads(s['deltas'])
            d_str = " ".join("{0}{1:+d}".format(k,v) for k,v in d.items())
            print("    {0}: {1} ({2})".format(s['char_name'], d_str, s['reason']))

    # NPCs in same scene
    scene = clue['scene_id']
    if scene:
        npcs = conn.execute("SELECT char_name, loc_new, status_new FROM char_state_log WHERE scene_ref=?", (scene,)).fetchall()
        if npcs:
            print("\n  Present in scene {0}:".format(scene))
            for n in npcs:
                print("    {0} loc={1} status={2}".format(n['char_name'], n['loc_new'] or '-', n['status_new'] or '-'))

    conn.close()

def cmd_npcs(db_path, keyword=None):
    """Search NPCs. Use import_md.py to populate first."""
    conn = get_conn(db_path)
    if keyword:
        rows = conn.execute("SELECT * FROM npcs WHERE name LIKE ? OR role LIKE ? OR faction LIKE ?",
            ("%{0}%".format(keyword),)*3).fetchall()
    else:
        rows = conn.execute("SELECT * FROM npcs ORDER BY name").fetchall()
    if not rows: print("No NPCs. Run 'import_md.py' first."); conn.close(); return
    print("{0} NPCs:".format(len(rows)))
    for r in rows:
        facts = json.loads(r['key_facts'] or '[]')
        rels = json.loads(r['relationships'] or '[]')
        print("  {0} [{1}] faction={2} stance={3}".format(r['name'], r['role'], r['faction'] or '-', r['stance'] or '-'))
        if facts: print("    facts: {0}".format(", ".join(facts)))
        if rels: print("    rels: {0}".format(", ".join(rels)))
    conn.close()

def cmd_events(db_path, char=None, since=None, limit=30):
    """Per-character dual-track timeline: game events mixed + log-only tail."""
    conn = get_conn(db_path)
    pool_dict = _load_dict(conn, 'pool'); reason_dict = _load_dict(conn, 'reason')
    
    game_rows = []; log_rows = []
    
    # 1. Timeline events (always game-time)
    sql = "SELECT event_time, event, participants FROM timeline_events"
    params = []
    if char: sql += " WHERE participants LIKE ?"; params.append("%{0}%".format(char))
    if since:
        clause = "WHERE" if "WHERE" not in sql else "AND"
        sql += " {0} event_time >= ?".format(clause); params.append(since)
    sql += " ORDER BY event_time"
    for r in conn.execute(sql, params):
        game_rows.append(('timeline', r['event_time'] or '', r['event'],
                          json.loads(r['participants'] or '[]'), None))
    
    # 2. State changes — split by game_time presence, group by game_date
    sql = "SELECT char_name, deltas, reason, game_time, game_date, created_at, clue_ref FROM char_state_log"
    params = []
    conditions = []
    if char: conditions.append("char_name = ?"); params.append(char)
    if conditions: sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY game_date, game_time, created_at"
    
    for r in conn.execute(sql, params):
        d = json.loads(r['deltas'])
        delta_str = " ".join("{0} {1:+d}".format(pool_dict.get(k, k), v) for k, v in d.items())
        desc = "{0}: {1}".format(r['char_name'], delta_str)
        extra = "{0} ({1})".format(reason_dict.get(r['reason'], r['reason']), r['clue_ref'] or '-')
        if r['game_time'] or r['game_date']:
            ts = (r['game_date'] + ' ' if r['game_date'] else '') + (r['game_time'] if r['game_time'] else '')
            game_rows.append(('state', ts.strip(), desc, [], extra))
        else:
            log_rows.append((r['created_at'] or '', desc, extra))
    
    game_rows.sort(key=lambda x: x[1])
    
    if not game_rows and not log_rows:
        print("No events found{0}.".format(" for " + char if char else ""))
        conn.close(); return
    
    total = len(game_rows) + len(log_rows)
    if total > limit: game_rows = game_rows[:max(limit-len(log_rows), 0)]
    
    title = char or "全局"
    print("=" * 60)
    print("  {0} — 游戏内时间线".format(title))
    print("=" * 60)
    
    if not game_rows:
        print("  (无游戏时间记录 — 请用 state add --time HH:MM 标注)")
    
    for src, ts, desc, parts, extra in game_rows:
        if src == 'timeline':
            chars = ", ".join(parts[:5]) + ("..." if len(parts) > 5 else "")
            print("  ⏱ {0}  {1:<30} [{2}]".format(ts, desc, chars))
        else:
            print("  💥 {0}  {1:<30} {2}".format(ts, desc, extra))
    
    if log_rows:
        print("\n  ── 以下为录入时间戳(非游戏时间) ──")
        for ts, desc, extra in log_rows:
            print("  📝 {0}  {1:<30} {2}".format(ts, desc, extra))
    conn.close()

def cmd_timeline(db_path, since=None, char=None):
    """Query timeline events. Use import_md.py to populate first."""
    conn = get_conn(db_path)
    sql = "SELECT * FROM timeline_events"
    params = []
    conditions = []
    if since: conditions.append("event_time >= ?"); params.append(since)
    if char: conditions.append("participants LIKE ?"); params.append("%{0}%".format(char))
    if conditions: sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY event_time"
    rows = conn.execute(sql, params).fetchall()
    if not rows: print("No events. Run 'import_md.py' first."); conn.close(); return
    for r in rows:
        parts = json.loads(r['participants'] or '[]')
        clues = json.loads(r['related_clues'] or '[]')
        print("  {0} | {1} | participants: {2}".format(r['event_time'], r['event'], ", ".join(parts)))
        if clues: print("    clues: {0}".format(", ".join(clues)))
    conn.close()

def _clue_visible_to(conn, clue_id, character):
    """Check if a clue is visible to given character based on scene membership + sharing."""
    if not character: return True  # GM view — all visible
    
    # Source = KP旁白 → always visible
    source = conn.execute("SELECT source FROM clues WHERE id=?", (clue_id,)).fetchone()
    if source and source['source'] == 'KP旁白': return True
    
    # Shared via timeline event? (any event with this clue + this char)
    shared = conn.execute(
        "SELECT 1 FROM timeline_events WHERE related_clues LIKE ? AND participants LIKE ?",
        ("%{0}%".format(clue_id), "%{0}%".format(character))).fetchone()
    if shared: return True
    
    # TODO: full scene membership check (needs scene_id on clues table)
    return False

def cmd_relations(db_path, npc=None):
    """Display NPC relations from npc_relations edge table."""
    conn = get_conn(db_path)
    dir_disp = {'mutual': '↔', 'a_to_b': '→', 'b_to_a': '←', 'oneway': '→'}
    if npc:
        rows = conn.execute(
            "SELECT npc_a,npc_b,rel_type,direction,source_ref FROM npc_relations WHERE npc_a=? OR npc_b=? ORDER BY npc_a,npc_b",
            (npc, npc)).fetchall()
        if not rows:
            print("{0}: 无关系记录".format(npc))
        else:
            print("{0} 的关系 ({1}条):".format(npc, len(rows)))
            for r in rows:
                arrow = dir_disp.get(r['direction'], '↔')
                if r['npc_a'] == npc:
                    print("  {0} {1}({2}) {3}".format(arrow, r['npc_b'], r['rel_type'] or '未知', (' ['+r['source_ref']+']' if r['source_ref'] else '')))
                else:
                    print("  {0} {1}({2}) {3}".format(dir_disp.get('b_to_a', '←'), r['npc_a'], r['rel_type'] or '未知', (' ['+r['source_ref']+']' if r['source_ref'] else '')))
    else:
        rows = conn.execute("SELECT npc_a,npc_b,rel_type,direction FROM npc_relations ORDER BY npc_a,npc_b").fetchall()
        if not rows:
            print("无关系记录")
        else:
            print("全部关系 ({0}条):".format(len(rows)))
            for r in rows:
                arrow = dir_disp.get(r['direction'], '↔')
                print("  {0} {1} {2}({3})".format(r['npc_a'], arrow, r['npc_b'], r['rel_type'] or '-'))
    conn.close()

def cmd_graph(db_path, entity, as_char=None):
    """Complete relationship graph — with optional per-character visibility filter."""
    conn = get_conn(db_path)
    pool_dict = _load_dict(conn, 'pool'); reason_dict = _load_dict(conn, 'reason')
    
    view_tag = " [视角: {0}]".format(as_char) if as_char else ""
    print("=" * 60)
    print("  {0} — 关系图谱{1}".format(entity, view_tag))
    print("=" * 60)
    
    # NPC info
    try:
        npc = conn.execute("SELECT * FROM npcs WHERE name=?", (entity,)).fetchone()
    except: npc = None
    if npc:
        print("\n  NPC: {0} [{1}] stance={2} faction={3}".format(
            npc['name'], npc['role'], npc['stance'] or '-', npc['faction'] or '-'))
        facts = json.loads(npc['key_facts'] or '[]')
        if facts: print("  facts: {0}".format(", ".join(facts)))
        rels = json.loads(npc['relationships'] or '[]')
        if rels:
            print("\n  ↔ 人物关联:")
            for rel in rels:
                print("    {0}".format(rel))
    
    # Clues
    clues = conn.execute(
        "SELECT id,content,source,confidence,priority,linked_ids FROM clues WHERE source=? OR content LIKE ? ORDER BY id",
        (entity, "%{0}%".format(entity))).fetchall()
    if clues:
        visible = [c for c in clues if _clue_visible_to(conn, c['id'], as_char)]
        hidden = len(clues) - len(visible)
        print("\n  📋 线索 ({0}条{1}):".format(len(visible), ", {0}条不可见".format(hidden) if hidden else ""))
        for c in visible:
            linked = json.loads(c['linked_ids'] or '[]')
            linked_str = " ← {0}".format(", ".join(linked)) if linked else ""
            print("    {0} [{1}/{2}] {3}{4}".format(
                c['id'], c['confidence'], c['priority'] if c['priority'] else '-', c['content'], linked_str))
    
    # Timeline
    events = conn.execute(
        "SELECT event_time,event,participants,related_clues FROM timeline_events WHERE participants LIKE ? ORDER BY event_time",
        ("%{0}%".format(entity),)).fetchall()
    if events:
        print("\n  ⏱ 时间线 ({0}条):".format(len(events)))
        for e in events:
            parts = json.loads(e['participants'] or '[]')
            clues_ref = json.loads(e['related_clues'] or '[]')
            c_str = " → {0}".format(", ".join(clues_ref)) if clues_ref else ""
            print("    {0} | {1} | {2}{3}".format(e['event_time'], e['event'], ", ".join(parts), c_str))
    
    # State changes (through clue_ref)
    clue_ids = [c['id'] for c in clues] if clues else []
    if clue_ids:
        states = []
        for cid in clue_ids:
            rows = conn.execute(
                "SELECT char_name,deltas,reason FROM char_state_log WHERE clue_ref=? ORDER BY seq", (cid,)).fetchall()
            states.extend(rows)
        if states:
            print("\n  💥 状态变更 ({0}条):".format(len(states)))
            for s in states:
                d = json.loads(s['deltas'])
                d_str = " ".join("{0}{1:+d}".format(pool_dict.get(k,k), v) for k,v in d.items())
                print("    {0}: {1} ({2})".format(s['char_name'], d_str, reason_dict.get(s['reason'], s['reason'])))
    
    if not npc and not clues and not events:
        print("\n  No connections found.")
    conn.close()

def cmd_links(db_path, entity):
    """Show all connections for an entity (NPCs, clues, state changes)."""
    conn = get_conn(db_path)
    print("=== Connections for {0} ===\n".format(entity))
    # NPC lookups
    try:
        npc = conn.execute("SELECT * FROM npcs WHERE name=?", (entity,)).fetchone()
    except:
        npc = None
    if npc:
        for rel in json.loads(npc['relationships'] or '[]'):
            print("  ↔ {0}".format(rel))
    # Clues where this entity is source or in content
    clues = conn.execute("SELECT id,content,confidence FROM clues WHERE source=? OR content LIKE ?",
        (entity, "%{0}%".format(entity))).fetchall()
    if clues:
        print("\n  Clues:")
        for c in clues:
            print("    {0} [{1}] {2}".format(c['id'], c['confidence'], c['content']))
    # Timeline events
    events = conn.execute("SELECT event_time,event,participants FROM timeline_events WHERE participants LIKE ?",
        ("%{0}%".format(entity),)).fetchall()
    if events:
        print("\n  Timeline:")
        for e in events:
            print("    {0} | {1}".format(e['event_time'], e['event']))
    if not npc and not clues and not events:
        print("  No connections found.")
    conn.close()

def _run_export(db_path):
    """Run export_dashboard.py + render_views.py to refresh all outputs"""
    import subprocess, os
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.dirname(os.path.abspath(db_path))
    for tool, args in [
        ("export_dashboard.py", [sys.executable, os.path.join(skill_dir, "tools", "export_dashboard.py"), db_path]),
        ("render_views.py",    [sys.executable, os.path.join(skill_dir, "tools", "render_views.py"), log_dir]),
    ]:
        if not os.path.exists(args[1]):
            print("  ({0} not found, skip)".format(tool))
            continue
        r = subprocess.run(args, capture_output=True, timeout=10)
        out = (r.stdout + r.stderr).decode('utf-8', errors='replace').strip()
        if out:
            for line in out.split('\n'):
                line = line.strip()
                if line and 'CLIXML' not in line: print("  [export] " + line)

def _validate_snake(s, field):
    """Reject non-snake_case input to prevent DB pollution."""
    if not s or not s.replace('_','').replace('-','').isalnum():
        print("ERROR: {0} '{1}' — 必须用 snake_case (只含 a-z 0-9 _)".format(field, s))
        return False
    if any('\u4e00' <= c <= '\u9fff' for c in s):
        print("ERROR: {0} '{1}' — 不允许中文，请用 snake_case".format(field, s))
        return False
    return True

def _validate_pool(p):
    """Pool key must be alphanumeric + underscore."""
    if not p or not p.replace('_','').isalnum():
        print("ERROR: pool key '{0}' — 只含 a-z 0-9 _".format(p))
        return False
    return True

def _validate_int(v, field):
    """Must be an integer."""
    if not isinstance(v, int):
        try: v = int(v)
        except: print("ERROR: {0} '{1}' — 必须是整数".format(field, v)); return None
    return v

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
        bases = conn.execute("SELECT char_name,char_type,base_stats FROM char_base ORDER BY CASE char_type WHEN 'pc' THEN 0 ELSE 1 END, char_name").fetchall()
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
    parser.add_argument("command", choices=["init", "search", "clue", "stats", "export", "state", "trace", "graph", "events", "npcs", "timeline", "links", "relations"])
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
            if sub == "link" and len(ns.args) >= 3:
                cmd_clue_link(ns.db_path, ns.args[1], ns.args[2])
            else:
                print("Usage: db_manager.py <db> clue link <id1> <id2>")
        else:
            print("Usage: db_manager.py <db> clue link <id1> <id2>")

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
            # state add <name> [--hp N] [--san N] [--any N ...] --reason S [--time HH:MM] [--loc S] [--status S] [--clue S] [--scene S] [--round N] [--note S] [--export]
            if len(rest) < 1: print("Usage: state add <name> --reason S [--hp N] [--time HH:MM] [--export] ..."); return
            name = rest[0]
            deltas = {}; reason = None; loc = None; status = None; clue = None; scene = None; round_n = None; note = None; game_time = None; game_date = None; do_export = True
            i = 1
            while i < len(rest):
                if rest[i] == '--reason' and i+1 < len(rest): reason = rest[i+1]; i += 2
                elif rest[i] == '--loc' and i+1 < len(rest): loc = rest[i+1]; i += 2
                elif rest[i] == '--status' and i+1 < len(rest): status = rest[i+1]; i += 2
                elif rest[i] == '--clue' and i+1 < len(rest): clue = rest[i+1]; i += 2
                elif rest[i] == '--scene' and i+1 < len(rest): scene = rest[i+1]; i += 2
                elif rest[i] == '--round' and i+1 < len(rest): round_n = int(rest[i+1]); i += 2
                elif rest[i] == '--note' and i+1 < len(rest): note = rest[i+1]; i += 2
                elif rest[i] == '--time' and i+1 < len(rest): game_time = rest[i+1]; i += 2
                elif rest[i] == '--date' and i+1 < len(rest): game_date = rest[i+1]; i += 2
                elif rest[i] == '--export': do_export = True; i += 1
                elif rest[i] == '--no-export': do_export = False; i += 1
                elif rest[i].startswith('--') and i+1 < len(rest):
                    try: deltas[rest[i][2:]] = int(rest[i+1])
                    except ValueError: deltas[rest[i][2:]] = rest[i+1]
                    i += 2
                else: i += 1
            if not reason: print("Usage: state add <name> --reason S [--hp N] [--export] ..."); return
            cmd_state_add(ns.db_path, name, deltas, loc, status, reason, clue, scene, round_n, game_time, game_date, note, do_export)
        elif sub == "query":
            if not rest: print("Usage: state query <name>"); return
            cmd_state_query(ns.db_path, rest[0])
        elif sub == "current":
            cmd_state_current(ns.db_path, rest[0] if rest else None)
        elif sub == "list":
            cmd_state_current(ns.db_path, None)
        else:
            print(f"Unknown state sub: {sub!r} rest={rest!r}; Usage: state init|add|query|current|list")

    elif ns.command == "events":
        char = None; since = None
        for i, a in enumerate(ns.args):
            if a == '--char' and i+1 < len(ns.args): char = ns.args[i+1]
            elif a == '--since' and i+1 < len(ns.args): since = ns.args[i+1]
        cmd_events(ns.db_path, char, since)

    elif ns.command == "graph":
        entity = ns.args[0] if ns.args else None
        as_char = None
        for i, a in enumerate(ns.args):
            if a == '--as' and i+1 < len(ns.args): as_char = ns.args[i+1]
        if not entity: print("Usage: graph <entity> [--as <角色>]"); return
        cmd_graph(ns.db_path, entity, as_char)

    elif ns.command == "trace":
        if len(ns.args) < 1: print("Usage: trace <clue_id>"); return
        cmd_trace(ns.db_path, ns.args[0])

    elif ns.command == "npcs":
        cmd_npcs(ns.db_path, ns.args[0] if ns.args else None)

    elif ns.command == "timeline":
        since = None; char = None
        for i in range(len(ns.args)):
            if ns.args[i] == '--since' and i+1 < len(ns.args): since = ns.args[i+1]
            elif ns.args[i] == '--char' and i+1 < len(ns.args): char = ns.args[i+1]
        cmd_timeline(ns.db_path, since, char)

    elif ns.command == "links":
        if len(ns.args) < 1: print("Usage: links <entity_name>"); return
        cmd_links(ns.db_path, ns.args[0])

    elif ns.command == "relations":
        npc = ns.args[0] if ns.args else None
        cmd_relations(ns.db_path, npc)

    elif ns.command == "export":
        limit = 50
        if ns.args and ns.args[0].startswith("--limit="):
            limit = int(ns.args[0].split("=")[1])
        cmd_export(ns.db_path, limit)


if __name__ == "__main__":
    main()
