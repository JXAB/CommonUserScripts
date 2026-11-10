# 项目来源与上游集成策略（核查日期 2026-11-01）

## 用户指定来源

- **JXAB/CommonUserScripts**：https://github.com/JXAB/CommonUserScripts ，Shadowsocks 主集成候选：https://raw.githubusercontent.com/JXAB/CommonUserScripts/main/shadowsocks/install.sh 。仓库存在，不应直接 pipe 到 shell；建议固定发布版本/commit 并校验实际下载的哈希。
- **teddysun/shadowsocks_install**：https://github.com/teddysun/shadowsocks_install ，旧版 Shadowsocks 安装脚本仓库，可作历史参考。老旧部分组件需要安全评估，默认禁用不受维护的方案。
- **idlm/CommonUserScripts**：https://github.com/idlm/CommonUserScripts ，2026-11-01 检查为空仓库，不能依赖其 `dev-env-setup/setupv11.sh`；Android 安装应重新开发。
- **Gabxb/FrequentlyUsedScripts**：https://github.com/Gabxb/FrequentlyUsedScripts ，2026-11-01 请求返回 404，不作为构建依赖；可仅参考用户提出的菜单化需求。

## AI CLI 官方来源

- Codex CLI：https://github.com/openai/codex ，官方 README 提供原生安装器或 npm/Homebrew；具体版本固定在 release lock。
- Claude Code：https://github.com/anthropics/claude-code ，当前 README 推荐原生安装器；npm 安装渠道已标为 deprecated，优先选官方推荐渠道。
- Gemini CLI：https://github.com/google-gemini/gemini-cli ，官方支持 npm/Homebrew 等方式，Node/OS 要求随官方文档更新。
- Grok CLI：https://github.com/xai-org/grok-build ，官方也发布 `@xai-official/grok`；应根据平台区分原生/npm 安装。
- ZCF：https://github.com/UfoMiao/zcf ，`npx zcf` 入口与子命令按当前文档检查。

## API 网关

- CLIProxyAPI：https://github.com/router-for-me/CLIProxyAPI 。独立服务器安装器，用户必须选择认证、绑定地址、持久化目录与服务运行模式。
- Magpie：https://github.com/yetone/magpie 。支持桌面/TUI/Web/CLI、Docker 等模式；应区分本地开发工具与 VPS 上的服务。对外监听须先配置可控认证与网络访问策略。

## 注意

所有上游版本、安装命令、适配平台都可能变化。首次开发和每次 release 必须再核查维护状态。下载地址只是登记数据，不是已审计安全的执行授权。
