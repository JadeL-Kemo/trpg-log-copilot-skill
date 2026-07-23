# -*- coding: utf-8 -*-
"""MD文件原子操作工具。AI不读文件全文——工具定位、追加、替换。

Usage:
    python file_ops.py append-table <file> <cols...>
        追加一行到MD表格末尾。格式: --col name=value
        返回: 新行的id值（用于后续关联）

    python file_ops.py replace-scene <file> <scene_id> [--text "<new>"] [--keep-header]
        替换指定场景区块。不传--text则返回当前内容（AI先读后改）。

    python file_ops.py append-scene <file> <scene_id> <title> [--time HH:MM]
        在文件末尾追加新场景(### 标题块)。
"""
import sys, re, os

def _read(fpath):
    with open(fpath, encoding='utf-8') as f: return f.read()

def _write(fpath, text):
    with open(fpath, 'w', encoding='utf-8') as f: f.write(text)

def _last_id(text):
    """Extract last CL-XXX / NPC-XXX id from table."""
    ids = re.findall(r'(CL-\d+|NPC-\d+)', text)
    return ids[-1] if ids else None

def _next_id(last):
    if not last: return None
    prefix, num = re.match(r'([A-Z]+-)(\d+)', last).groups()
    return prefix + str(int(num) + 1).zfill(len(num))

# ==================== append-table ====================
def append_table(mdfile, col_args):
    """Append a row to MD table. col_args: ['id=CL-013','content=...','source=...',...]
    Returns the id of the new row."""
    text = _read(mdfile)
    last = _last_id(text)
    nid = _next_id(last) if last else col_args[0].split('=',1)[1] if col_args[0].startswith('id=') else None
    
    # Parse columns
    cols = {}
    for a in col_args:
        if '=' in a: k, v = a.split('=', 1); cols[k] = v
    
    if 'id' not in cols and nid:
        cols['id'] = nid
    
    # Build row line — read header to get column order
    header_match = re.search(r'\|([^|]+\|)+', text)
    if header_match:
        header_cols = [c.strip() for c in header_match.group(0).strip('|').split('|')]
        header_cols = [h for h in header_cols if h]  # filter empty
        ordered = []
        for h in header_cols:
            ordered.append(cols.get(h, ''))
        row = '| ' + ' | '.join(ordered) + ' |'
    else:
        row = '| ' + ' | '.join(cols.values()) + ' |'
    
    # Append
    text = text.rstrip('\n') + '\n' + row + '\n'
    _write(mdfile, text)
    
    rid = cols.get('id', nid or '?')
    print("appended: {0}".format(rid))
    return rid

# ==================== replace-scene ====================
def replace_scene(mdfile, scene_id, new_text=None, keep_header=True):
    """Replace scene block identified by ### Sxx or <!-- scene: Sxx -->.
    Without --text: prints current content and exits (AI reads, then calls again with --text).
    """
    text = _read(mdfile)
    
    # Find scene block boundaries
    patterns = [
        r'(###\s+{0}\b[^\n]*\n)'.format(re.escape(scene_id)),
        r'(<!--\s*scene:\s*{0}\s*-->)'.format(re.escape(scene_id)),
    ]
    
    start = end = None
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            start = m.start()
            header_line = m.group(1)
            # Find next scene boundary
            next_scene = re.search(r'\n(### |<!-- scene:)', text[m.end():])
            if next_scene:
                end = m.end() + next_scene.start()
            else:
                end = len(text)
            break
    
    if start is None:
        print("ERROR: scene '{0}' not found".format(scene_id))
        return None
    
    current = text[m.end()+1:end].strip() if start is not None else ''
    
    if new_text is None:
        # Read-only mode
        print(current)
        return current
    
    # Replace
    before = text[:start]
    after = text[end:]
    if keep_header:
        result = before + header_line + '\n' + new_text.strip() + '\n' + after
    else:
        result = before + new_text.strip() + '\n' + after
    
    _write(mdfile, result)
    print("replaced: {0} ({1} chars)".format(scene_id, len(new_text)))
    return True

# ==================== append-scene ====================
def append_scene(mdfile, scene_id, title, time_str=None):
    """Append a new scene block at end of file."""
    text = _read(mdfile).rstrip('\n')
    
    time_suffix = ' ({0})'.format(time_str) if time_str else ''
    block = '\n\n### {0} — {1}{2}\n<!-- scene: {0} -->\n\n'.format(scene_id, title, time_suffix)
    
    _write(mdfile, text + block)
    print("appended scene: {0}".format(scene_id))
    return scene_id

# ==================== CLI ====================
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    
    cmd = sys.argv[1]; fpath = sys.argv[2]
    
    if cmd == 'append-table':
        col_args = []
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == '--col' and i+1 < len(sys.argv):
                col_args.append(sys.argv[i+1]); i += 2
            elif '=' in sys.argv[i] and not sys.argv[i].startswith('--'):
                col_args.append(sys.argv[i]); i += 1
            else:
                i += 1
        append_table(fpath, col_args)
    
    elif cmd == 'replace-scene':
        sid = sys.argv[3]
        new_text = None
        keep_header = True
        i = 4
        while i < len(sys.argv):
            if sys.argv[i] == '--text' and i+1 < len(sys.argv):
                new_text = sys.argv[i+1]; i += 2
            elif sys.argv[i] == '--no-header':
                keep_header = False; i += 1
            else:
                i += 1
        replace_scene(fpath, sid, new_text, keep_header)
    
    elif cmd == 'append-scene':
        sid, title = sys.argv[3], sys.argv[4]
        time_str = None
        if len(sys.argv) > 5 and sys.argv[5] == '--time':
            time_str = sys.argv[6] if len(sys.argv) > 6 else None
        append_scene(fpath, sid, title, time_str)
    
    else:
        print("Unknown command: {0}".format(cmd))
