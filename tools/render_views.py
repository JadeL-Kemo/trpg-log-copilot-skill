# -*- coding: utf-8 -*-
"""SQL → HTML + CSS/JS。AI 不碰 HTML/JS/CSS。

Usage:
    python tools/render_views.py <日志目录>
"""
import os, sys, json, sqlite3
from datetime import datetime

LOG = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
DB = os.path.join(LOG, "trpg_data.db")
if not os.path.exists(DB):
    print("No trpg_data.db — run import_md.py first"); sys.exit(0)

conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row

# Labels
labels = {}
for cat in ['pool', 'reason', 'status', 'verified', 'confidence']:
    labels[cat] = {r['key']: r['cn_name'] for r in conn.execute(
        "SELECT key,cn_name FROM dict_labels WHERE category=?", (cat,)).fetchall()}

# Data from SQL
clues = [dict(r) for r in conn.execute("SELECT id,content,source,confidence,tags,linked_ids FROM clues ORDER BY id")]
npcs_ = [dict(r) for r in conn.execute("SELECT id,name,role,stance,faction,key_facts,relationships FROM npcs ORDER BY id")]
events = [dict(r) for r in conn.execute("SELECT event_time,event,participants,related_clues,notes,scene_id FROM timeline_events WHERE category IS NULL OR category != 'chronicle' ORDER BY event_time")]
chronicles = [dict(r) for r in conn.execute("SELECT event_date,event,participants,related_clues,notes FROM timeline_events WHERE category='chronicle' ORDER BY event_date")]
relations = [dict(r) for r in conn.execute("SELECT id,npc_a,npc_b,rel_type,direction,source_ref FROM npc_relations ORDER BY npc_a,npc_b")]

# Character state
char_rows = []
for ch in conn.execute("SELECT char_name,char_type,base_stats FROM char_base ORDER BY CASE char_type WHEN 'pc' THEN 0 END, char_name"):
    base = json.loads(ch['base_stats']); totals = dict(base)
    for d in conn.execute("SELECT deltas FROM char_state_log WHERE char_name=? ORDER BY seq", (ch['char_name'],)):
        for k, v in json.loads(d['deltas']).items(): totals[k] = totals.get(k, 0) + v
    last = conn.execute("SELECT loc_new,status_new FROM char_state_log WHERE char_name=? AND (loc_new IS NOT NULL OR status_new IS NOT NULL) ORDER BY seq DESC LIMIT 1", (ch['char_name'],)).fetchone()
    pools = {}
    for k in sorted(base.keys()):
        pools[labels['pool'].get(k, k)] = {"cur": totals.get(k, '?'), "max": base[k]}
    char_rows.append({
        "name": ch['char_name'], "type": ch['char_type'], "pools": pools,
        "loc": last['loc_new'] if last and last['loc_new'] else '-',
        "status": labels['status'].get(last['status_new'], last['status_new']) if last and last['status_new'] else '-'})

# Todos
todos = []
todo_path = os.path.join(LOG, "06_待办.md")
if os.path.exists(todo_path):
    for line in open(todo_path, encoding='utf-8').readlines():
        line = line.strip()
        if line.startswith('- [') or line.startswith('- '):
            done = '[x]' in line[:6]
            task = line[line.find(']')+1:].strip() if ']' in line[:6] else line[2:].strip()
            priority = line[line.find('[')+1:line.find(']')] if '[' in line[:6] else '🟡'
            todos.append({"task": task, "priority": priority, "done": done})
import re as _re
# Only confirmed clues exist in DATA — filter todo refs
valid_ids = {c['id'] for c in clues}
for t in todos:
    task = t['task']; reason = ''
    rm = _re.search(r'\((.+?)\)', task)
    if rm: reason = rm.group(1); task = _re.sub(r'\s*\(.+?\)', '', task)
    m = _re.search(r'→?\s*(CL-\d[\d,\s]*)', task)
    ref_ids = []
    if m:
        ref_ids = [x.strip() for x in _re.split(r'[,，\s]+', m.group(1)) if x.strip() and x.strip() in valid_ids]
        task = _re.sub(r'→?\s*CL-\d[\d,\s]*', '', task).strip()
    t['task'] = task; t['reason'] = reason; t['ref_ids'] = ref_ids

conn.close()

# Dashboard summary
ts = datetime.now().strftime('%H:%M')
dash_parts = []
for ch in char_rows:
    if ch['type'] != 'pc': continue  # PC characters only in dashboard
    parts = [ch['name']]
    for pn, pd in ch['pools'].items():
        parts.append('{0} {1}/{2}'.format(pn[:4].upper().ljust(4), pd['cur'], pd['max']))
    if ch['loc'] != '-': parts.append(ch['loc'])
    if ch['status'] != '-': parts.append('[{}]'.format(ch['status']))
    dash_parts.append(' · '.join(parts))
dash = '  |  '.join(dash_parts) if dash_parts else 'No PC data'

# Build DATA blob
DATA = json.dumps({
    "clues": clues, "npcs": npcs_, "events": events, "chronicles": chronicles, "relations": relations,
    "chars": char_rows, "todos": todos,
    "labels": {"verified": labels['verified'], "confidence": labels['confidence']}
}, ensure_ascii=False)

# Use static template from assets/
import os as _os
tmpl_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', 'assets', 'panel.html')
if _os.path.exists(tmpl_path):
    tmpl = open(tmpl_path, 'r', encoding='utf-8').read()
else:
    # Fallback: minimal shell
    tmpl = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel</title><link rel="stylesheet" href="panel.css"></head><body><div id="dash"></div><nav></nav><div id="clues" class="panel active"><h2>线索板</h2><div id="ct"></div></div><div id="npcs" class="panel"><h2>人物关系</h2><div id="nt"></div></div><div id="tl" class="panel"><h2 style="cursor:pointer" onclick="document.getElementById(\'chr\').classList.toggle(\'fold\')">▶ 大纪事</h2><div id="chr" class="chr-wrap fold"></div><h2 style="margin-top:16px">事件线</h2><div id="tt"></div></div><div id="chars" class="panel"><h2>角色状态</h2><div id="cc"></div></div><div id="todos" class="panel"><h2>待办事项</h2><div id="tlst"></div></div><div id="ts"></div><div id="drill" onclick="var e=event;if(e.target===this)closeDrill()"><div id="drillPane"><div id="drillHead"><span id="drillTitle"></span><button id="drillClose" onclick="closeDrill()">✕</button></div><div id="drillBody"></div></div></div><script src="panel.js"></script></body></html>'

# Embed DATA for offline mode, then load panel.js
embed = '<script>window.DATA=' + DATA + ';</script>'
html = tmpl.replace('<script src="panel.js"></script>', embed + '<script src="panel.js"></script>')

out = os.path.join(LOG, "panel.html")
with open(out, 'w', encoding='utf-8') as f: f.write(html)
print("{} ({}c/{}n/{}e/{}ch/{}td)".format(out, len(clues), len(npcs_), len(events), len(char_rows), len(todos)))
