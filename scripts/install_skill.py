#!/usr/bin/env python3
"""Install/sync the runtime skill from this repository without touching secrets."""

import argparse
import filecmp
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = [
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("config/archive.example.ini"),
    Path("scripts/install_skill.py"),
    Path("scripts/xyz_fetch.py"),
    Path("scripts/xyz_render.py"),
    Path("scripts/xyz_validate.py"),
]


def drift(target):
    changed = []
    for relative in RUNTIME_FILES:
        source = ROOT / relative
        installed = target / relative
        if not installed.exists() or not filecmp.cmp(source, installed, shallow=False):
            changed.append(relative)
    return changed


def install(target):
    for relative in RUNTIME_FILES:
        source = ROOT / relative
        installed = target / relative
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, installed)


def main():
    parser = argparse.ArgumentParser(description="同步仓库中的运行时 Skill 文件，不覆盖 token 或私人配置")
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--check", action="store_true", help="只检查源仓与安装副本是否漂移")
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    changed = drift(target)
    if args.check:
        if changed:
            for relative in changed:
                print(f"DRIFT: {relative}")
            raise SystemExit(1)
        print("✓ 安装副本与源仓一致")
        return
    install(target)
    print(f"✓ 已同步 {len(RUNTIME_FILES)} 个运行时文件 → {target}")


if __name__ == "__main__":
    main()
