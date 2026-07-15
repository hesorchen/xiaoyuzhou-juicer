#!/usr/bin/env python3
"""Generate deterministic summary scaffolds and archive paths from fetch cache."""

import argparse
import configparser
import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path

MODES = ("quick", "full", "transcript", "deep")


def cache_root():
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "xiaoyuzhou-juicer"


def safe_name(value, limit=80):
    value = re.sub(r"[\\/:*?\"<>|\s]+", "-", str(value or "")).strip("-.")
    return value[:limit] or "untitled"


def without_md(value):
    return value[:-3] if value.lower().endswith(".md") else value


def stamp_seconds(value):
    parts = [int(x) for x in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}min"


def load_archive_config(path):
    config = configparser.ConfigParser()
    if path and Path(path).exists():
        config.read(path, encoding="utf-8")
    return config["archive"] if config.has_section("archive") else {}


def detect_history_dir(root):
    root = Path(root).expanduser()
    candidates = {}
    if not root.exists():
        return None
    for path in root.rglob("*-摘要.md"):
        candidates[path.parent] = candidates.get(path.parent, 0) + 1
    if not candidates:
        return None
    return max(candidates, key=lambda p: (candidates[p], str(p)))


def resolve_archive_dir(args, config):
    if args.archive_dir:
        return Path(args.archive_dir).expanduser()
    configured = config.get("dir") if config else None
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    if args.history_root:
        return detect_history_dir(args.history_root)
    return None


def filename_context(meta, topic):
    pub = (meta.get("pub_date") or "")[:10] or dt.date.today().isoformat()
    title = meta.get("title") or "untitled"
    episode = ""
    match = re.match(r"\s*([A-Za-z]*\.?\s*\d+[:：.]?)", title)
    if match:
        episode = safe_name(match.group(1), 20)
    return {
        "date": pub,
        "podcast": safe_name(meta.get("podcast"), 30),
        "episode": episode,
        "title": safe_name(title, 80),
        "topic": safe_name(topic or title, 50),
    }


