#!/usr/bin/env python3
"""
通用规则书解析器 — 将 CHM/EPUB/PDF 格式的规则书转换为 AI 友好的结构化数据。

支持格式:
    - .chm  → HTML 提取 + 文本清洗 → Markdown / JSON
    - .epub → 章节提取 → Markdown（保留标题层级）
    - .pdf  → 文本提取（含表格检测） → Markdown / JSON

输出目标:
    1. rule_lib/[规则系统]/raw/     — 原始文本（保留完整内容）
    2. rule_lib/[规则系统]/tables/   — 提取的数据表（JSON）
    3. rule_lib/[规则系统]/index.md  — 结构化摘要索引
    4. rule_lib/[规则系统]/full.md   — 完整 Markdown（AI 可读全文本）

Usage:
    python rule_reader.py <input_file> [--output <dir>] [--name <rule_name>] [--format chm|epub|pdf]
    python rule_reader.py list  # 列出已导入的规则系统

Examples:
    python rule_reader.py "CoC7e核心规则书.epub" --name "coc7"
    python rule_reader.py "dnd5e_phb.pdf" --name "dnd5e" --output ./rule_lib
"""

import sys
import os
import json
import re
import argparse
import shutil
from pathlib import Path
from datetime import datetime


# ============================================================================
# 格式检测
# ============================================================================

def detect_format(filepath):
    """Detect file format from extension and magic bytes."""
    ext = Path(filepath).suffix.lower()

    if ext == '.chm':
        return 'chm'
    elif ext == '.epub':
        return 'epub'
    elif ext == '.pdf':
        return 'pdf'
    else:
        # Try magic bytes for misnamed files
        try:
            with open(filepath, 'rb') as f:
                header = f.read(8)
                if header[:4] == b'ITSF':
                    return 'chm'
                elif header[:4] == b'PK\x03\x04':
                    return 'epub'
                elif header[:5] == b'%PDF-':
                    return 'pdf'
        except Exception:
            pass
        return None


# ============================================================================
# CHM 解析
# ============================================================================

def parse_chm(filepath):
    """Extract text from CHM (Compiled HTML Help) file."""
    try:
        import pychm
        reader = pychm.CHMReader()
        reader.LoadCHM(filepath)

        # Try to get topic tree first
        topics = []
        try:
            topics = reader.GetTopicTree()
        except Exception:
            pass

        # Extract all HTML content
        pages = []
        if topics:
            for topic in topics:
                try:
                    html = reader.GetTopicContent(topic)
                    text = html_to_markdown(html)
                    pages.append({"title": topic.title if hasattr(topic, 'title') else '',
                                  "content": text})
                except Exception:
                    pass

        if not pages:
            return fallback_chm_extract(filepath)

        return {"source": "chm", "pages": pages, "structure": "topics"}

    except ImportError:
        return fallback_chm_extract(filepath)


