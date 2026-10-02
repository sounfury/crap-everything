# 启用 Git 提交门禁

在项目提交前自动检查源码复杂度，最高允许 12：12 通过，13 拦截。纯复杂度模式不编译、不运行测试。

## 1. 安装工具

```powershell
uv tool install --force D:\code-tools\crap
```

## 2. 在目标项目启用

```powershell
cd D:\projects\ZhiYing\zhiying_backend
crap init --lang kotlin --max-complexity 12
crap check
crap hook install
git add crap.toml CRAP_GUIDE.md
```

语言可选 `kotlin`、`java`、`python`。已存在 `crap.toml` 时跳过 `crap init`，直接编辑配置即可。

安装钩子时会同时创建项目内的 `CRAP_GUIDE.md`，说明各语言的复杂度计分规则、示例和修改建议，无需查看 crap 源码。重新安装不会覆盖已有说明，可自行补充团队规则。

生成的配置核心内容：

```toml
[project]
language = "kotlin"

[gate]
mode = "complexity"
max_complexity = 12
```

## 3. 正常提交

将本次要提交的源码加入暂存区后，可先手动检查：

```powershell
crap check --staged
```

之后照常执行 `git commit`，钩子会自动检查；超标或分析失败时拦截提交。配置修改也需 `git add crap.toml`，门禁使用暂存区中的源码和配置。

被拦截时会显示违规函数、源文件位置、实际分数和阈值，并提示阅读 `CRAP_GUIDE.md`，修改后暂存并再次运行 `crap check --staged`。

`crap check` 检查当前工作区；`crap check --staged` 检查即将提交的完整项目。项目没有暂存变更时，自动钩子会跳过。

每个克隆都需执行一次 `crap hook install`，并确保提交进程能找到 `crap` 命令。已有其他提交钩子时不会覆盖，按提示接入即可。

CRAP、覆盖率阈值等更多配置见 [README](../README.md#项目配置与-git-提交门禁)。
