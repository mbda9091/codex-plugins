# Codex Plugins

独立开发、测试和打包 Codex Python Hooks 的工程。Plugin 名称由用户明确指定，可以包含一个或多个 Hook，不从 Hook 名称自动推导。所有运行时 Hook 都使用 Python 标准库，测试统一使用 pytest。不构建 wheel，也不添加安装式 CLI 入口。

## 环境

开发解释器固定为 Python **3.14.10**，包范围为 `>=3.14,<3.15`。使用 uv 管理开发依赖，提交 `uv.lock`；不要提交 `.venv`。

```sh
uv sync --locked --python 3.14.10
make check
make pack PLUGIN=tmp-redirect-approval
```

开发和测试还需要 PATH 中的 `codex`。规则测试调用 `codex execpolicy check` 检查临时规则，不启动 Codex 会话。

`make check` 执行 Ruff、格式检查、严格 Pyright 和 pytest。打包必须通过 `PLUGIN` 指定插件，不设默认值；上例输出 `dist/tmp-redirect-approval-0.1.0.zip`，只包含该插件的运行时 JSON 和 Python 脚本。这个应用不使用 `uv build`。

## 目录

- `plugins/<plugin-name>/`：使用用户指定名称的 Plugin，源码由 Git 管理。
- `plugins/tmp-redirect-approval/hooks/`：临时日志重定向审批的事件注册与处理脚本。
- `tests/<plugin-name>/`：按插件源码目录组织规则测试、真实子进程协议测试及归档后运行测试。
- `tests/` 顶层：仅放仓库级工具与环境测试，例如打包命令必须显式指定插件。
- `scripts/build_plugin.py`：发布文件白名单与可复现 ZIP 归档。
- `.agents/plugins/marketplace.json`：本仓库的本地安装目录。

当前插件：

| 插件 | 事件 | 用途 |
| --- | --- | --- |
| `tmp-redirect-approval` | `PermissionRequest`，匹配 `Bash` | 核对 `/tmp` 输出重定向，符合规则时返回批准 |

临时日志重定向审批从原仓库迁入并改写为 Python，保留插件名 `tmp-redirect-approval` 和原审批规则。详见[规则与迁移说明](docs/tmp-redirect-approval.md)。现有 `dynamic-agents.py` 等生产 Hook 尚未迁入。

## 添加 Hook

1. 由用户指定 Plugin 名称；新插件创建 `plugins/<plugin-name>/`，在 `plugin.json` 中使用相同的 `name`。也可以向已有插件增加 Hook。
2. 在其 `hooks/` 下添加 Python 脚本和 `hooks.json`，使用 `${PLUGIN_ROOT}` 定位脚本。
3. 在 `.agents/plugins/marketplace.json` 中登记同名插件及其目录。
4. 在 `tests/<plugin-name>/` 按源码目录增加允许、拒绝、故障及适用的路径测试，测试样本跟随所属测试存放。
5. 执行 `make check` 与 `make pack PLUGIN=<plugin-name>`。

构建器收集 `plugin.json` 和 `hooks/` 下的 `.json`、`.py` 文件。如果引入其他资源类型，需要扩展构建白名单与归档测试。运行时只使用 Python 标准库，开发依赖放在根目录 dev group；Codex 不会自动执行 `uv sync`。

## 测试验证

协议测试从不同 cwd 启动脚本，并验证 JSON、stderr、退出码和打包后带空格路径。审批测试还验证候选命令和重定向均不执行。它们没有启动真实 Codex 会话，也不会修改 `~/.codex`、安装插件或授予 Hook 信任。

## 可选：安装到 Codex

开发、测试和打包不会自动安装插件。需要使用临时重定向审批时，再自行执行：

```sh
codex plugin marketplace add /Users/zmceadmk/Code/codex-plugins
codex plugin add tmp-redirect-approval@codex-plugins-local
```

新建 Codex 会话，通过 `/hooks` 检查并审查信任。插件缓存是安装副本，修改仓库脚本后需要更新安装副本并重新审查变化。若已启用旧的 `tmp-redirect-approval@dshplugins-codex-local`，在切换时停用旧来源的插件，避免重复注册。本次源码迁移不执行安装或切换。

所有 Hook 使用 `python3.14`；`PermissionRequest` 有规则文件时还调用 `codex execpolicy check`。Codex 启动环境必须能解析对应命令；开发项目的 `.venv` 不会自动成为 Hook 解释器。示例命令面向 macOS/Linux。其他电脑或容器需要独立安装 Python 3.14 并确认 PATH，不能复用本机 `.venv`。

多机分发时将仓库推送到自己的 Git 服务，再用固定 Git ref 添加 marketplace。ZIP 仅作为独立发布产物，不要求通过 ZIP 安装。

## Git 与边界

源码、测试、清单、版本 pin 和 `uv.lock` 进入 Git。凭据、会话数据、日志、缓存、虚拟环境和构建产物不进入 Git 或归档。本工程不修改已有用户级 Hook 注册。容器端应保持普通用户和已有隔离边界，不引入 privileged、host network、Docker socket 或宿主机 SSH agent。

官方参考：[Hook 协议](https://learn.chatgpt.com/docs/hooks)、[Plugin 打包](https://developers.openai.com/plugins/build/plugins)。
