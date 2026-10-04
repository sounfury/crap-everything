# crap-everything

跨语言、多项目的 **CRAP** (Change Risk Anti-Pattern) 代码质量与变更风险统一门面度量工具。

通过抽象层与插件式适配器架构，将不同语言底层的圈复杂度分析工具与测试覆盖率工具（如针对 Java 的 `crap4java`、针对 Python 的 `crap4py`）统一汇聚，支持**单命令同时扫描分析多个项目**，并输出统一的汇总表格、全局风险函数排行及 CI/CD 质量门禁状态。

---

## 安装方式

### 方式一：使用 uv tool 全局安装（推荐）

在本项目根目录下执行：

```bash
uv tool install .
```

安装完成后，即可在系统的**任何终端与任意目录**直接使用 `crap` 或 `crap-everything` 命令：

```bash
crap --version
```

> **更新或重新安装**：
> ```bash
> uv tool install --force .
> ```

---

### 方式二：使用 pip 安装

在 Python 虚拟环境或全局环境下执行：

```bash
# 标准安装
pip install .

# 或开发者可编辑模式 (Editable)
pip install -e .
```

---

### 方式三：使用 uv 免安装直接运行

在本项目仓库目录下，无需预先全局安装：

```bash
uv run crap [参数...]
```

---

## 快速上手

### 1. 自动分析当前工作区的所有子项目

在包含多个语言项目的目录（如 monorepo 或工作区根目录）下：

```bash
crap .
```

工具会自动识别各子项目的编程语言（Java、Python、Kotlin JVM），分别驱动底层度量套件，并输出整齐的跨项目概览与 Top 20 高危函数清单。

---

### 2. 分析任意单一项目（本地或外部绝对路径）

支持直接传入外部项目路径，工具会自动推断源码目录与虚拟环境：

```bash
crap D:\projects\ZhiYing\backend
```

---

### 3. 显式指定多个项目同时运行

```bash
crap ./crap4java ./crap4py /path/to/another_project
```

---

## 常用命令行参数

| 参数 | 缩写 | 说明 | 示例 |
|---|:---:|---|---|
| `paths` | - | 待分析的项目路径列表（默认：当前目录 `.`） | `crap ./service-a ./service-b` |
| `--fail-on-crap <n>` | - | 统一门禁：若任意函数 CRAP >= n，退出码返回 `2` | `crap . --fail-on-crap 30` |
| `--fail-on-complexity <n>` | - | 门禁：若任意函数圈复杂度 >= n 则标记超标 | `crap . --fail-on-complexity 15` |
| `--fail-on-coverage-below <n>` | - | 门禁：若任意函数测试覆盖率低于 n% 则标记超标 | `crap . --fail-on-coverage-below 70` |
| `--output <format>` | `-o` | 输出格式：`text` (默认), `json`, `markdown`, `csv` | `crap . -o markdown` |
| `--json` | - | 快捷输出完整 JSON 结构化数据 | `crap . --json` |
| `--markdown` | - | 快捷输出 Markdown 报告（适合嵌入 PR / CI 构建报告） | `crap . --markdown` |
| `--report <file>` | - | 同时将 JSON 报告导出到文件；不指定时不写任何文件 | `crap complexity . --report build/crap.json` |
| `--top <n>` | - | 展示高危函数清单的最大数量（默认: 20，`0` 表示全部） | `crap . --top 10` |
| `--src <dir>` | - | 指定源码目录名（默认自动智能探测 `src` 或 `app` 等） | `crap . --src app` |
| `--changed` | - | 仅分析版本控制（Git）中发生变更的代码文件 | `crap . --changed` |
| `--exclude <pattern>` | - | 排除包含指定模式的路径（可多次指定） | `crap . --exclude tests --exclude dist` |
| `--lang <name>` | - | 强制指定语言适配器（`python`, `java`, `kotlin`） | `crap . --lang kotlin` |
| `--recursive` | `-r` | 递归扫描目录下的所有深层子项目 | `crap . -r` |
| `--timeout <sec>` | - | 单个项目分析超时时间（秒，默认: 300） | `crap . --timeout 120` |

---

## 只看复杂度

使用独立子命令 `crap complexity`，不运行测试、不读取已有覆盖率，也不计算 CRAP：

