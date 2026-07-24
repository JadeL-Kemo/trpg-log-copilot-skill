# -*- coding: utf-8 -*-
"""MD表格 + 行内标注 → SQL 批量导入。AI writes MD tables — this tool syncs to SQL.

Usage:
    python tools/import_md.py <日志目录> <trpg_data.db>

Reads:
    01_线索.md  → table rows → INSERT clues (verified=confirmed only)
    02_人物.md  → table rows → INSERT npcs
    03_时间线.md → table rows → INSERT timeline_events
    04_行动日志.md → <!-- state: ... --> → state_add
    After import: rebuild FTS + render HTML + export character panel
"""
import os, sys, json, sqlite3, re, subprocess

if len(sys.argv) < 3:
    print(__doc__); sys.exit(1)

LOG = sys.argv[1]; DB = sys.argv[2]

# ============== MD table parser ==============
def validate_table(text, fname=''):
    """Scan for | inside cell content (e.g. '医学|急救' → parsed as separate columns).
    Returns list of warnings, empty if OK."""
    warnings = []
    lines = text.split('\n')
    header_cols = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('|') or not line.endswith('|'): continue
        if re.match(r'^\|[\s\-:]+\|', line): continue
        cells = [c.strip() for c in line[1:-1].split('|')]
        if header_cols == 0:
            header_cols = len(cells)
            continue
        if len(cells) != header_cols:
            warnings.append('  ⚠ {0} line {1}: expected {2} columns, got {3}'.format(
                fname, i+1, header_cols, len(cells)))
    return warnings

def parse_md_table(text):
    """Parse markdown table into list of dicts. Header row determines column names.
    
    Input:
        | id | content | source | verified | priority | tags | linked |
        |------|------|------|------|------|------|------|
        | CL-001 | 内容 | KP旁白 | confirmed | high | a,b | CL-002 |
    
    Returns: [{'id':'CL-001','content':'内容',...}, ...]
    """
    lines = text.split('\n')
    result = []; header = None; positions = None
    
    for line in lines:
        line = line.strip()
        if not line.startswith('|') or not line.endswith('|'):
            continue
        if re.match(r'^\|[\s\-:]+\|', line):
            continue
        
        cells = [c.strip() for c in line[1:-1].split('|')]
        
        if header is None:
            header = cells
            positions = {h: i for i, h in enumerate(cells) if h}
            continue
        
        row = {}
        for col, idx in positions.items():
            if idx < len(cells) and cells[idx]:
                row[col] = cells[idx]
        if row:
            result.append(row)
    
    return result

def parse_clue_tags(tag_str):
    """'blindness,shiming,失明' → ['blindness','shiming','失明']"""
    if not tag_str: return []
    return [t.strip() for t in tag_str.split(',') if t.strip()]

def parse_clue_linked(linked_str):
    """'CL-001,CL-002' → ['CL-001','CL-002']"""
    if not linked_str: return []
    return [l.strip() for l in linked_str.split(',') if l.strip()]

def parse_state_annotations(text):
    """Extract <!-- state: char_name pool delta reason [clue_ref] -->"""
    pattern = r'<!--\s*state:\s*(.+?)\s*-->'
    results = []
    for m in re.finditer(pattern, text):
        parts = m.group(1).strip().split()
        if len(parts) < 4: continue
        results.append({
            'name': parts[0], 'pool': parts[1], 'delta': int(parts[2]),
            'reason': parts[3], 'clue': parts[4] if len(parts)>4 else None,
            'scene': parts[5] if len(parts)>5 else None,
        })
    return results


# ============== Load sync.ini ==============
import configparser
_sync_paths = {
    '01_clues': '01_线索.md', '02_npcs': '02_人物.md',
    '03_timeline': '03_时间线.md', '03a_chronicle': '03a_大纪事.md',
    '04_action': '04_行动日志.md', '06_todos': '06_待办.md',
}
ini_path = os.path.join(LOG, "sync.ini")
if os.path.exists(ini_path):
    cfg = configparser.ConfigParser()
    cfg.read(ini_path, encoding='utf-8')
    if cfg.has_section('sync'):
        for key, val in cfg.items('sync'):
            _sync_paths[key] = val
def _path(key):
    return os.path.join(LOG, _sync_paths.get(key, ''))

# --- Import loop ---
conn = sqlite3.connect(DB); imported = 0

