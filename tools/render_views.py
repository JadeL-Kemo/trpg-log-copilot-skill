# -*- coding: utf-8 -*-
"""Generate single-page HTML panel from JSON + SQL data. AI never reads HTML.

Usage:
    python tools/render_views.py <日志目录>
"""
import os, sys, json, sqlite3

LOG = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
DB = os.path.join(LOG, "trpg_data.db")

clues=[]; npcs=[]; events=[]; index_data=[]; todos=[]
for fname, target in [("01_线索.json",clues),("02_人物.json",npcs),("03_时间线.json",events),("_index.json",index_data),("06_待办.json",todos)]:
    path = os.path.join(LOG, fname)
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f: target.extend(json.load(f))

char_rows = []
if os.path.exists(DB):
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    pool_cn = {r['key']: r['cn_name'] for r in conn.execute("SELECT key,cn_name FROM dict_labels WHERE category='pool'")}
    status_cn = {r['key']: r['cn_name'] for r in conn.execute("SELECT key,cn_name FROM dict_labels WHERE category='status'")}
    for ch in conn.execute("SELECT char_name,char_type,base_stats FROM char_base ORDER BY CASE char_type WHEN 'pc' THEN 0 ELSE 1 END, char_name"):
        base = json.loads(ch['base_stats'])
        totals = dict(base)
        for d in conn.execute("SELECT deltas FROM char_state_log WHERE char_name=? ORDER BY seq",(ch['char_name'],)):
            for k,v in json.loads(d['deltas']).items(): totals[k]=totals.get(k,0)+v
        last = conn.execute("SELECT loc_new,status_new FROM char_state_log WHERE char_name=? AND (loc_new IS NOT NULL OR status_new IS NOT NULL) ORDER BY seq DESC LIMIT 1",(ch['char_name'],)).fetchone()
        pools = {}
        for k in sorted(base.keys()):
            pools[pool_cn.get(k,k)] = {"cur":totals.get(k,'?'),"max":base[k]}
        char_rows.append({"name":ch['char_name'],"type":ch['char_type'],"pools":pools,
            "loc":last['loc_new'] if last and last['loc_new'] else '-',
            "status":status_cn.get(last['status_new'],last['status_new']) if last and last['status_new'] else '-'})
    conn.close()

C=json.dumps(clues,ensure_ascii=False); N=json.dumps(npcs,ensure_ascii=False)
E=json.dumps(events,ensure_ascii=False); H=json.dumps(char_rows,ensure_ascii=False)
I=json.dumps(index_data,ensure_ascii=False); T=json.dumps(todos,ensure_ascii=False)

