# -*- coding: utf-8 -*-
"""本地 HTTP 面板服务器 — 毫秒启动，空闲自停，端口持久化。

Usage:
    python tools/serve.py <跑团日志目录> [--port 9201] [--idle 300] [--hidden]
    
    --idle N   空闲N秒无请求后自动关闭（默认300=5分钟，设0为永不关闭）
    --port N   指定端口（覆盖已存储的端口）
    --hidden   启动后隐藏控制台窗口（Windows：脱离控制台，Linux/Mac：后台运行）
    
首次启动自动选端口(9201起)，存储到 .port 文件，后续复用。
"""
import os, sys, time, json, socket, webbrowser, http.server, socketserver, threading

LOG = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else '跑团日志'
PORT = 0; IDLE = 300; HIDDEN = False

for i, a in enumerate(sys.argv):
    if a == '--port' and i+1 < len(sys.argv): PORT = int(sys.argv[i+1])
    if a == '--idle' and i+1 < len(sys.argv):
        try: IDLE = int(sys.argv[i+1])
        except: pass
    if a == '--hidden': HIDDEN = True

if not os.path.isdir(LOG):
    print("ERROR: {0} not found".format(LOG))
    sys.exit(1)

os.chdir(LOG)

# --- Port selection (stable, no creep) ---
port_file = os.path.join(LOG, '.port')

def port_busy(p):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3); s.bind(('', p)); s.close()
        return False
    except: return True

has_stored = os.path.exists(port_file)
stored = 0
if has_stored:
    try:
        with open(port_file) as f: stored = json.load(f)
    except: has_stored = False

# Priority: explicit --port > stored .port > auto-pick 9201
if PORT == 0 and has_stored:
    PORT = stored

if PORT == 0:
    # First run: try 9201, fallback to 9202
    PORT = 9201 if not port_busy(9201) else 9202
    if port_busy(PORT):
        print("ERROR: ports 9201-9202 both occupied"); sys.exit(1)
else:
    # Reusing stored/explicit port — check it
    if port_busy(PORT):
        print("ERROR: port {0} occupied — is another serve.py running?".format(PORT))
        print("  Kill it or use: python tools/serve.py ... --port {0}".format(PORT+1))
        sys.exit(1)

with open(port_file, 'w') as f: json.dump(PORT, f)

# --- Server ---
last_req = time.time()
lock = threading.Lock()

class PanelHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def do_GET(self):
        global last_req
        with lock: last_req = time.time()
        if self.path == '/api/data':
            self._serve_data()
            return
        if self.path.startswith('/api/'):
            try:
                import urllib.parse, sqlite3
                qs = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(qs)
                sid = urllib.parse.unquote(params.get('id', [''])[0])
                q = urllib.parse.unquote(params.get('q', [''])[0])
                text = ''
                db = os.path.join('.', 'trpg_data.db')
                if os.path.exists(db):
                    conn = sqlite3.connect(db)
                    # 1. Exact scene_id match
                    row = conn.execute(
                        "SELECT chunk_text FROM narrative_chunks WHERE scene_id=? LIMIT 1", (sid,)).fetchone()
                    # 2. LIKE fallback
                    if not row:
                        row = conn.execute(
                            "SELECT chunk_text FROM narrative_chunks WHERE chunk_text LIKE ? LIMIT 1", ('%' + sid + '%',)).fetchone()
                    # 3. FTS5 content search
                    if not row and q:
                        try:
                            row = conn.execute(
                                "SELECT chunk_text FROM narrative_fts WHERE chunk_text MATCH ? LIMIT 1", (q.replace(' ', ' AND '),)).fetchone()
                        except: pass
                    conn.close()
                    if row: text = row[0]
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(text.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
            return
        super().do_GET()
    
    def _serve_data(self):
        """Return full panel data as JSON — pure JS rendering."""
        import json, sqlite3
        db = os.path.join('.', 'trpg_data.db')
        if not os.path.exists(db):
            self._json_resp({"error": "no db"})
            return
        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        data = {
            "clues": [dict(r) for r in conn.execute("SELECT id,content,source,confidence,tags,linked_ids FROM clues ORDER BY id")],
            "npcs": [dict(r) for r in conn.execute("SELECT id,name,role,stance,faction,key_facts,relationships FROM npcs ORDER BY id")],
            "events": [dict(r) for r in conn.execute("SELECT event_time,event,participants,related_clues,notes,scene_id FROM timeline_events WHERE category IS NULL OR category != 'chronicle' ORDER BY COALESCE(event_date,event_time), event_time")],
            "chronicles": [dict(r) for r in conn.execute("SELECT event_date,event,participants,related_clues,notes FROM timeline_events WHERE category='chronicle' ORDER BY event_date")],
            "relations": [dict(r) for r in conn.execute("SELECT id,npc_a,npc_b,rel_type,direction,source_ref FROM npc_relations ORDER BY npc_a,npc_b")],
            "labels": {"verified": {}, "confidence": {}}
        }
        for r in conn.execute("SELECT key,cn_name,category FROM dict_labels WHERE category IN ('verified','confidence')"):
            data["labels"][r['category']][r['key']] = r['cn_name']
        conn.close()
        # Add character dash summary
        conn2 = sqlite3.connect(db); conn2.row_factory = sqlite3.Row
        chars = []
        for ch in conn2.execute("SELECT char_name,char_type,base_stats FROM char_base ORDER BY CASE char_type WHEN 'pc' THEN 0 END, char_name"):
            base = json.loads(ch['base_stats']); totals = dict(base)
            for d in conn2.execute("SELECT deltas FROM char_state_log WHERE char_name=? ORDER BY seq", (ch['char_name'],)):
                for k, v in json.loads(d['deltas']).items(): totals[k] = totals.get(k, 0) + v
            last = conn2.execute("SELECT loc_new,status_new FROM char_state_log WHERE char_name=? AND (loc_new IS NOT NULL OR status_new IS NOT NULL) ORDER BY seq DESC LIMIT 1", (ch['char_name'],)).fetchone()
            pools = {}
            for k in sorted(base.keys()):
                pools[k] = {"cur": totals.get(k, '?'), "max": base[k]}
            chars.append({"name": ch['char_name'], "type": ch['char_type'], "pools": pools,
                "loc": last['loc_new'] if last and last['loc_new'] else '-',
                "status": last['status_new'] if last and last['status_new'] else '-'})
        conn2.close()
        data["chars"] = chars

        # Todos — parsed from MD (no SQL table)
        import re as _re3
        todos = []
        valid_ids = {c['id'] for c in data['clues']}
        todo_path = os.path.join('.', '06_待办.md')
        if os.path.exists(todo_path):
            for line in open(todo_path, encoding='utf-8').readlines():
                line = line.strip()
                if not (line.startswith('- [') or line.startswith('- ')): continue
                done = '[x]' in line[:6]
                task = line[line.find(']')+1:].strip() if ']' in line[:6] else line[2:].strip()
                priority = line[line.find('[')+1:line.find(']')] if '[' in line[:6] else ''
                reason = ''
                rm = _re3.search(r'\((.+?)\)', task)
                if rm: reason = rm.group(1); task = _re3.sub(r'\s*\(.+?\)', '', task)
                ref_ids = []
                m = _re3.search(r'→?\s*(CL-\d[\d,\s]*)', task)
                if m:
                    ref_ids = [x.strip() for x in _re3.split(r'[,，\s]+', m.group(1)) if x.strip() and x.strip() in valid_ids]
                    task = _re3.sub(r'→?\s*CL-\d[\d,\s]*', '', task).strip()
                todos.append({"task": task, "priority": priority, "done": done, "reason": reason, "ref_ids": ref_ids})
        data["todos"] = todos

        self._json_resp(data)
    
    def _json_resp(self, data):
        import json
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, fmt, *args): pass

httpd = socketserver.TCPServer(("", PORT), PanelHandler)
httpd.timeout = 1

def idle_watcher():
    while True:
        time.sleep(10)
        with lock: elapsed = time.time() - last_req
        if IDLE > 0 and elapsed > IDLE:
            print("\n[serve] {0}s idle — shutting down".format(int(elapsed)))
            threading.Thread(target=httpd.shutdown, daemon=True).start()
            return

if IDLE > 0:
    threading.Thread(target=idle_watcher, daemon=True).start()
    idle_note = "idle {0}s then stop".format(IDLE)
else:
    idle_note = "never stop"

url = "http://localhost:{0}/panel.html".format(PORT)
if not HIDDEN:
    webbrowser.open(url)

print("=" * 45)
print("  TRPG Panel")
print("  {0}".format(url))
print("  {0}".format(idle_note))
print("  Ctrl+C to stop")
print("=" * 45)
sys.stdout.flush()

try:
    httpd.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    httpd.server_close()
    print("\n[serve] stopped.")
