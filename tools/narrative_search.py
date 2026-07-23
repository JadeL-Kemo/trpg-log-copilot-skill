# -*- coding: utf-8 -*-
"""叙事文件精准检索。不读全文——按场景边界切分。

Usage:
    python narrative_search.py <日志目录> scenes              # 列出所有场景
    python narrative_search.py <日志目录> scene <id>          # 提取指定场景文本
    python narrative_search.py <日志目录> grep <词> [--file F] # 搜索关键词(含上下文)
"""
import sys, re, os

LOG = sys.argv[1]
NARRATIVE = ['04_行动日志.md', '04a_过往日志.md', '05_推测与假设.md']

def find_scenes(text):
    """Yield (scene_id, header, start, end) from text."""
    idx = 0
    for m in re.finditer(r'^###\s+(\S+)([^\n]*)', text, re.MULTILINE):
        sid = m.group(1)
        title = m.group(2).strip(' —-')
        start = m.end()
        next_m = re.search(r'^###\s+', text[m.end():], re.MULTILINE)
        end = m.end() + next_m.start() if next_m else len(text)
        content = text[start:end].strip()
        line_count = content.count('\n') + 1
        yield {'id': sid, 'title': title, 'start': start, 'end': end, 
               'content': content, 'lines': line_count, 'idx': idx}
        idx += 1

def cmd_scenes():
    """List all scenes across narrative files."""
    total = 0
    for fname in NARRATIVE:
        fpath = os.path.join(LOG, fname)
        if not os.path.exists(fpath): continue
        text = open(fpath, encoding='utf-8').read()
        scenes = list(find_scenes(text))
        if not scenes: continue
        print("\n{0} ({1} scenes)".format(fname, len(scenes)))
        for s in scenes:
            time_m = re.search(r'(\d{2}:\d{2})', s['title'])
            t = time_m.group(1) if time_m else '-'
            print("  {0:<10} {1:<8} {2:>4}行  {3}".format(s['id'], t, s['lines'], s['title']))
        total += len(scenes)
    if total == 0:
        print("No scenes found. Add '### SXX_RXX — Title' headers to narrative files.")

def cmd_scene(sid):
    """Extract one scene by ID."""
    for fname in NARRATIVE:
        fpath = os.path.join(LOG, fname)
        if not os.path.exists(fpath): continue
        text = open(fpath, encoding='utf-8').read()
        for s in find_scenes(text):
            if s['id'] == sid:
                print(s['content'])
                return
    print("Scene '{0}' not found".format(sid))

def cmd_grep(word, file_filter='04a'):
    """Search keyword across narrative files, return matching lines with 2-line context."""
    any_match = False
    for fname in NARRATIVE:
        if file_filter and file_filter not in fname: continue
        fpath = os.path.join(LOG, fname)
        if not os.path.exists(fpath): continue
        
        text = open(fpath, encoding='utf-8').read()
        scenes = list(find_scenes(text))
        lines = text.split('\n')
        
        matched = False
        for i, line in enumerate(lines):
            if word in line:
                any_match = True
                if not matched:
                    print("\n--- {0} ---".format(fname))
                    matched = True
                # Find which scene this line belongs to
                scene_id = '?'
                for s in reversed(scenes):
                    start_line = text[:s['start']].count('\n')
                    end_line = text[:s['end']].count('\n')
                    if start_line <= i <= end_line:
                        scene_id = s['id']; break
                
                ctx_start = max(0, i-2); ctx_end = min(len(lines), i+3)
                print("  [{0}:{1}] {2}".format(scene_id, i+1, line.strip()))
                for j in range(ctx_start, ctx_end):
                    if j != i:
                        marker = '    ' if j in (ctx_start, ctx_end-1) else '  | '
                        print("{0}{1:>4}: {2}".format(marker, j+1, lines[j].strip()))
        if matched: print()
    
    if not any_match:
        print("No matches for '{0}' in narrative files".format(word))

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    
    cmd = sys.argv[2]
    if cmd == 'scenes':
        cmd_scenes()
    elif cmd == 'scene':
        cmd_scene(sys.argv[3] if len(sys.argv) > 3 else '')
    elif cmd == 'grep':
        word = sys.argv[3] if len(sys.argv) > 3 else ''
        file_filter = None
        for i, a in enumerate(sys.argv):
            if a == '--file' and i+1 < len(sys.argv):
                file_filter = sys.argv[i+1]
        cmd_grep(word, file_filter)