def timeline(meta):
    chapters = meta.get("chapters") or []
    selected = chapters
    if len(chapters) > 12:
        stride = max(2, (len(chapters) + 11) // 12)
        selected = chapters[::stride]
    lines = ["```mermaid", "timeline", f"    title {safe_name(meta.get('title'), 50)}"]
    for chapter in selected:
        title = chapter.get("title", "")[:12]
        lines.append(f"    {chapter.get('ts', '')} : {title}")
    lines.append("```")
    return "\n".join(lines)


def chapter_scaffold(meta):
    chapters = meta.get("chapters") or []
    duration = int(meta.get("duration_sec") or 0)
    lines = []
    for index, chapter in enumerate(chapters):
        start = chapter.get("ts", "00:00")
        end = chapters[index + 1].get("ts") if index + 1 < len(chapters) else meta.get("duration_hms", "结束")
        heading = f"### {index + 1}. {chapter.get('title', '')}（{start}–{end}）"
        lines.extend([
            heading + "<!-- TODO: ⭐⭐⭐ 必听 / ⭐⭐ 选听 / ⭐ 可跳 -->",
            "",
            "- <!-- TODO：核心观点＋具体支撑；术语首次出现时给白话解释。 -->",
            "",
            f"> <!-- TODO：逐字稿原话；时间戳范围 {start}–{end}，节目总长 {duration}s。 -->",
            "",
        ])
    return "\n".join(lines)


def render_scaffold(meta, mode="full", comments_text=""):
    stats = meta.get("stats") or {}
    snapshot = meta.get("snapshot") or {}
    subscriptions = stats.get("podcast_subscriptions")
    subs = f"{subscriptions / 10000:.1f} 万" if subscriptions else "未知"
    age = snapshot.get("age_hours")
    age_note = f"；发布约 {age:g} 小时后抓取" if isinstance(age, (int, float)) else ""
    metadata_line = (
        f"> 节目：{meta.get('podcast') or ''}（订阅 {subs}）｜"
        f"时长 {meta.get('duration_hms') or ''}｜发布 {(meta.get('pub_date') or '')[:10]}"
    )
    heat_line = (
        f"| 热度 | 播放 {stats.get('play_count')} · 收藏 {stats.get('favorite_count')} · "
        f"评论 {stats.get('comment_count')}（节目订阅 {subs}{age_note}） |"
    )
    header = [
        f"# {meta.get('title', '')}", "",
        metadata_line,
        f"> 链接：<{meta.get('url') or ''}>", "",
        "## TL;DR", "", "<!-- TODO：严格三句话：谁、主线、最大信息增量。 -->", "",
    ]
    if mode == "transcript":
        return "\n".join(header + ["<!-- transcript 模式只归档逐字稿；无需生成摘要。 -->", ""])
    decision = [
        "## 值不值得听 · 决策卡", "",
        "| 维度 | 判断 |", "|------|------|",
        f"| 时长投入 | {fmt_duration(meta.get('duration_sec'))}；<!-- TODO：倍速／⭐⭐⭐ 章节 --> |",
        heat_line,
        "| 评论区情绪 | <!-- TODO --> |", "| 最适合谁 | <!-- TODO --> |",
        "| 一句话 | <!-- TODO：值得／可跳过 --> |", "",
    ]
    if mode == "quick":
        return "\n".join(header + decision + [
            "## 推荐章节", "", "<!-- TODO：3–5 个章节＋理由。 -->", "",
            "## 争议与存疑", "", "<!-- TODO -->", "",
        ])
    body = decision + [
        "## 听众怎么看", "", "<!-- TODO：风向、观点交叉表、聚类、热门原话；身份仅按接口明确字段。 -->", "",
    ]
    if comments_text:
        body.extend(["<!-- 评论源材料（完成后删除本注释块）", comments_text, "-->", ""])
    body.extend([
        "## 嘉宾背景卡（联网增强，与正片内容严格分区）", "", "<!-- TODO：每条带权威来源。 -->", "",
        "## 章节时间轴", "", timeline(meta), "",
        "## 章节摘要", "", chapter_scaffold(meta),
        "## 金句", "", "<!-- TODO：5–10 条逐字稿原话＋精确时间戳。 -->", "",
        "## 听完带走的 N 件事", "", "<!-- TODO：3–5 条可迁移启发。 -->", "",
        "## 提到的人 / 书 / 论文 / 产品", "", "| 类型 | 名称 | 语境 | 时间戳 |",
        "|------|------|------|--------|", "| <!-- TODO --> | | | |", "",
        "## 争议与存疑", "", "<!-- TODO：区分事实、嘉宾判断与编者推断。 -->", "",
    ])
    if mode == "deep":
        body.extend(["> deep 模式：摘要完成后接 paper-reading-report 生成技术精读 HTML。", ""])
    return "\n".join(header + body)


def main():
    parser = argparse.ArgumentParser(description="生成确定性的摘要骨架并按配置归档")
    parser.add_argument("eid")
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--cache-dir", default=str(cache_root()))
    parser.add_argument("--output")
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--archive-dir")
    parser.add_argument("--history-root", help="未配置目录时，从该目录下的历史 *-摘要.md 检测归档位置")
    parser.add_argument("--config", default="config/archive.ini")
    parser.add_argument("--topic")
    args = parser.parse_args()

    episode_dir = Path(args.cache_dir).expanduser() / args.eid
    with open(episode_dir / "meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    comments_path = episode_dir / "comments.md"
    comments = comments_path.read_text(encoding="utf-8") if comments_path.exists() else ""
    scaffold = render_scaffold(meta, args.mode, comments)
    output = Path(args.output) if args.output else episode_dir / "summary-scaffold.md"
    output.write_text(scaffold, encoding="utf-8")
    print(f"✓ 摘要骨架 → {output}")

    if not args.archive:
        return
    config = load_archive_config(args.config)
    archive_dir = resolve_archive_dir(args, config)
    if archive_dir is None:
        raise SystemExit("未找到归档目录：传 --archive-dir、配置 archive.ini，或传 --history-root")
    archive_dir.mkdir(parents=True, exist_ok=True)
    context = filename_context(meta, args.topic)
    default_pattern = "{date}-{podcast}-{episode}-{topic}-{kind}"
    pattern = config.get("filename_pattern", default_pattern) if config else default_pattern
    if args.mode != "transcript":
        summary_name = safe_name(without_md(pattern.format(**context, kind="摘要")), 180) + ".md"
        shutil.copy2(output, archive_dir / summary_name)
        print(f"✓ 摘要归档 → {archive_dir / summary_name}")
    transcript = episode_dir / "transcript.md"
    if transcript.exists():
        transcript_name = safe_name(without_md(pattern.format(**context, kind="逐字稿")), 180) + ".md"
        shutil.copy2(transcript, archive_dir / transcript_name)
        print(f"✓ 逐字稿归档 → {archive_dir / transcript_name}")


if __name__ == "__main__":
    main()