def fallback_chm_extract(filepath):
    """Fallback: use 7-Zip or hh.exe for CHM extraction."""
    pages = []

    # Try 7-Zip first (most reliable)
    seven_zip_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"D:\Program Files\7-Zip\7z.exe",
    ]
    # Also check PATH
    import subprocess
    try:
        result = subprocess.run(['where', '7z'], capture_output=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.decode('gbk', errors='replace').strip().split('\n'):
                p = line.strip()
                if p and os.path.exists(p):
                    seven_zip_paths.insert(0, p)
    except Exception:
        pass

    for sz_path in seven_zip_paths:
        if not os.path.exists(sz_path):
            continue
        try:
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix='chm_7z_')
            subprocess.run(
                [sz_path, 'x', filepath, f'-o{tmpdir}', '-y'],
                capture_output=True, timeout=120, check=False
            )
            # Collect HTML files with hierarchy preserved
            tmp = Path(tmpdir)
            html_files = list(tmp.rglob('*.htm*'))
            if html_files:
                # Build tree from relative paths
                tree = {}
                for hf in html_files:
                    try:
                        rel = hf.relative_to(tmp)
                    except ValueError:
                        continue
                    parts = rel.parts
                    node = tree
                    for part in parts[:-1]:  # Directory hierarchy
                        if part not in node:
                            node[part] = {}
                        node = node[part]
                    # Leaf: store the file
                    node[parts[-1]] = hf

                # Recursively flatten tree into pages with depth
                def _flatten_tree(t, depth=0):
                    result = []
                    for key, val in sorted(t.items()):
                        if isinstance(val, Path):
                            try:
                                html = val.read_text(encoding='utf-8', errors='replace')
                                text = html_to_markdown(html)
                                if len(text.strip()) > 30:
                                    result.append({
                                        "title": val.stem,
                                        "content": f"<!-- {val.name} -->\n{text}",
                                        "depth": depth + 1
                                    })
                            except Exception:
                                pass
                        elif isinstance(val, dict):
                            children = _flatten_tree(val, depth + 1)
                            if children:
                                # Insert folder as section header
                                result.append({
                                    "title": key,
                                    "content": "",
                                    "depth": depth + 1,
                                    "is_section": True
                                })
                                result.extend(children)
                    return result

                pages = _flatten_tree(tree)
                # Deduplicate: merge single-child sections
                merged = []
                i = 0
                while i < len(pages):
                    pg = pages[i]
                    if pg.get('is_section') and i + 1 < len(pages) and pages[i + 1].get('depth', 0) > pg.get('depth', 0):
                        merged.append(pages[i + 1])
                        i += 2
                    elif pg.get('is_section'):
                        merged.append({"title": pg['title'], "content": "", "depth": pg['depth']})
                        i += 1
                    else:
                        merged.append(pg)
                        i += 1
                pages = merged

            shutil.rmtree(tmpdir, ignore_errors=True)
            if pages:
                print(f"  ✅ CHM extracted via 7-Zip: {len(pages)} sections from {len(html_files)} HTML files")
                return {"source": "chm+7z", "pages": pages, "structure": "sections"}
        except Exception as e:
            print(f"  ⚠️  7-Zip at {sz_path} failed: {e}")
            continue

    # Fallback: hh.exe (Windows only)
    # Check common install paths in addition to PATH
    hh_paths = [
        r"C:\Windows\hh.exe",
        r"C:\Windows\System32\hh.exe",
    ]
    hh_exe = None
    for p in hh_paths:
        if os.path.exists(p):
            hh_exe = p
            break
    if not hh_exe:
        try:
            result = subprocess.run(['where', 'hh.exe'], capture_output=True, timeout=5)
            if result.returncode == 0:
                hh_exe = result.stdout.decode('gbk', errors='replace').strip().split('\n')[0].strip()
        except Exception:
            pass

    if hh_exe:
        try:
            import tempfile, shutil
            tmpdir = str(Path(filepath).parent / '.chm_extract')
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir, ignore_errors=True)
            os.makedirs(tmpdir, exist_ok=True)
            subprocess.run(
                [hh_exe, '-decompile', tmpdir, filepath],
                capture_output=True, timeout=300, check=False
            )
            # Collect all HTML files and build hierarchy tree
            tmp = Path(tmpdir)
            html_files = list(tmp.rglob("*.htm*"))
            if html_files:
                tree = {}
                for hf in html_files:
                    try:
                        rel = hf.relative_to(tmp)
                    except ValueError:
                        continue
                    parts = rel.parts
                    node = tree
                    for part in parts[:-1]:
                        if part not in node:
                            node[part] = {}
                        node = node[part]
                    node[parts[-1]] = hf

                def _flatten_tree(t, depth=0):
                    result = []
                    for key, val in sorted(t.items()):
                        if isinstance(val, Path):
                            try:
                                raw = val.read_bytes()
                                meta_match = re.search(rb'charset=([a-zA-Z0-9-]+)', raw[:4096])
                                enc = meta_match.group(1).decode('ascii') if meta_match else 'utf-8'
                                text = raw.decode(enc, errors='replace')
                                text = html_to_markdown(text)
                                if len(text.strip()) > 50:
                                    result.append({
                                        "title": val.stem,
                                        "content": text,
                                        "depth": depth + 1
                                    })
                            except Exception:
                                pass
                        elif isinstance(val, dict):
                            children = _flatten_tree(val, depth + 1)
                            if children:
                                result.append({
                                    "title": key,
                                    "content": "",
                                    "depth": depth + 1,
                                    "is_section": True
                                })
                                result.extend(children)
                    return result

                pages = _flatten_tree(tree)
                merged = []
                i = 0
                while i < len(pages):
                    pg = pages[i]
                    if pg.get('is_section') and i + 1 < len(pages) and pages[i + 1].get('depth', 0) > pg.get('depth', 0):
                        merged.append(pages[i + 1])
                        i += 2
                    elif pg.get('is_section'):
                        merged.append({"title": pg['title'], "content": "", "depth": pg['depth']})
                        i += 1
                    else:
                        merged.append(pg)
                        i += 1
                pages = merged
            shutil.rmtree(tmpdir, ignore_errors=True)
            if pages:
                return {"source": "chm_hh", "pages": pages, "structure": "directories"}
        except Exception:
            pass

    # Absolute last resort: basic extraction note
    data = Path(filepath).read_bytes()
    pages.append({
        "title": "chm_parse_failed",
        "content": (
            f"CHM parsing requires additional tools.\n"
            f"File size: {len(data)} bytes.\n"
            f"Detected format: {'ITSF (valid CHM)' if data[:4] == b'ITSF' else 'Unknown'}.\n"
            f"Options:\n"
            f"  1. Install pychm: pip install pychm (may fail on Windows)\n"
            f"  2. Install 7-Zip from https://7-zip.org/\n"
            f"  3. Use online converter: chm → html → text\n"
            f"  4. Manually extract with: 7z x {Path(filepath).name}"
        )
    })

    return {"source": "chm", "pages": pages, "structure": "flat"}


