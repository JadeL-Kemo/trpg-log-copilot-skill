# -*- coding: utf-8 -*-
"""JSON + MD 批量导入 SQL。AI writes JSON — this tool imports.

Usage:
    python tools/import_from_md.py <日志目录> <trpg_data.db>

Reads:
    01_线索.json → INSERT clues (only ✅已验证)
    02_人物.json → INSERT npcs
    03_时间线.json → INSERT timeline_events
    04_行动日志.md → parse <!-- state: ... --> → state_add
    After import: rebuild FTS + render 跑团面板.html
"""
import os, sys, json, sqlite3, re, subprocess

if len(sys.argv) < 3:
    print(__doc__); sys.exit(1)

LOG_DIR = sys.argv[1]; DB_PATH = sys.argv[2]
SQL_CONFIDENCE = {'✅已确认'}

def load_json(filename):
    path = os.path.join(LOG_DIR, filename)
    if not os.path.exists(path): return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def parse_state_annotations(text):
    pattern = r'<!--\s*state:\s*(.+?)\s*-->'
    results = []
    for m in re.finditer(pattern, text):
        parts = m.group(1).strip().split()
        if len(parts) < 4: continue
        results.append({
            'name': parts[0], 'pool': parts[1], 'delta': int(parts[2]),
            'reason': parts[3], 'clue': parts[4] if len(parts)>4 else None,
            'scene': parts[5] if len(parts)>5 else None,
            'round': int(parts[6]) if len(parts)>6 else None,
        })
    return results

conn = sqlite3.connect(DB_PATH); imported = 0

# 01_线索.json
for c in load_json("01_线索.json"):
    if not isinstance(c, dict) or 'id' not in c: continue
    if c.get('confidence','') not in SQL_CONFIDENCE: continue
    old = conn.execute("SELECT confidence FROM clues WHERE id=?", (c['id'],)).fetchone()
    if old and old[0] != c['confidence']:
        print("  UPGRADE: {0} {1} -> {2}".format(c['id'], old[0], c['confidence']))
    conn.execute("INSERT OR REPLACE INTO clues (id,content,source,confidence,category,linked_ids,status) VALUES (?,?,?,?,?,?,?)",
        (c['id'], c.get('content',''), c.get('source',''), c.get('confidence',''), 'core',
         json.dumps(c.get('linked',[]), ensure_ascii=False), 'active'))
    imported += 1
total_clues = len(load_json("01_线索.json"))
print("Clues: {0}/{1} (unconfirmed stay in JSON)".format(imported, total_clues))
clue_import = imported

# 02_人物.json
n = 0
for npc in load_json("02_人物.json"):
    if not isinstance(npc, dict) or 'id' not in npc: continue
    conn.execute("INSERT OR REPLACE INTO npcs (id,name,role,stance,faction,key_facts,relationships) VALUES (?,?,?,?,?,?,?)",
        (npc['id'], npc.get('name',''), npc.get('role',''), npc.get('stance',''), npc.get('faction',''),
         json.dumps(npc.get('key_facts',[]), ensure_ascii=False),
         json.dumps(npc.get('relationships',[]), ensure_ascii=False)))
    n += 1; imported += 1
print("NPCs: {0}".format(n))

# 03_时间线.json
n = 0
for evt in load_json("03_时间线.json"):
    if not isinstance(evt, dict): continue
    conn.execute("INSERT OR REPLACE INTO timeline_events (event_time,event,participants,related_clues) VALUES (?,?,?,?)",
        (evt.get('time',''), evt.get('event',''),
         json.dumps(evt.get('participants',[]), ensure_ascii=False),
         json.dumps(evt.get('related_clues',[]), ensure_ascii=False)))
    n += 1; imported += 1
print("Timeline: {0}".format(n))

# 04_行动日志.md — state annotations
action_file = os.path.join(LOG_DIR, "04_行动日志.md")
if os.path.exists(action_file):
    text = open(action_file, encoding='utf-8').read()
    states = parse_state_annotations(text)
    for s in states:
        try: conn.execute("SELECT 1 FROM char_base WHERE char_name=?", (s['name'],)).fetchone()
        except: print("  Skip state '{0}' — not in char_base".format(s['name'])); continue
        seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM char_state_log WHERE char_name=?", (s['name'],)).fetchone()[0]
        conn.execute("INSERT INTO char_state_log (char_name,seq,deltas,reason,clue_ref,scene_ref,round) VALUES (?,?,?,?,?,?,?)",
            (s['name'], seq, json.dumps({s['pool']: s['delta']}), s['reason'], s['clue'], s['scene'], s['round']))
        imported += 1
    print("States: {0}".format(len(states)))

# Rebuild FTS
try: conn.execute("INSERT INTO clues_fts(clues_fts) VALUES('rebuild')")
except: pass
conn.commit(); conn.close()
print("\nTotal: {0}".format(imported))

# Render HTML panel
export_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_dashboard.py")
render_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_views.py")
for tool in [export_py, render_py]:
    if os.path.exists(tool):
        args = [sys.executable, tool, DB_PATH] if tool == export_py else [sys.executable, tool, LOG_DIR]
        r = subprocess.run(args, capture_output=True, timeout=10)
        out = (r.stdout + r.stderr).decode('utf-8', errors='replace')
        for line in out.split('\n'):
            line = line.strip()
            if line and 'CLIXML' not in line: print("  "+line)
