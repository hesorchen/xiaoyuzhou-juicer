# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号遵循 [语义化版本 SemVer](https://semver.org/lang/zh-CN/)。

## [1.3.0] - 2026-07-15

### Added
- 开始前选择 `quick` / `full` / `transcript` / `deep` 四种处理模式。
- `xyz_render.py`：按官方章节生成确定性摘要骨架，支持显式目录、配置文件或受限历史目录检测后归档。
- `xyz_validate.py`：校验原标题、章节顺序、热度数字、时间戳、逐字稿引文与评论昵称。
- `meta.json.snapshot`：记录抓取时间、发布时长、每小时播放和每千次播放评论数。
- 离线单元测试覆盖压缩解码、章节提取、评论身份、原子写入、骨架与校验器。
- Codex UI 元数据 `agents/openai.yaml`。
- `install_skill.py`：从唯一源仓同步运行时文件并检查安装漂移，不覆盖 token 与私人归档配置。

### Changed
- refresh token 轮换增加进程锁与原子写回，短效 access token 写入权限受限的 XDG 缓存并复用。
- 评论接口的未知关系字段改为 `[关联:原值]`，不再把 `ORIGINAL` 等字段自动解释成主播或嘉宾。

### Fixed
- 兼容逐字稿 CDN 返回 gzip / deflate 压缩体导致的 UTF-8 解析失败。

## [1.2.0] - 2026-06-10

### Added
- 单集热度数据进 `meta.json`（`stats`：播放 / 收藏 / 评论 / 标记数 + 节目订阅数，SSR 免 token），并进决策卡新增「热度」行。
- 关键词搜索：`--search <关键词>`（配 `--search-type EPISODE|PODCAST`），补足榜单只有 Top 3 的短板。
- 结构化摘要新增六节：TL;DR 三句话、章节时间轴（mermaid timeline）、每章必听指数（⭐⭐⭐/⭐⭐/⭐）、术语白话注解、「提到的人/书/论文/产品」参考表（带时间戳）、「听完带走的 N 件事」takeaway。
- 多嘉宾（圆桌）背景卡规则：每人一卡、检索预算递减、>3 人只做主要发言者。
- `README.en.md` 英文文档；中文 README 增加 FAQ 与一键安装命令。

### Changed
- `摘要.md` 的 H1 标题改为**原样使用节目原标题**（多数节目自带期号，如 `140. …`），不再裁剪或改写，确保产出标题与小宇宙原始单集一致、可溯源。

## [1.1.0] - 2026-06-04

### Added
- 单集评论区首屏热评抓取（`--comments`，免 token，SSR 解析）。
- 评论者身份信号渲染：`[主播]` / `[嘉宾]` / `⭐资深`（重度听众），供观点加权。
- 账户级能力：发现页聚合（`--discover`）、订阅清单（`--subscriptions`）、订阅更新（`--inbox`）。
- 结构化摘要新增「值不值得听 · 决策卡」与「听众怎么看」框架（嘉宾观点 × 听众反应交叉表、金句众测回标）。
- 工程化：`pyproject.toml`、Ruff lint + `py_compile` 的 GitHub Actions CI、`SECURITY.md`、`CONTRIBUTING.md`、本 changelog。

### Changed
- 抓取产物迁移到 XDG 缓存目录（`~/.cache/xiaoyuzhou-juicer/<eid>/`），不再污染 skill 安装目录。

### Fixed
- 清理脚本 lint 问题（import 排序、歧义变量名、多语句分号、空 f-string）。

## [1.0.0] - 2026-05

### Added
- 首个版本：小宇宙单集元信息 / 官方章节 / shownotes / 音频直链抓取（免 token）。
- 逐字稿抓取（BYO-token，自动用 refresh token 续期 access token）。
- Claude Code skill 流程：说话人标注、WebFetch 嘉宾背景增强、官方章节为骨架的结构化摘要。
- 纯标准库实现，无第三方依赖，Python 3.8+。

[Unreleased]: https://github.com/hesorchen/xiaoyuzhou-juicer/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/hesorchen/xiaoyuzhou-juicer/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/hesorchen/xiaoyuzhou-juicer/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/hesorchen/xiaoyuzhou-juicer/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/hesorchen/xiaoyuzhou-juicer/releases/tag/v1.0.0
