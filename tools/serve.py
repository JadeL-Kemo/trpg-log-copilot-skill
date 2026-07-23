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
        if self.path.startswith('/api/'):
            try:
                import urllib.parse, sqlite3
                qs = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(qs)
                sid = urllib.parse.unquote(params.get('id', [''])[0])
                q = urllib.parse.unquote(params.get('q', [''])[0])  # event text for FTS5 fallback
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
