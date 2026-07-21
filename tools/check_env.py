#!/usr/bin/env python3
"""
Dependency checker — run before using scripts.
Detects available Python, checks and installs deps with mirror fallback.
Usage: python check_env.py [--install] [--mirror tsinghua|aliyun|default]
"""
import sys
import os
import subprocess

MIN_PYTHON = (3, 8)

# Script-level dependency requirements
DEPENDENCIES = {
    "core": {
        "sqlite3": {"import": "sqlite3", "builtin": True, "desc": "SQLite database"},
        "json": {"import": "json", "builtin": True, "desc": "JSON processing"},
    },
    "rule_reader": {
        "beautifulsoup4": {"import": "bs4", "pip": "beautifulsoup4", "desc": "HTML/EPUB text extraction"},
        "pdfplumber": {"import": "pdfplumber", "pip": "pdfplumber", "desc": "PDF text + table extraction"},
        "PyPDF2": {"import": "PyPDF2", "pip": "PyPDF2", "desc": "PDF fallback extraction"},
        "ebooklib": {"import": "ebooklib", "pip": "ebooklib", "desc": "EPUB chapter extraction"},
        "python-docx": {"import": "docx", "pip": "python-docx", "desc": "DOCX fallback extraction (non-native format)"},
    },
    "dice_roller": {
        # no external deps — only stdlib
    }
}

PYPI_MIRRORS = {
    "tsinghua": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple",
    "ustc": "https://mirrors.ustc.edu.cn/pypi/web/simple",
    "default": "https://pypi.org/simple",
}


def check_python_version():
    v = sys.version_info[:2]
    if v < MIN_PYTHON:
        print(f"Python {v[0]}.{v[1]} < {MIN_PYTHON[0]}.{MIN_PYTHON[1]} (minimum)")
        return False
    print(f"Python {v[0]}.{v[1]}.{sys.version_info[2]} ")
    return True


def check_deps(category="all", auto_install=False, mirror="tsinghua"):
    missing = []
    installed = []

    if category == "all":
        deps_to_check = {}
        for cat_deps in DEPENDENCIES.values():
            deps_to_check.update(cat_deps)
    else:
        deps_to_check = DEPENDENCIES.get(category, {})

    for name, info in deps_to_check.items():
        if info.get("builtin"):
            try:
                __import__(info["import"])
                installed.append(f"  [builtin] {name}")
            except ImportError:
                missing.append(f"  [builtin-MISSING] {name}")
        else:
            try:
                __import__(info["import"])
                installed.append(f"  {name}")
            except ImportError:
                missing.append(f"  {name} ({info.get('desc', '')})")

    print("\nInstalled:")
    for s in installed:
        print(s)

    if missing:
        print(f"\nMissing ({len(missing)}):")
        for s in missing:
            print(s)

        if auto_install:
            return install_deps(missing, deps_to_check, mirror)

    return len(missing) == 0


def install_deps(missing_names, deps_dict, mirror="tsinghua"):
    mirror_url = PYPI_MIRRORS.get(mirror, PYPI_MIRRORS["tsinghua"])

    to_install = []
    for m in missing_names:
        name = m.strip().split(" ")[0]
        for dep_name, info in deps_dict.items():
            if dep_name == name and "pip" in info:
                to_install.append(info["pip"])
            elif dep_name == name and not info.get("builtin"):
                to_install.append(name)

    if not to_install:
        print("\nNo pip-installable dependencies missing.")
        return False

    print(f"\nInstalling: {', '.join(to_install)}")
    print(f"Mirror: {mirror_url}")

    success = True
    for pkg in to_install:
        print(f"\n> pip install {pkg}")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg,
                 "-i", mirror_url, "--trusted-host", mirror_url.split("//")[1].split("/")[0],
                 "-q"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                # verify
                for dep_name, info in deps_dict.items():
                    if info.get("pip") == pkg or dep_name == pkg:
                        try:
                            __import__(info["import"])
                            print(f"  {pkg}: OK")
                            break
                        except ImportError:
                            print(f"  {pkg}: installed but import failed")
                            success = False
                            break
            else:
                print(f"  {pkg}: FAILED")
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}")
                success = False
        except Exception as e:
            print(f"  {pkg}: ERROR - {e}")
            success = False

    if not success:
        print("\n---")
        print("Manual install:")
        print(f"  pip install {' '.join(to_install)} -i {mirror_url}")
        print("\nAlternative mirrors:")
        for name, url in PYPI_MIRRORS.items():
            print(f"  {name}: pip install -i {url} <package>")

    return success


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TRPG Copilot Environment Checker")
    parser.add_argument("--install", action="store_true", help="Auto-install missing deps")
    parser.add_argument("--mirror", default="tsinghua", choices=list(PYPI_MIRRORS.keys()),
                       help="PyPI mirror (default: tsinghua for China)")
    parser.add_argument("--category", default="all",
                       choices=["core", "rule_reader", "dice_roller", "all"],
                       help="Dependency category to check")
    args = parser.parse_args()

    print("TRPG Log Copilot — Environment Check")
    print("=" * 40)

    if not check_python_version():
        print(f"\nERROR: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required.")
        print("Install from: https://www.python.org/downloads/")
        sys.exit(1)

    ok = check_deps(args.category, args.install, args.mirror)

    if ok:
        print("\nAll dependencies OK.")
        sys.exit(0)
    else:
        print("\nSome dependencies missing. Run with --install to auto-fix.")
        sys.exit(1)


if __name__ == "__main__":
    main()