# 01_线索.md
clue_path = _path('01_clues')
if os.path.exists(clue_path):
    raw = open(clue_path, encoding='utf-8').read()
    for w in validate_table(raw, '01_线索.md'): print(w)
    rows = parse_md_table(raw)
    n = 0; skipped = 0
    for r in rows:
        if 'id' not in r or 'content' not in r: skipped += 1; continue
        verified = r.get('verified', 'pending')
        if verified != 'confirmed': skipped += 1; continue
        tags = parse_clue_tags(r.get('tags', ''))
        if not tags and r.get('tags','').strip() == '':
            print('  ⚠ empty tags: ' + r['id'] + ' — FTS5 search degraded')
        linked = parse_clue_linked(r.get('linked', ''))
        confidence = r.get('confidence', 'medium')
        conn.execute(
            "INSERT OR REPLACE INTO clues (id,content,source,confidence,tags,category,linked_ids,status) VALUES (?,?,?,?,?,?,?,?)",
            (r['id'], r['content'], r.get('source',''),
             confidence,
             json.dumps(tags, ensure_ascii=False), 'core',
             json.dumps(linked, ensure_ascii=False), 'active'))
        n += 1
    print("Clues: {0} of {1} ({2} unconfirmed/skipped)".format(n, len(rows), skipped))
else:
    print("No 01_线索.md")

# 02_人物.md
npc_path = _path('02_npcs')
if os.path.exists(npc_path):
    text = open(npc_path, encoding='utf-8').read()
    # Only parse the first table (before narrative text)
    table_start = text.find('| id |')
    if table_start >= 0:
        table_text = text[table_start:]
        for w in validate_table(table_text, '02_人物.md'): print(w)
        rows = parse_md_table(table_text)
    else:
        rows = []
    n = 0
    for r in rows:
        if 'id' not in r or 'name' not in r: continue
        # Clean NPC name: strip emoji + 🔴 prefixes
        _name_clean = re.sub(r'[\U0001F300-\U0001F9FF\u2600-\u27BF\u2B50\u2764\u2728\u25CF]', '', r['name']).strip()
        # Strip leading emoji-sequence markers like 🔴🔴🔴
        _name_clean = re.sub(r'^[\ue000-\uf8ff\u2764\u2728\u25CF\U0001F000-\U0001FFFF]+', '', _name_clean).strip()
        if not _name_clean: _name_clean = r['name']  # Fallback if all chars stripped
        if _name_clean != r['name']:
            print('  clean NPC name: "' + r['name'] + '" -> "' + _name_clean + '"')
        conn.execute(
            "INSERT OR REPLACE INTO npcs (id,name,role,stance,faction,key_facts,relationships) VALUES (?,?,?,?,?,?,?)",
            (r['id'], _name_clean, r.get('role',''), r.get('stance',''),
             r.get('faction',''),
             json.dumps(parse_clue_tags(r.get('key_facts','')), ensure_ascii=False),
             json.dumps(parse_clue_tags(r.get('relationships','')), ensure_ascii=False)))
        n += 1
    print("NPCs: {0}".format(n))

    # === Build npc_relations from relationships column ===
    conn.execute("DELETE FROM npc_relations")
    _rel_re = re.compile(r'^(.+?)\((.+?)\)$')
    for npc_name, rels_json in conn.execute("SELECT name,relationships FROM npcs").fetchall():
        rels = json.loads(rels_json) if rels_json else []
        for rel in rels:
            m = _rel_re.match(rel)
            if not m:
                # No type annotation: "李锐光" → just tag with empty type
                target = rel
                rtype, direction, src = '', 'mutual', None
            else:
                target = m.group(1).strip()
                parts = [p.strip() for p in m.group(2).split(',')]
                rtype = parts[0] if parts else ''
                direction = 'mutual'
                src = None
                for p in parts[1:]:
                    if p in ('mutual', 'oneway', 'a_to_b', 'b_to_a'):
                        direction = p
                    elif p.startswith('S') and '_' in p:
                        src = p
            if not target: continue
            conn.execute(
                "INSERT INTO npc_relations (npc_a,npc_b,rel_type,direction,source_ref) VALUES (?,?,?,?,?)",
                (npc_name, target, rtype, direction, src))
    rel_cnt = conn.execute("SELECT COUNT(*) FROM npc_relations").fetchone()[0]
    print("Relations: {0} edges".format(rel_cnt))