html = '''<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><title>跑团面板</title>
<style>*{box-sizing:border-box}body{font-family:-apple-system,system-ui,sans-serif;margin:0;background:#0f0f1a;color:#d0d0d0}nav{background:#1a1a30;display:flex;position:sticky;top:0;z-index:10;border-bottom:1px solid #333}nav button{flex:1;background:0;border:0;color:#888;padding:12px;font-size:13px;cursor:pointer;transition:all .2s}nav button:hover{color:#fff;background:#222}nav button.active{color:#e94560;border-bottom:2px solid #e94560}.panel{display:none;padding:20px;max-width:1000px;margin:0 auto}.panel.active{display:block}h2{color:#e94560;margin-top:0}table{width:100%;border-collapse:collapse;margin:10px 0}th{background:#16213e;padding:8px 10px;text-align:left;font-weight:600;color:#aaa;font-size:13px}td{padding:6px 10px;border-bottom:1px solid #1a1a30;font-size:13px}tr:hover{background:#16213e}.ok{color:#4caf50}.warn{color:#ff9800}.urgent{color:#e94560}.low{color:#888}.tag{padding:1px 6px;border-radius:3px;font-size:11px}.tag-pc{background:#1a3a5c;color:#2196f3}.tag-npc{background:#3a1a1a;color:#e94560}.pool{display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;background:#1a1a30;border-radius:4px;font-size:12px}.pool .val{color:#e94560;font-weight:bold}.pool .net{font-size:11px;margin-left:4px}.pos{color:#4caf50}.neg{color:#e94560}.footer{color:#666;font-size:11px;margin-top:20px;text-align:center}</style></head><body>
<nav><button class="active" onclick="showTab(this,'clues')">线索板</button><button onclick="showTab(this,'npcs')">人物</button><button onclick="showTab(this,'timeline')">时间线</button><button onclick="showTab(this,'chars')">角色</button><button onclick="showTab(this,'todos')">待办</button><button onclick="showTab(this,'idx')">索引</button></nav>
<div id="clues" class="panel active"><h2>线索板</h2><table id="ct"></table></div>
<div id="npcs" class="panel"><h2>人物关系</h2><table id="nt"></table></div>
<div id="timeline" class="panel"><h2>时间线</h2><table id="tt"></table></div>
<div id="chars" class="panel"><h2>角色状态</h2><div id="cc"></div></div>
<div id="todos" class="panel"><h2>待办事项</h2><div id="tl"></div></div>
<div id="idx" class="panel"><h2>关键词索引</h2><table id="it"></table></div>
<p class="footer">自动渲染 · JSON+SQL · 双击任意标签页切换</p>
<script>function showTab(btn,id){document.querySelectorAll(".panel").forEach(p=>p.classList.remove("active"));document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));document.getElementById(id).classList.add("active");btn.classList.add("active")}
var C=''' + C + ''',N=''' + N + ''',E=''' + E + ''',H=''' + H + ''',I=''' + I + ''',T=''' + T + ''';\n''' + \
'''var M={"✅已确认":"ok","🟡待验证":"warn","🔴紧急":"urgent"};
document.getElementById("ct").innerHTML="<tr><th>编号</th><th>内容</th><th>来源</th><th>可靠性</th><th>关联</th></tr>"+C.map(c=>"<tr><td>"+c.id+"</td><td>"+c.content+"</td><td>"+c.source+"</td><td class=\\""+(M[c.confidence]||"")+"\\">"+c.confidence+"</td><td style=\\"color:#888;font-size:12px\\">"+(c.linked||[]).join(", ")+"</td></tr>").join("");
document.getElementById("nt").innerHTML="<tr><th>名称</th><th>角色</th><th>立场</th><th>势力</th><th>关键事实</th></tr>"+N.map(n=>"<tr><td><b>"+n.name+"</b></td><td>"+n.role+"</td><td>"+n.stance+"</td><td>"+(n.faction||"-")+"</td><td style=\\"font-size:12px;color:#888\\">"+(n.key_facts||[]).join("; ")+"</td></tr>").join("");
document.getElementById("tt").innerHTML="<tr><th>时间</th><th>事件</th><th>参与者</th><th>关联线索</th></tr>"+E.map(e=>"<tr><td>"+e.time+"</td><td>"+e.event+"</td><td>"+(e.participants||[]).join(", ")+"</td><td style=\\"color:#2196f3;font-size:12px\\">"+(e.related_clues||[]).join(", ")+"</td></tr>").join("");
var ch="";H.forEach(c=>{var p="";Object.keys(c.pools).forEach(k=>{var v=c.pools[k];var n=v.cur-v.max;var cl=n<0?"neg":(n>0?"pos":"");p+="<span class=\\"pool\\">"+k+' <span class="val">'+v.cur+"/"+v.max+"</span>"+(n!=0?'<span class="net '+cl+'">('+(n>0?"+":"")+n+")</span>":"")+"</span>"});ch+="<div style=\\"background:#1a1a30;margin:8px 0;padding:12px;border-radius:6px\\"><b>"+c.name+"</b> <span class=\\"tag tag-"+(c.type=="pc"?"pc":"npc")+"\\">"+(c.type=="pc"?"PC":"NPC")+"</span><div style=\\"margin:6px 0\\">"+p+"</div><span style=\\"font-size:12px;color:#888\\">位置: "+c.loc+" | 状态: "+c.status+"</span></div>"});document.getElementById("cc").innerHTML=ch;
document.getElementById("tl").innerHTML=T.map(t=>'<div style="background:#1a1a30;margin:6px 0;padding:10px 14px;border-radius:6px;display:flex;align-items:center"><span style="font-size:18px;margin-right:10px">'+t.priority+'</span><span '+(t.done?'style="text-decoration:line-through;color:#666"':"")+'>'+t.task+'</span><span style="margin-left:auto;font-size:11px;color:#888">'+t.related+'</span></div>').join("");
document.getElementById("it").innerHTML="<tr><th>关键词</th><th>文件</th><th>备注</th></tr>"+I.map(i=>'<tr><td><code style="background:#16213e;padding:1px 6px;border-radius:3px;font-size:12px">'+i.keyword+'</code></td><td>'+i.file+'</td><td style="color:#888;font-size:12px">'+i.note+'</td></tr>').join("");
</script></body></html>'''

out = os.path.join(LOG, "跑团面板.html")
with open(out, 'w', encoding='utf-8') as f: f.write(html)
print("{0} ({1}c/{2}n/{3}e/{4}ch/{5}td/{6}ix)".format(out, len(clues), len(npcs), len(events), len(char_rows), len(todos), len(index_data)))
