# 临时日志重定向审批

该 Hook 从 `dshplugins/codex-plugins/tmp-redirect-approval` 迁入，保留独立插件名 `tmp-redirect-approval`。运行脚本和测试均已改写为 Python，运行时只依赖标准库，沿用原审批规则。脚本位于 `plugins/tmp-redirect-approval/hooks/permission_request.py`，事件注册位于同目录的 `hooks.json`。

## 审批规则

只处理 `PermissionRequest` 的 `Bash` 工具事件。`cwd` 必须为绝对路径；指定了 `permission_mode` 时，只接受 `default` 或 `acceptEdits`。

只有下列条件全部满足才返回 `allow`，否则返回空决定，继续原审批流程：

- Bash 的单条字面量命令，尾部带 `>`、`>>`、`1>`、`2>` 输出重定向。stdout 重定向后可附带 `2>&1`。
- 所有文件目标均在 `/tmp/` 或 macOS `/private/tmp/`，父目录必须存在。软链接解析后的最终目标仍须在临时目录内；拒绝悬空软链接、路径穿越、目录和设备文件。已有普通文件允许有多个硬链接。
- 临时目录是重定向目标的白名单，不要求原始 argv 预先命中 `allow` 规则。用户规则、`/etc/codex/rules` 和 cwd 祖先目录的 `.codex/rules` 中，原始 argv 或原 shell 调用命中 `forbidden` 时不批准；`prompt` 不阻止此目录白名单。
- 规则文件通过 `codex execpolicy check` 检查，不自行解释。存在规则但检查失败、超时或 CLI 不可用时返回空决定；没有规则文件时无需调用 CLI。

可识别的命令示例：

```sh
./preview.sh --force > /tmp/preview.log 2>&1
./preview.sh --force >> "/tmp/preview log.txt" 2>/tmp/preview.err
```

管道、命令串、变量或命令展开、输入重定向、环境变量前缀、shell 包装和无法判断的语法均继续原审批流程。

Hook 不执行候选命令，不打开重定向目标写入，不改写命令或规则。路径检查与 shell 后续打开文件之间仍有时间间隔；此审批规则不能替代 OS sandbox，也不能还原未落盘的管理策略。其他 Hook 的 deny 仍由 Codex 优先处理。

## 开发验证

```sh
make check
```

`make check` 使用 pytest 覆盖命令语法、临时路径与链接、真实 `execpolicy` 规则、异常回退和 stdin/stdout 协议。插件注册测试验证 marketplace 指向有效插件，并从带空格的源码副本路径启动已注册的 Hook。

子进程协议测试使用临时 cwd 和 `CODEX_HOME`，验证候选命令与重定向均不执行。测试不启动真实 Codex 会话，不安装或启用插件，不改用户 hook 注册，也不授予信任。

## 安装切换边界

本次只迁入源码、事件注册、测试和 marketplace 配置，旧仓库及本机已安装的插件副本保持不动。

后续切换到 `tmp-redirect-approval@mbda9091-codex-plugins` 时，应停用旧的 `tmp-redirect-approval@dshplugins-codex-local`，避免重复注册同一审批功能。安装和信任由用户单独操作，入口见根目录 README。