# ============================================================================
# EPUB 解析
# ============================================================================

def parse_epub(filepath):
    """Extract text from EPUB file with chapter structure."""
    pages = []

    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(filepath)

        # Get table of contents
        toc = []
        for item in book.toc:
            if hasattr(item, 'title'):
                toc.append(item.title)
            elif isinstance(item, list) and len(item) > 0:
                if hasattr(item[0], 'title'):
                    toc.append(item[0].title)

        # Extract each document
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), 'html.parser')

            # Remove script/style tags
            for tag in soup(['script', 'style']):
                tag.decompose()

            # Extract text with structure
            title = ''
            h1_tag = soup.find('h1')
            if h1_tag:
                title = h1_tag.get_text(strip=True)

            # Convert to markdown
            md_lines = []
            if title:
                md_lines.append(f"# {title}\n")

            for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'table', 'li']):
                tag = elem.name
                text = elem.get_text(strip=True)

                if not text:
                    continue

                if tag == 'h1':
                    md_lines.append(f"\n# {text}\n")
                elif tag == 'h2':
                    md_lines.append(f"\n## {text}\n")
                elif tag == 'h3':
                    md_lines.append(f"\n### {text}\n")
                elif tag == 'h4':
                    md_lines.append(f"\n#### {text}\n")
                elif tag == 'table':
                    md_lines.append(table_to_markdown(elem))
                elif tag == 'li':
                    md_lines.append(f"- {text}")
                else:
                    md_lines.append(f"\n{text}\n")

            content = "\n".join(md_lines)
            if len(content.strip()) > 50:
                pages.append({"title": title or f"section_{len(pages)}", "content": content})

    except ImportError:
        pages.append({
            "title": "error",
            "content": "EPUB parsing requires: pip install ebooklib beautifulsoup4"
        })

    return {"source": "epub", "pages": pages, "toc": toc if pages else [],
            "structure": "chapters"}