```bash
crap complexity D:\projects\ZhiYing\zhiying_backend --top 10
crap complexity . --json
crap complexity . --fail-on-complexity 10 --markdown
crap complexity . --changed --exclude generated
```

支持 Java、Python 和 Kotlin JVM，结果按复杂度从高到低排列。
JSON 中每个函数除 `location`（`相对路径:行号`）外，还提供拆开的 `file`（相对 `project_path`）和 `line`，便于 arch-view 等工具按文件对应。
Java 使用已有 Java 语法树解析器，Python 使用与 CRAP 相同口径的 AST 决策点计数，均无需运行或编译目标项目。
Kotlin 使用 Tree-sitter 解析源码语法树，无需 JDK、Gradle/Maven、生产代码依赖或编译产物；不编译或运行目标项目。

`--fail-on-complexity N` 对全部方法判断，任何方法 CC >= N 时退出码为 `2`；`--top` 仅限制文本/Markdown 展示条数。
该子命令支持 `--lang`、`--src`、`--exclude`、`--changed`、`--timeout` 和所有输出格式；不接受 `--fail-on-crap` 或 `--fail-on-coverage-below`。

---

## Kotlin JVM 支持

支持 Gradle（Groovy/Kotlin DSL）和 Maven 的 Kotlin JVM 项目，优先使用项目自带的 Wrapper：

```bash
crap /path/to/kotlin-project --lang kotlin
crap /path/to/kotlin-project --lang kotlin --json --fail-on-crap 30
crap /path/to/kotlin-project --lang kotlin --changed --exclude generated
```

包含生产 `.kt` 源码的项目会自动选用 Kotlin 适配器；仅使用 `build.gradle.kts` 的 Java 项目仍归类为 Java。
Java/Kotlin 混合项目会同时报告两种语言的方法，并为每个条目标注语言、源文件和行号。Kotlin 函数名包含源码参数类型，用于区分重载。

分析会重新运行 JVM `test` 测试。Gradle 通过临时初始化脚本启用 JaCoCo XML，不需要修改项目构建文件；多模块项目使用共享的根构建和 Wrapper。
没有测试源码的模块仍会分析源码函数，覆盖率计为 0%，不会复用旧覆盖率数据。
Maven 项目需已配置 Kotlin 编译和测试，通过 JaCoCo Maven 插件生成 `target/site/jacoco/jacoco.xml`；自定义报告输出目录暂不支持。

Kotlin 复杂度采用源码 AST 决策点计数：基础值 1，`if`、每个非 `else` 的 `when` 分支、循环、`catch`、`&&`、`||`、`?:` 各加 1。
`when` 同一分支的多个匹配值只计一次；安全调用、类型转换和普通集合/作用域函数调用不额外加分。
lambda 中的显式分支计入外层；局部函数单独报告，其分支不重复计入外层。
仅报告有源码函数体的函数、显式属性访问器、`init` 块和次构造器，不报告编译器生成的 getter、数据类方法、隐式构造器等。
纯复杂度和 CRAP 命令共用上述口径，不会计入集合函数内联生成的字节码分支。

CRAP 的覆盖率仍来自 JaCoCo：将源码函数体行范围内 `<sourcefile>` 的已覆盖/未覆盖指令数汇总，计算指令覆盖率，再与源码复杂度结合。
此映射按源码行归属；同一行包含多个函数体时覆盖率可能共享，外层函数范围内的局部函数也可能影响外层覆盖率。
未匹配到可执行源码行的声明显示 `N/A`。
Gradle 新启用的 JaCoCo 和 Maven 插件使用 0.8.15；已有 Gradle JaCoCo 配置保留项目指定的版本。
当前支持标准 Kotlin JVM 项目，Android、Kotlin Multiplatform、JS、Native 和独立 `.kts` 脚本暂不支持。

开发验收（需要真实 JVM 项目、JDK 和项目构建工具）：

```powershell
$env:CRAP_KOTLIN_ACCEPTANCE_PROJECT = 'D:\projects\ZhiYing\zhiying_backend'
uv run --extra dev pytest tests/acceptance
```

---

## 项目配置与 Git 提交门禁

快速启用步骤见 [Git 提交门禁简明说明](docs/git-gate.md)。

在项目目录创建并提交 `crap.toml`：

