#!/usr/bin/env python3
"""Validate a generated Xiaoyuzhou summary against deterministic source files."""

import argparse
import json
import re
from pathlib import Path

FULL_SECTIONS = [
    "TL;DR", "值不值得听 · 决策卡", "听众怎么看", "嘉宾背景卡",
    "章节时间轴", "章节摘要", "金句", "听完带走", "提到的人", "争议",
]


def timestamp_seconds(value):
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def normalize(value):
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value).lower()


def fuzzy_quote_match(quote, transcript):
    quote = normalize(quote)
    transcript = normalize(transcript)
    if len(quote) < 10:
        return True
    if quote[:12] in transcript:
        return True
    width = 4
    shingles = {quote[i:i + width] for i in range(len(quote) - width + 1)}
    if not shingles:
        return True
    hits = sum(shingle in transcript for shingle in shingles)
    return hits / len(shingles) >= 0.65


def comment_authors(comments):
    names = set()

    def collect(comment):
        names.add((comment.get("author") or {}).get("nickname", ""))
        for reply in comment.get("replies") or []:
            collect(reply)

    for comment in comments.get("comments", []):
        collect(comment)
    return names


def section_positions(text, expected):
    positions = []
    for name in expected:
        match = re.search(rf"^##[^\n]*{re.escape(name)}", text, re.M)
        positions.append(match.start() if match else -1)
    return positions


def validate(summary_text, meta, transcript_text="", comments=None, mode="full"):
    errors, warnings = [], []
    first = summary_text.splitlines()[0] if summary_text.splitlines() else ""
    if first != f"# {meta.get('title', '')}":
        errors.append("H1 与 meta.json 的 title 不完全一致")

    expected = FULL_SECTIONS if mode in ("full", "deep") else ["TL;DR", "值不值得听 · 决策卡", "争议"]
    positions = section_positions(summary_text, expected)
    missing = [name for name, position in zip(expected, positions) if position < 0]
    if missing:
        errors.append("缺少章节：" + "、".join(missing))
    present = [position for position in positions if position >= 0]
    if present != sorted(present):
        errors.append("摘要章节顺序不符合 Skill 规范")

    duration = int(meta.get("duration_sec") or 0)
    for value in re.findall(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", summary_text):
        if duration and timestamp_seconds(value) > duration + 2:
            errors.append(f"时间戳超出节目时长：[{value}]")

    stats = meta.get("stats") or {}
    decision_match = re.search(r"^\| 热度 \|(.+)$", summary_text, re.M)
    if decision_match:
        decision = decision_match.group(1)
        for key, label in (("play_count", "播放"), ("favorite_count", "收藏"), ("comment_count", "评论")):
            value = stats.get(key)
            if value is not None and str(value) not in decision:
                errors.append(f"决策卡热度缺少原始{label}数 {value}")

    if "TODO" in summary_text:
        warnings.append("摘要仍包含 TODO 占位符")

    if transcript_text:
        source_sections = []
        for section_name in ("章节摘要", "金句"):
            match = re.search(rf"^## {section_name}(.*?)(?=^## |\Z)", summary_text, re.M | re.S)
            if match:
                source_sections.append(match.group(1))
        for quote in re.findall(r"^>\s*[“\"]?(.{12,}?)[”\"]?(?:——|\s*\[)", "\n".join(source_sections), re.M):
            if not fuzzy_quote_match(quote, transcript_text):
                warnings.append(f"引文未在逐字稿中直接匹配：{quote[:24]}…（可能做了 ASR 订正）")

    if comments:
        source_names = comment_authors(comments)
        section = re.search(r"## 听众怎么看(.*?)(?=\n## )", summary_text, re.S)
        if section:
            mentioned = set(re.findall(r"^>.*——([^（\n]+)(?:（|\n)", section.group(1), re.M))
            cleaned = {re.sub(r"[［\[].*?[］\]]", "", name).strip() for name in mentioned}
            unknown = sorted(name for name in cleaned if name and name not in source_names)
            if unknown:
                warnings.append("评论区出现未在首屏源数据中找到的昵称：" + "、".join(unknown))

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description="校验摘要与抓取源的一致性")
    parser.add_argument("summary")
    parser.add_argument("--meta", required=True)
    parser.add_argument("--transcript")
    parser.add_argument("--comments")
    parser.add_argument("--mode", choices=("quick", "full", "deep"), default="full")
    args = parser.parse_args()

    summary = Path(args.summary).read_text(encoding="utf-8")
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    transcript = Path(args.transcript).read_text(encoding="utf-8") if args.transcript else ""
    comments = json.loads(Path(args.comments).read_text(encoding="utf-8")) if args.comments else None
    errors, warnings = validate(summary, meta, transcript, comments, args.mode)
    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        raise SystemExit(1)
    print(f"✓ 校验通过（{len(warnings)} 条警告）")


if __name__ == "__main__":
    main()
