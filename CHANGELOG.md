# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循 [语义化版本 SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.0.0] - 2026-06-04

首个公开发布。一条小宇宙单集链接，榨成可读逐字稿 + 官方章节 + 嘉宾背景增强 + 结构化摘要。

### Added
- 单集抓取（免 token，SSR 解析）：元信息 / 官方章节 / shownotes / 音频直链 / 评论区首屏热评（`--comments`）。
- 逐字稿抓取（BYO-token，自动用 refresh token 续期 access token）。
- 评论者身份信号渲染：`[主播]` / `[嘉宾]` / `⭐资深`（重度听众），供观点加权。
- 账户级能力：发现页聚合（`--discover`）、订阅清单（`--subscriptions`）、订阅更新（`--inbox`）。
- Claude Code skill 流程：说话人标注、WebFetch 嘉宾背景增强、官方章节为骨架的结构化摘要。
- 结构化摘要框架：「值不值得听 · 决策卡」与「听众怎么看」（嘉宾观点 × 听众反应交叉表、金句众测回标）。
- 抓取产物写入 XDG 缓存目录（`~/.cache/xiaoyuzhou-juicer/<eid>/`），不污染 skill 安装目录。
- 工程化：`pyproject.toml`、Ruff lint + `py_compile` 的 GitHub Actions CI、`SECURITY.md`、`CONTRIBUTING.md`、issue/PR 模板。
- 纯标准库实现，无第三方运行时依赖，Python 3.8+。

[Unreleased]: https://github.com/hesorchen/xiaoyuzhou-juicer/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/hesorchen/xiaoyuzhou-juicer/releases/tag/v1.0.0
