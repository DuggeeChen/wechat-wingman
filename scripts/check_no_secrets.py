#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前守卫：确认私人文件和高危字符串没有进仓库。

用法：
    python scripts/check_no_secrets.py

退出码 0 = 干净；1 = 发现问题（CI 会因此失败）。
在 git 仓库里只检查被追踪的文件；不在仓库里则退化成扫当前目录。
"""
import os
import re
import subprocess
import sys

# Windows 上 stdout 可能是 cp1252（GitHub Actions 的 runner 就是），打印中文会直接
# 抛 UnicodeEncodeError。统一按 UTF-8 输出，本地和 CI 表现一致。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 这些文件属于「本机私有」，永远不该被提交
FORBIDDEN_NAMES = {"config.json", ".env", "ui_state.json", "debug_last.png"}
FORBIDDEN_EXT = {".log", ".log.1"}
FORBIDDEN_PREFIX = ("wx_helper.log",)

# 常见密钥形态
PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "疑似 OpenAI 风格的 API key"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{24,}"), "硬编码的 Bearer token"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "疑似长十六进制密钥"),
]

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".ttf", ".otf", ".woff", ".woff2", ".zip"}
MAX_SCAN_BYTES = 2_000_000


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
        files = [f.strip() for f in out.splitlines() if f.strip()]
        if files:
            return files
    except Exception:
        pass
    files = []
    for root, dirs, names in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            files.append(os.path.relpath(os.path.join(root, n), ".").replace("\\", "/"))
    return files


def main():
    problems = []
    files = tracked_files()
    for f in files:
        base = os.path.basename(f)
        ext = os.path.splitext(base)[1].lower()
        if base in FORBIDDEN_NAMES or ext in FORBIDDEN_EXT or base.startswith(FORBIDDEN_PREFIX):
            problems.append("%s  ->  私人文件不该入库（.gitignore 漏了？）" % f)
            continue
        if ext in BINARY_EXT:
            continue
        try:
            if os.path.getsize(f) > MAX_SCAN_BYTES:
                continue
            text = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for rx, why in PATTERNS:
            m = rx.search(text)
            if m:
                problems.append("%s  ->  %s：%s…" % (f, why, m.group(0)[:12]))

    print("已检查 %d 个文件。" % len(files))
    if problems:
        print("\n发现问题 %d 处：" % len(problems))
        for p in problems:
            print("  [!] " + p)
        return 1
    print("干净：没有私人文件，也没有疑似密钥。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