# 03_时间线.md
tl_path = _path('03_timeline')
if os.path.exists(tl_path):
    raw = open(tl_path, encoding='utf-8').read()
    for w in validate_table(raw, '03_时间线.md'): print(w)
    rows = parse_md_table(raw)
    # Validate event_date format
    import re as _re2
    _date_ok = _re2.compile(r'^\d{4}(-\d{2}){0,2}(-[a-z]+)?$')
    _date_bad = ['当日', '现在', '近日', '三天前', '案发后', '约', '左右']
    for r in rows:
        ed = (r.get('event_date') or '').strip()
        if not ed:
            print('  ⚠ timeline missing event_date: "' + (r.get('event') or r.get('time','?'))[:30] + '"')
        elif not _date_ok.match(ed):
            print('  ⚠ timeline event_date invalid: "' + ed + '" ← "' + (r.get('event',''))[:20] + '"')
        elif any(b in ed for b in _date_bad):
            print('  ⚠ timeline event_date has bad keyword: "' + ed + '"')
    if rows: conn.execute("DELETE FROM timeline_events")
    n = 0
    for r in rows:
        if 'event' not in r and 'content' not in r: continue
        event_text = r.get('event') or r.get('content', '')
        event_time = r.get('time') or r.get('event_date') or r.get('event_time') or ''
        participants = parse_clue_tags(r.get('participants', ''))
        related = parse_clue_linked(r.get('related_clues', ''))
        category = r.get('category', 'story') or 'story'
        event_date = r.get('event_date') or None
        timeline_status = r.get('timeline_status', 'canon') or 'canon'
        notes = r.get('notes', None)
        scene_id = r.get('scene_id', None)
        # Auto-suffix: AI writes bare YYYY-MM-DD, import assigns -010/-020/-030...
        if event_date and _re2.match(r'^\d{4}-\d{2}-\d{2}$', event_date):
            cnt = conn.execute("SELECT COUNT(*) FROM timeline_events WHERE event_date LIKE ?",
                (event_date + '-%',)).fetchone()[0]
            event_date = event_date + '-{0:03d}'.format(cnt * 10 + 10)
        conn.execute(
            "INSERT OR REPLACE INTO timeline_events (event_time,event,participants,related_clues,category,event_date,timeline_status,notes,scene_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (event_time, event_text,
             json.dumps(participants, ensure_ascii=False),
             json.dumps(related, ensure_ascii=False),
             category, event_date, timeline_status, notes, scene_id))
        n += 1
    print("Timeline: {0}".format(n))

# 03a_大纪事.md
chr_path = _path('03a_chronicle')
if os.path.exists(chr_path):
    raw = open(chr_path, encoding='utf-8').read()
    for w in validate_table(raw, '03a_大纪事.md'): print(w)
    rows = parse_md_table(raw)
    n = 0
    for r in rows:
        if 'event' not in r and 'event_date' not in r: continue
        event_text = r.get('event', '')
        event_date = r.get('event_date', '')
        participants = parse_clue_tags(r.get('participants', ''))
        related = parse_clue_linked(r.get('related_clues', ''))
        notes = r.get('notes', None)
        conn.execute(
            "INSERT INTO timeline_events (event_time,event,participants,related_clues,category,event_date,timeline_status,notes) VALUES (?,?,?,?,?,?,?,?)",
            (event_date, event_text,
             json.dumps(participants, ensure_ascii=False),
             json.dumps(related, ensure_ascii=False),
             'chronicle', event_date, 'canon', notes))
        n += 1
    print("Chronicle: {0}".format(n))

# 04_行动日志.md
action_path = _path('04_action')
if os.path.exists(action_path):
    states = parse_state_annotations(open(action_path, encoding='utf-8').read())
    n = 0
    for s in states:
        try:
            exists = conn.execute("SELECT 1 FROM char_base WHERE char_name=?", (s['name'],)).fetchone()
        except:
            print("  Skip state '{0}' — DB not initialized".format(s['name'])); continue
        if not exists:
            print("  Skip state '{0}' — not in char_base. Use 'state init'.".format(s['name'])); continue
        seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM char_state_log WHERE char_name=?", (s['name'],)).fetchone()[0]
        conn.execute(
            "INSERT INTO char_state_log (char_name,seq,deltas,reason,clue_ref,scene_ref) VALUES (?,?,?,?,?,?)",
            (s['name'], seq, json.dumps({s['pool']: s['delta']}), s['reason'], s['clue'], s['scene']))
        n += 1
    print("States: {0}".format(n))

# === Narrative import: sync.ini → narrative_chunks ===
ini_path = os.path.join(LOG, "sync.ini")
if os.path.exists(ini_path):
    cfg = configparser.ConfigParser()
    cfg.read(ini_path, encoding='utf-8')
    n = 0
    for key, fname in cfg.items('narrative'):
        fpath = os.path.join(LOG, fname)
        if not os.path.exists(fpath): continue
        text = open(fpath, encoding='utf-8').read()
        # Split by ### headers
        chunks = re.split(r'(?=###\s)', text)
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk: continue
            # Extract scene_id from header
            m = re.search(r'###\s*(\S+)', chunk)
            sid = m.group(1) if m else key
            conn.execute(
                "INSERT OR REPLACE INTO narrative_chunks (scene_id, file_name, chunk_text) VALUES (?,?,?)",
                (sid, fname, chunk))
            n += 1
    print("Narrative: {0} chunks".format(n))

# Rebuild FTS
try: conn.execute("INSERT INTO clues_fts(clues_fts) VALUES('rebuild')")
except: pass
conn.commit(); conn.close()
print("\nSync complete.")

# Render + export
skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for tool in ['export_dashboard.py', 'render_views.py']:
    p = os.path.join(skill_dir, 'tools', tool)
    if os.path.exists(p):
        args = [sys.executable, p, DB] if tool == 'export_dashboard.py' else [sys.executable, p, LOG]
        r = subprocess.run(args, capture_output=True, timeout=10)
        out = (r.stdout + r.stderr).decode('utf-8', errors='replace')
        for line in out.split('\n'):
            line = line.strip()
            if line and 'CLIXML' not in line: print("  " + line)