# ============================================================================
# PDF 解析
# ============================================================================

def parse_pdf(filepath):
    """Extract text from PDF with table detection."""
    pages = []

    # Try pdfplumber first (best table support)
    try:
        import pdfplumber

        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and len(text.strip()) > 20:
                    pages.append({
                        "title": f"page_{i+1}",
                        "content": text,
                        "page_number": i + 1
                    })

                # Extract tables
                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    if table and len(table) > 1:
                        md_table = list_of_lists_to_md_table(table)
                        pages.append({
                            "title": f"table_p{i+1}_{j+1}",
                            "content": md_table,
                            "page_number": i + 1,
                            "is_table": True
                        })

        if pages:
            return {"source": "pdf", "pages": pages, "structure": "pages"}

    except ImportError:
        pass

    # Fallback: PyPDF2
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(filepath)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and len(text.strip()) > 20:
                pages.append({
                    "title": f"page_{i+1}",
                    "content": text,
                    "page_number": i + 1
                })

        if pages:
            return {"source": "pdf", "pages": pages, "structure": "pages"}

    except ImportError:
        pass

    pages.append({
        "title": "error",
        "content": "PDF parsing requires: pip install pdfplumber PyPDF2"
    })

    return {"source": "pdf", "pages": pages, "structure": "flat"}


# ============================================================================
# 通用工具函数
# ============================================================================

def sanitize_filename(name):
    """Remove characters unsafe for filenames."""
    return re.sub(r'[\\/*?:"<>|]', '', name).strip().replace(' ', '_')