```toml
[project]
language = "kotlin" # java / python / kotlin；省略时自动识别
# src = "src"      # 可选，按语言自动推断；多模块 Kotlin 默认扫描项目
exclude = ["generated"]
timeout = 300

[gate]
mode = "complexity" # 仅源码分析，无需编译或运行测试
max_complexity = 12  # 12 通过，13 拦截
```

也可以自动生成配置，然后安装 Git `pre-commit` 钩子：

```powershell
cd D:\projects\ZhiYing\zhiying_backend
crap init --lang kotlin --max-complexity 12
crap check                    # 按配置检查当前工作区
crap hook install
git add crap.toml CRAP_GUIDE.md # 配置、提示文档需与源码一起提交
crap check --staged           # 手动检查即将提交的完整内容
```

`crap init` 默认使用纯复杂度模式，上限为 12，不覆盖已有配置。
`crap hook install` 会在目标项目创建 `CRAP_GUIDE.md`，包含 Java/Python/Kotlin 计分规则、算分示例和修改建议；重复安装保留已有文档。门禁失败时会输出文档位置与复查步骤，JSON 的 `gate.help` 也包含这些提示。
`crap check` 才会读取项目配置；原有 `crap` / `crap complexity` 参数语义保持一致，`--fail-on-complexity N` 仍表示 CC >= N 拦截。
配置不允许未知字段，也不能缺少所有阈值。分析失败、无可分析项目/函数、受约束指标为 N/A 均拒绝放行。
退出码：通过为 `0`，分析/配置错误为 `1`，指标超标为 `2`；`crap check --json` 额外输出 `gate` 的错误和违规明细。

若需要结合覆盖率检查 CRAP，将 `[gate]` 改成：

```toml
[gate]
mode = "crap"       # 会编译并运行测试，需要项目测试依赖和构建环境
max_complexity = 12 # 每项可选，但至少保留一个阈值
max_crap = 30       # CRAP <= 30 通过
min_coverage = 80   # 每个函数覆盖率 >= 80% 通过
```

钩子检查暂存区的完整项目快照，配置文件也取暂存版本；未暂存的修改不影响判定。
快照不包含未跟踪/忽略的依赖、虚拟环境和本地配置；CRAP 模式需要其测试环境能独立运行，提交前优先使用纯复杂度模式。
分析使用临时目录，不 stash、不修改原工作区或 index。所有快照内的生产函数都检查，而非仅检查变更行。
钩子仅在该项目有暂存变更时执行，其他目录的提交不受影响；可用 `crap check --staged --if-changed` 手动复现这一行为。
项目可位于 Git 仓库的子目录；安装时自动找到仓库根和实际钩子目录，支持 `core.hooksPath` 和 worktree。
已有其他 `pre-commit` 钩子时拒绝覆盖，可在现有钩子中接入 `crap check --staged /项目路径`，并向 Git 返回检查的非零退出码。
工具必须在提交进程的 PATH 上可用；缺少 `crap` 时拒绝提交。每个克隆需单独安装钩子。
本地钩子可通过 Git 的 `--no-verify` 绕过；团队需要强制执行时，在 CI 中同样运行 `crap check`，再配合受保护分支。

---

## CI/CD 集成与退出码规范

在持续集成自动化流水线中，通过检查退出码实现质量门禁拦截：

| 退出码 | 含义 |
|:---:|---|
| **`0`** | **PASSED**：所有项目分析完成，且没有函数触发失败阈值 |
| **`1`** | **ERROR**：执行异常、依赖工具缺失或参数错误 |
| **`2`** | **VIOLATION**：质量超标，至少有一个函数的 CRAP 分数达到或超过 `--fail-on-crap` |

**GitHub Actions 示例**：

```yaml
- name: Run CRAP Quality Gate
  run: |
    crap . --fail-on-crap 30 --markdown >> $GITHUB_STEP_SUMMARY
```

---

## 扩展新语言适配器

项目采用插件式驱动架构（Adapter Pattern）。如需接入新语言（例如 Go、Rust、TypeScript）：

1. 继承 `crap_everything.adapters.base.BaseAdapter`；
2. 实现 `detect(project_path: Path) -> bool`（项目类型探测）与 `run(project_path: Path, options: AnalysisOptions) -> ProjectReport`；
3. 在 `crap_everything.adapters.__init__.py` 中调用 `get_global_registry().register(...)` 注册。

上层的扫描调度、多项目聚合、输出格式化与质量门禁均会自动无缝兼容新语言。
