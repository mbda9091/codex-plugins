# Codex Hooks

独立开发、测试和打包 Codex Python Hooks 的工程。采用脚本型 Plugin，不构建 wheel，也不添加安装式 CLI 入口。所有运行时 Hook 都使用 Python 标准库，测试统一使用 pytest。

## 环境

开发解释器固定为 Python **3.14.10**，包范围为 `>=3.14,<3.15`。使用 uv 管理开发依赖，提交 `uv.lock`；不要提交 `.venv`。

```sh
uv sync --locked --python 3.14.10
make check
make pack
```

`make check` 执行 Ruff、格式检查、严格 Pyright 和 pytest。`make pack` 输出 `dist/personal-hooks-0.1.0.zip`，只包含运行时 JSON 和 Python 脚本。这个应用不使用 `uv build`。

## 目录

- `plugins/personal-hooks/`：可直接由 Codex 安装的 Plugin，源码由 Git 管理。
- `plugins/personal-hooks/hooks/`：事件注册与处理脚本。
- `tests/`：真实子进程协议测试及归档后运行测试。
- `fixtures/`：模拟事件，测试命令只把内容当作数据。
- `scripts/build_plugin.py`：发布文件白名单与可复现 ZIP 归档。
- `.agents/plugins/marketplace.json`：本仓库的本地安装目录。

当前只有一个无副作用的 `SessionStart` 示例：向 Codex 返回固定的开发提示，不读取项目文件，不写数据，不访问网络。生产 Hook 尚未迁入。

## 添加 Hook

1. 在 `plugins/personal-hooks/hooks/` 添加独立 Python 脚本。
2. 在同目录 `hooks.json` 注册事件，使用 `${PLUGIN_ROOT}` 定位脚本。
3. 在 `tests/` 增加允许、拒绝、故障及适用的路径测试。
4. 执行 `make check` 与 `make pack`。

构建器收集 `plugin.json` 和 `hooks/` 下的 `.json`、`.py` 文件。如果引入其他资源类型，需要扩展构建白名单与归档测试。运行时只使用 Python 标准库，开发依赖放在根目录 dev group；Codex 不会自动执行 `uv sync`。

## 手工验证示例

```sh
uv run python plugins/personal-hooks/hooks/session_start.py < fixtures/session-start.json
```

协议测试从不同 cwd 启动脚本，并验证 JSON、stderr、退出码和打包后带空格路径。它们没有启动真实 Codex 会话，也不会修改 `~/.codex`、安装插件或授予 Hook 信任。

## 可选：安装到 Codex

环境搭建不会自动执行下面的安装命令。需要体验示例时，再自行执行：

```sh
codex plugin marketplace add /Users/zmceadmk/Code/codex-hooks
codex plugin add personal-hooks@codex-hooks-local
```

新建 Codex 会话，通过 `/hooks` 检查并审查信任。插件缓存是安装副本，修改仓库脚本后需要更新安装副本并重新审查变化。避免将同一脚本同时注册在用户 `hooks.json` 和 Plugin 中，以免重复执行。

`hooks.json` 使用 `python3.14` 执行脚本。Codex 启动环境必须能解析对应命令；开发项目的 `.venv` 不会自动成为 Hook 解释器。示例命令面向 macOS/Linux。其他电脑或容器需要独立安装 Python 3.14 并确认 PATH，不能复用本机 `.venv`。

多机分发时将仓库推送到自己的 Git 服务，再用固定 Git ref 添加 marketplace。ZIP 仅作为独立发布产物，不要求通过 ZIP 安装。

## Git 与边界

源码、测试、清单、版本 pin 和 `uv.lock` 进入 Git。凭据、会话数据、日志、缓存、虚拟环境和构建产物不进入 Git 或归档。本工程不修改已有用户级 Hook 注册。容器端应保持普通用户和已有隔离边界，不引入 privileged、host network、Docker socket 或宿主机 SSH agent。

官方参考：[Hook 协议](https://learn.chatgpt.com/docs/hooks)、[Plugin 打包](https://developers.openai.com/plugins/build/plugins)。
