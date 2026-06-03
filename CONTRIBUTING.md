# 贡献指南 Contributing

感谢你愿意改进本项目。这是一个个人维护的小工具，流程尽量轻量。

## 开始之前

- 本项目定位为**个人本地存档 / 学习**用途，**不接受**任何扩大爬取规模、绕过平台限制、或内置/分享账号凭证的改动。
- 接口为逆向所得，平台改版可能导致失效；修复这类问题的 PR 最受欢迎（见下）。

## 开发环境

纯标准库，**无需 `pip install`**。只需 Python 3.8+：

```bash
git clone https://github.com/hesorchen/xiaoyuzhou-juicer
cd xiaoyuzhou-juicer
python3 scripts/xyz_fetch.py --help
```

## 提交前自检

CI 会跑 Ruff lint 与多版本 `py_compile`。本地请先过一遍：

```bash
# lint（与 CI 同配置，见 pyproject.toml）
ruff check scripts/
# 语法/字节码编译
python3 -m compileall -q scripts
# 凭证泄露自检：应无输出
git diff --cached --name-only | grep -i token
```

> **铁律**：任何改动都不得把 token 写入产出文件、日志或提交。新增产物路径时请确认不含凭证。

## 提交规范

- commit message 用祈使句，简述「做了什么 + 为什么」。
- 面向用户的改动请在 [`CHANGELOG.md`](CHANGELOG.md) 的 `Unreleased` 段补一行。
- 改了接口/参数请同步更新 [`README.md`](README.md) 与 [`SKILL.md`](SKILL.md)。

## 常见可贡献方向

- 平台改版导致的接口/UA 修复（403/404/401）。
- 新的 shownotes 章节排版兼容。
- 文档与示例改进。
