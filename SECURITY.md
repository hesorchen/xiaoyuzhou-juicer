# 安全策略 Security Policy

## 凭证处理（BYO-token）

本工具采用 **自带凭证（Bring-Your-Own-Token）** 模式，**不内置、不分发任何账号凭证**。

- 凭证只读取自本地 `config/token.txt` 或环境变量 `XYZ_REFRESH_TOKEN`，**只存在于你自己的机器上**。
- `config/token.txt` 已写入 [`.gitignore`](.gitignore)，不会被提交到仓库。
- **凭证绝不写入任何产出文件**（逐字稿 / 摘要 / 缓存 JSON 均不含 token）。
- refresh token 会在每次续期后轮换，新值仅回存到本地 `config/token.txt`。

> 如果你 fork 或克隆本仓库，请再次确认 `config/token.txt` 未被 `git add`。
> 提交前可执行：`git diff --cached --name-only | grep -i token` —— 若有输出立即撤销暂存。

## 数据边界

- 仅抓取 **你自己账号有权访问** 的内容，定位为个人本地存档 / 学习 / 无障碍用途。
- 不提供规模化爬取能力，请勿高频批量请求，尊重平台 ToS 与内容版权。
- 产出文件（逐字稿 / 摘要）请勿公开转载。

## 漏洞与凭证泄露报告

如果你发现：

- 脚本在某条路径下**会把 token 写入产出文件或日志**，
- 或任何可能导致凭证泄露的缺陷，

请**不要公开提 issue**，改为通过仓库的私有渠道（GitHub Security Advisory / 维护者邮箱）私下报告，便于在公开前修复。其它一般性 bug 走正常 issue 即可。

## 支持范围

本项目为个人维护的小工具，逆向接口随平台改版可能失效，**风险自负**；安全修复按维护者精力尽力而为，不承诺 SLA。