def html_to_markdown(html_content):
    """Convert HTML to basic markdown."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup(['script', 'style']):
            tag.decompose()
        return soup.get_text(separator='\n', strip=True)
    except ImportError:
        # Crude regex-based HTML stripping
        clean = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.I)
        clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL | re.I)
        clean = re.sub(r'<[^>]+>', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean


def table_to_markdown(soup_table):
    """Convert BeautifulSoup table element to markdown table."""
    rows = soup_table.find_all('tr')
    if not rows:
        return ""

    md_rows = []
    for i, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        md_row = '| ' + ' | '.join(c.get_text(strip=True) for c in cells) + ' |'
        md_rows.append(md_row)

        if i == 0 and cells:
            # Add header separator
            sep = '|' + '|'.join(['---'] * len(cells)) + '|'
            md_rows.append(sep)

    return '\n'.join(md_rows)


def list_of_lists_to_md_table(data):
    """Convert list of lists to markdown table."""
    if not data:
        return ""

    # Filter None rows
    data = [row for row in data if row and any(cell for cell in row)]

    if not data:
        return ""

    # Normalize column count
    max_cols = max(len(row) for row in data)
    rows = []
    for i, row in enumerate(data):
        padded = list(row) + [''] * (max_cols - len(row))
        rows.append('| ' + ' | '.join(str(c or '') for c in padded) + ' |')
        if i == 0:
            rows.append('|' + '|'.join(['---'] * max_cols) + '|')

    return '\n'.join(rows)


# ============================================================================
# 主处理流程
# ============================================================================

def process_rulebook(filepath, output_dir, rule_name):
    """Parse a rulebook and output structured AI-friendly files."""
    fmt = detect_format(filepath)

    if not fmt:
        return {"error": f"Unknown format: {filepath}. Supported: chm, epub, pdf"}

    print(f"Detected format: {fmt}")
    print(f"Parsing: {filepath}")

    # Parse
    if fmt == 'chm':
        result = parse_chm(filepath)
    elif fmt == 'epub':
        result = parse_epub(filepath)
    elif fmt == 'pdf':
        result = parse_pdf(filepath)

    if not result.get('pages'):
        return {"error": "No content extracted. Check file integrity or install dependencies."}

    # Create output structure
    base = Path(output_dir) / rule_name
    raw_dir = base / 'raw'
    tables_dir = base / 'tables'
    raw_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    pages = result['pages']
    total_pages = len(pages)
    tables = [p for p in pages if p.get('is_table')]
    text_pages = [p for p in pages if not p.get('is_table')]

    # Save raw text pages with hierarchy-aware filenames
    # Track depth to build section-based numbering
    section_counters = {}
    for i, page in enumerate(text_pages):
        depth = page.get('depth', 2)
        title = page['title']
        content = page['content']

        # Reset child counters when at a shallower depth
        for d in list(section_counters.keys()):
            if d > depth:
                del section_counters[d]
        section_counters[depth] = section_counters.get(depth, 0) + 1

        # Build filename prefix from depth counters
        prefix_parts = []
        for d in range(1, depth + 1):
            prefix_parts.append(f"{section_counters.get(d, 1):02d}")
        file_prefix = '_'.join(prefix_parts)

        filename = raw_dir / f"{file_prefix}_{sanitize_filename(title)[:40]}.md"
        heading = '#' * min(depth, 6)
        filename.write_text(f"{heading} {title}\n\n{content}", encoding='utf-8')

    # Save tables as JSON
    for i, table in enumerate(tables):
        filename = tables_dir / f"table_{i+1:03d}.json"
        filename.write_text(
            json.dumps({"title": table['title'], "content": table['content']},
                       ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    # Smart full.md generation — skip if too large
    SMART_FULL_MD_THRESHOLD = 500  # pages; above this, skip monolithic full.md
    should_generate_full = total_pages <= SMART_FULL_MD_THRESHOLD

    if should_generate_full:
        full_md = []
        full_md.append(f"# {rule_name} — 完整规则书\n")
        full_md.append(f"> 来源: {Path(filepath).name}")
        full_md.append(f"> 格式: {fmt} | 提取页数: {total_pages} | 表格数: {len(tables)}")
        full_md.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        for page in pages:
            if page.get('is_table'):
                depth = min(page.get('depth', 3), 6)
                full_md.append(f"\n{'#' * depth} {page['title']}\n")
            elif page.get('content'):  # Content-bearing page
                depth = min(page.get('depth', 2), 6)
                full_md.append(f"\n{'#' * depth} {page['title']}\n")
                full_md.append(page['content'])
            else:
                # Section header only (folder)
                depth = min(page.get('depth', 2), 6)
                full_md.append(f"\n{'#' * depth} {page['title']}\n")

        full_content = '\n\n'.join(full_md)
        if len(full_content) < 2 * 1024 * 1024:  # Also check size < 2MB
            (base / 'full.md').write_text(full_content, encoding='utf-8')
        else:
            should_generate_full = False
            print(f"  ⚠️  full.md exceeds 2MB, skipped (use raw/ files + index instead)")

    if not should_generate_full:
        print(f"  ℹ️  Large rulebook ({total_pages} pages) — monolithic full.md skipped")
        print(f"  ℹ️  Navigate via index.md → raw/*.md files (each ~5-50KB)")

    # Generate index with quick-search anchors
    index_md = []
    index_md.append(f"# {rule_name} — 规则索引\n")
    index_md.append(f"> 来源: {Path(filepath).name} ({fmt})")
    index_md.append(f"> 总页数: {total_pages}\n")
    index_md.append("## 使用方式\n")
    if not should_generate_full:
        index_md.append("- **大型规则书已分页存储**，每个 `raw/*.md` 为独立可读单元")
        index_md.append("- 浏览下方目录找到需要的章节 → 打开对应 `raw/[文件名].md`")
    if tables:
        index_md.append(f"- **{len(tables)} 个数据表格**在 `tables/*.json`")
    index_md.append("")
    index_md.append("## 结构\n")
    index_md.append(f"- 原始格式: {fmt}")
    index_md.append(f"- 文本页数: {len(text_pages)}")
    index_md.append(f"- 提取表格: {len(tables)}")
    if not should_generate_full:
        index_md.append(f"- ℹ️ 未生成 full.md（规则书过大）\n")
    else:
        index_md.append("")

    index_md.append("## 内容导航\n")

    for page in pages[:1000]:  # Cap entries at 1000 for very large rulebooks
        title = page['title']
        is_table = page.get('is_table', False)
        has_content = bool(page.get('content', '').strip())
        depth = page.get('depth', 2)
        indent = "  " * (depth - 1)
        if has_content:
            preview = page['content'][:80].replace('\n', ' ') + '...'
            prefix = "📊" if is_table else "📄"
            index_md.append(f"{indent}- {prefix} **{title}** — {preview}")
        else:
            index_md.append(f"{indent}- 📁 **{title}**")

    index_md.append("\n## 文件索引\n")
    index_md.append(f"- 完整文本: [`full.md`](full.md)")
    index_md.append(f"- 原始分页: [`raw/`](raw/) ({len(text_pages)} 页)")
    index_md.append(f"- 数据表格: [`tables/`](tables/) ({len(tables)} 个)")

    (base / 'index.md').write_text('\n'.join(index_md), encoding='utf-8')

    return {
        "rule_name": rule_name,
        "format": fmt,
        "total_pages": total_pages,
        "text_pages": len(text_pages),
        "tables": len(tables),
        "output_dir": str(base.resolve()),
        "index": str((base / 'index.md').resolve()),
        "full_text": str((base / 'full.md').resolve())
    }


def list_rules(output_dir):
    """List all imported rule systems."""
    base = Path(output_dir)
    if not base.exists():
        print(f"No rule_lib found at {output_dir}")
        return

    rules = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / 'index.md').exists():
            idx = d / 'index.md'
            first_line = idx.read_text(encoding='utf-8').split('\n')[0].replace('# ', '')
            rules.append((d.name, first_line))

    if rules:
        print(f"\nImported rule systems ({len(rules)}):")
        print("-" * 50)
        for name, desc in rules:
            print(f"  [{name}] {desc}")
    else:
        print("No rule systems imported yet.")


def main():
    parser = argparse.ArgumentParser(
        description="Rulebook Parser — Convert CHM/EPUB/PDF to AI-friendly Markdown/JSON"
    )
    parser.add_argument("input", nargs='?', help="Input file path, or 'list' to show imported rules")
    parser.add_argument("--output", default="./rule_lib", help="Output directory (default: ./rule_lib)")
    parser.add_argument("--name", help="Rule system name (e.g., coc7, dnd5e, warhammer)")
    parser.add_argument("--format", choices=['chm', 'epub', 'pdf'], help="Force format (auto-detect by default)")

    args = parser.parse_args()

    if not args.input:
        parser.print_help()
        sys.exit(1)

    if args.input.lower() == 'list':
        list_rules(args.output)
        sys.exit(0)

    # Auto-detect name from filename if not provided
    rule_name = args.name
    if not rule_name:
        rule_name = Path(args.input).stem

    # Validate file exists
    if not Path(args.input).exists():
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    # Process
    result = process_rulebook(args.input, args.output, rule_name)

    if 'error' in result:
        print(f"\nERROR: {result['error']}")
        sys.exit(1)

    print(f"\n规则书导入成功: {rule_name}")
    print(f"  格式: {result['format']}")
    print(f"  总页面: {result['total_pages']}")
    print(f"  文本页: {result['text_pages']}")
    print(f"  表格数: {result['tables']}")
    print(f"  输出目录: {result['output_dir']}")
    print(f"  索引文件: {result['index']}")
    print(f"\nAI 使用方式: 加载 rule_lib/{rule_name}/index.md 获取概览，按需翻阅 full.md")


if __name__ == "__main__":
    main()
