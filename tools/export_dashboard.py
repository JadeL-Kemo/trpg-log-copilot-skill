# -*- coding: utf-8 -*-
"""导出角色面板.md (全量属性)——仅此一份，00_当前局势.md由人工维护。

Usage:
    python tools/export_dashboard.py                      (自动检测trpg_data.db)
    python tools/export_dashboard.py path/to/trpg_data.db (指定DB路径)"""
import os, sys, json, sqlite3
os.environ['PYTHONIOENCODING'] = 'utf-8'

if len(sys.argv) > 1:
    DB = sys.argv[1]
else:
    # Auto-detect: look for trpg_data.db in current dir
    DB = os.path.join(os.getcwd(), "trpg_data.db")
LOG = os.path.dirname(os.path.abspath(DB))
OUT = os.path.join(LOG, "角色面板.md")

conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
POOL = {r['key']: r['cn_name'] for r in conn.execute("SELECT key,cn_name FROM dict_labels WHERE category='pool'")}
REASON = {r['key']: r['cn_name'] for r in conn.execute("SELECT key,cn_name FROM dict_labels WHERE category='reason'")}
STATUS = {r['key']: r['cn_name'] for r in conn.execute("SELECT key,cn_name FROM dict_labels WHERE category='status'")}
def pc(k): return POOL.get(k, k)
def rc(r): return REASON.get(r, r)
def sc(s): return STATUS.get(s, s) if s else '-'

chars = conn.execute("SELECT char_name,char_type,base_stats FROM char_base ORDER BY CASE char_type WHEN 'pc' THEN 0 ELSE 1 END, char_name").fetchall()

blocks = []; timeline = []
for ch in chars:
    base = json.loads(ch['base_stats'])
    deltas = conn.execute("SELECT deltas,reason,clue_ref,scene_ref FROM char_state_log WHERE char_name=? ORDER BY seq", (ch['char_name'],)).fetchall()
    totals = dict(base); changes = []
    for d in deltas:
        dd = json.loads(d['deltas'])
        for k, v in dd.items():
            totals[k] = totals.get(k, 0) + v; changes.append((k, v, d['reason']))
            timeline.append({'name':ch['char_name'],'pool':k,'pool_cn':pc(k),'delta':v,'reason':d['reason'],'reason_cn':rc(d['reason']),'clue':d['clue_ref'] or '-'})
    last = conn.execute("SELECT loc_new,status_new FROM char_state_log WHERE char_name=? AND (loc_new IS NOT NULL OR status_new IS NOT NULL) ORDER BY seq DESC LIMIT 1", (ch['char_name'],)).fetchone()
    floating = [(k, totals[k] - base[k]) for k in sorted(base.keys())
                if isinstance(base[k],int) and totals.get(k,base[k]) != base[k]]
    blocks.append({
        'name': ch['char_name'], 'type': ch['char_type'],
        'base': base, 'totals': totals, 'floating': floating,
        'loc': last['loc_new'] if last and last['loc_new'] else '-',
        'status': sc(last['status_new']) if last else '-',
        'trace': "; ".join("{0} {1:+d} {2}".format(k, v, r) for k, v, r in changes),
    })

LF = []
LF.append("# 角色面板 — 全量属性")
LF.append("")
LF.append("> 自动生成 | {0}角色/{1}条变更".format(len(chars), len(timeline)))
LF.append("")

for b in blocks:
    LF.append("## {0} ({1})".format(b['name'], b['type']))
    LF.append("")
    # 固定值
    fixed_str = ", ".join("`最大{0}: {1}`".format(pc(k), b['base'][k]) for k in sorted(b['base'].keys()))
    LF.append("**固定值**: {0}".format(fixed_str))
    LF.append("")
    # 浮动值
    if b['floating']:
        float_str = ", ".join("`{0}: {1}{2}`".format(pc(k), '+' if net>0 else '', net) for k, net in b['floating'])
        LF.append("**浮动值**: {0}".format(float_str))
        LF.append("")
    LF.append("**位置**: {0}".format(b['loc']))
    LF.append("**状态**: {0}".format(b['status']))
    if b['trace']:
        LF.append("<!-- trace: {0} -->".format(b['trace']))
    LF.append("")
    LF.append("---")
    LF.append("")

LF.append("## 最近变更（最近10条）")
LF.append("")
LF.append("| 序号 | 角色 | 池 | 变化 | 原因 |")
LF.append("|:--:|------|------|:--:|------|")
for i, t in enumerate(timeline[-10:], 1):
    sign = '+' if t['delta'] > 0 else ''
    LF.append("| {0} | {1} | {2} | {3}{4} | {5} |".format(i, t['name'], t['pool_cn'], sign, t['delta'], t['reason_cn']))

LF.append("")
LF.append("> 完整变更链 → `state query <角色>` 查SQL，全量索引 `state current`")

LF.append("")
LF.append("> 生成时间: {0}".format(conn.execute("SELECT datetime('now','localtime')").fetchone()[0]))
conn.close()

with open(OUT, 'w', encoding='utf-8') as f: f.write("\n".join(LF))
print("Written: {0}".format(OUT))
