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

工具会自动识别各子项目的编程语言（如 Java、Python），分别驱动底层度量套件，并输出整齐的跨项目概览与 Top 20 高危函数清单。

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
| `--top <n>` | - | 展示高危函数清单的最大数量（默认: 20，`0` 表示全部） | `crap . --top 10` |
| `--src <dir>` | - | 指定源码目录名（默认自动智能探测 `src` 或 `app` 等） | `crap . --src app` |
| `--changed` | - | 仅分析版本控制（Git）中发生变更的代码文件 | `crap . --changed` |
| `--exclude <pattern>` | - | 排除包含指定模式的路径（可多次指定） | `crap . --exclude tests --exclude dist` |
| `--lang <name>` | - | 强制指定语言适配器（如 `python`, `java`），跳过自动探测 | `crap . --lang python` |
| `--recursive` | `-r` | 递归扫描目录下的所有深层子项目 | `crap . -r` |
| `--timeout <sec>` | - | 单个项目分析超时时间（秒，默认: 300） | `crap . --timeout 120` |

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
