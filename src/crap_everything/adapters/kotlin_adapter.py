from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from crap_everything.adapters.base import AnalysisOptions, BaseAdapter
from crap_everything.models import ProjectReport, UnifiedCrapEntry
from crap_everything.kotlin_complexity import SourceFunction, extract_kotlin_functions


JACOCO_VERSION = "0.8.15"
_IGNORED_DIRS = {
    "build", "target", "out", "dist", "node_modules", "__pycache__",
    "test", "tests", "testFixtures", "androidTest", "commonTest", "jvmTest",
}
_BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")

# Temporary initialization script: enable JaCoCo without editing the target build.
# Reports and execution data go to a fresh directory to avoid stale coverage.
_GRADLE_INIT = """
import groovy.json.JsonOutput

def outputDir = new File(__OUTPUT_DIR__)
gradle.beforeProject { p ->
    p.plugins.withId('java') {
        if (!p.plugins.hasPlugin('jacoco')) {
            p.pluginManager.apply('jacoco')
            p.jacoco.toolVersion = '__JACOCO_VERSION__'
        }
    }
}
gradle.projectsEvaluated {
    def reportManifest = []
    def reportTasks = []
    gradle.rootProject.allprojects.eachWithIndex { p, index ->
        if (p.plugins.hasPlugin('java') && p.plugins.hasPlugin('jacoco')) {
            def testTask = p.tasks.named('test')
            def reportTask = p.tasks.named('jacocoTestReport')
            testTask.configure {
                jacoco.destinationFile = new File(outputDir, "${index}.exec")
                // With no test sources, an empty execution file reports all code as missed.
                jacoco.destinationFile.createNewFile()
            }
            def xmlFile = new File(outputDir, "${index}.xml")
            reportTask.configure {
                dependsOn(testTask)
                reports.xml.required.set(true)
                reports.xml.outputLocation.set(xmlFile)
            }
            reportManifest.add([project: p.projectDir.absolutePath, report: xmlFile.absolutePath])
            reportTasks.add(reportTask)
        }
    }
    new File(outputDir, 'reports.json').text = JsonOutput.toJson(reportManifest)
    gradle.rootProject.tasks.register('crapEverythingCoverage') {
        dependsOn(reportTasks)
    }
}
"""

class KotlinAdapter(BaseAdapter):
    language = "kotlin"
    display_name = "Kotlin (JVM)"

    def owns_subprojects(self, project_path: Path) -> bool:
        if any((project_path / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
            return True
        pom = project_path / "pom.xml"
        if pom.is_file():
            try:
                return any(node.tag.rsplit('}', 1)[-1] == "modules" for node in ET.parse(pom).getroot())
            except ET.ParseError:
                return False
        return False

    def detect(self, project_path: Path) -> bool:
        # A Kotlin Gradle build script alone does not make a Kotlin project.
        if not any((project_path / name).is_file() for name in _BUILD_FILES):
            if not (project_path / "src").is_dir():
                return False
        return any(path.suffix == ".kt" for path in self._source_files(project_path))

    @staticmethod
    def _source_files(root: Path) -> list[Path]:
        files = []
        for directory, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS and not d.startswith('.')]
            files.extend(
                Path(directory) / name for name in names
                if Path(name).suffix in (".kt", ".java")
            )
        return sorted(files)

    @staticmethod
    def _build_root(project: Path) -> Path:
        # Modules often share the wrapper and settings with an ancestor build.
        if (project / "pom.xml").is_file():
            root = project
            while (root.parent / "pom.xml").is_file():
                root = root.parent
            return root
        for candidate in (project, *project.parents):
            if any((candidate / name).is_file() for name in ("settings.gradle", "settings.gradle.kts")):
                return candidate
        return project

    @staticmethod
    def _executable(root: Path, tool: str) -> str:
        wrapper = root / (("gradlew.bat" if tool == "gradle" else "mvnw.cmd")
                          if os.name == "nt" else ("gradlew" if tool == "gradle" else "mvnw"))
        if wrapper.is_file():
            return str(wrapper)
        executable = shutil.which(tool)
        if not executable:
            raise RuntimeError(f"未找到 {tool} 或项目 Wrapper，请安装构建工具或提供 Wrapper")
        return executable

    @staticmethod
    def _invoke(cmd: list[str], root: Path, deadline: float) -> subprocess.CompletedProcess:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(cmd, 0)
        result = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=remaining,
        )
        if result.returncode:
            detail = (result.stderr.strip() + "\n" + result.stdout.strip()).strip()
            raise RuntimeError(f"构建或测试失败 (exit code {result.returncode}):\n{detail}")
        return result

    def _coverage_reports(self, root: Path, output: Path, deadline: float) -> list[tuple[Path, Path]]:
        if any((root / name).is_file() for name in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")):
            script = output / "coverage.init.gradle"
            script.write_text(
                _GRADLE_INIT.replace("__OUTPUT_DIR__", json.dumps(output.as_posix()))
                .replace("__JACOCO_VERSION__", JACOCO_VERSION), encoding="utf-8",
            )
            command = [
                self._executable(root, "gradle"), "--console=plain",
                "--no-configuration-cache", "--init-script", str(script),
            ]
            command.extend(["--rerun-tasks", "crapEverythingCoverage"])
            self._invoke(command, root, deadline)
            manifest = output / "reports.json"
            if not manifest.is_file():
                raise RuntimeError("Gradle 未生成 JaCoCo 报告清单")
            items = json.loads(manifest.read_text(encoding="utf-8"))
            return [(Path(item["project"]), Path(item["report"])) for item in items]

        if (root / "pom.xml").is_file():
            # One fresh execution file can collect all modules in the sequential reactor.
            # Only XML files rewritten by this invocation are read.
            existing = {p: p.stat().st_mtime_ns for p in root.glob("**/target/site/jacoco/jacoco.xml")}
            data = output / "coverage.exec"
            data.touch()
            plugin = f"org.jacoco:jacoco-maven-plugin:{JACOCO_VERSION}"
            command = [
                self._executable(root, "mvn"), "-B", "-q",
                f"-Djacoco.destFile={data}", f"-Djacoco.dataFile={data}", "-Djacoco.append=true",
            ]
            command.extend([f"{plugin}:prepare-agent", "test", f"{plugin}:report"])
            self._invoke(command, root, deadline)
            return [(p.parents[3], p) for p in root.glob("**/target/site/jacoco/jacoco.xml")
                    if p.stat().st_mtime_ns != existing.get(p)]
        raise RuntimeError("Kotlin JVM 分析需要 Gradle 或 Maven 项目")

    def _changed_files(self, project: Path, deadline: float) -> set[Path]:
        root = Path(self._invoke(["git", "rev-parse", "--show-toplevel"], project, deadline).stdout.strip())
        changed = set()
        for args in (
            ["diff", "--name-only", "--diff-filter=ACMR", "-z"],
            ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
            ["ls-files", "--others", "--exclude-standard", "-z"],
        ):
            output = self._invoke(["git", *args], root, deadline).stdout
            changed.update((root / name).resolve() for name in output.split('\0') if name)
        return changed

    @staticmethod
    def _apply_coverage(
        module: Path, report: Path, functions: list[SourceFunction], entries: list[UnifiedCrapEntry],
    ) -> None:
        """把 JaCoCo 源文件行级指令数据映射到源码函数范围，不读取字节码复杂度。"""
        coverage = {}
        for package in ET.parse(report).getroot().iter("package"):
            for sourcefile in package.findall("sourcefile"):
                key = (package.get("name", ""), sourcefile.get("name", ""))
                coverage[key] = {
                    int(line.get("nr", "0")): (int(line.get("mi", "0")), int(line.get("ci", "0")))
                    for line in sourcefile.findall("line")
                }
        for function, entry in zip(functions, entries):
            if not function.source.is_relative_to(module):
                continue
            # 根模块的报告不能误匹配子模块同包同名源码。
            if any(any((parent / name).is_file() for name in _BUILD_FILES)
                   for parent in function.source.parents
                   if parent != module and parent.is_relative_to(module)):
                continue
            lines = coverage.get((function.package.replace('.', '/'), function.source.name))
            if lines is None:
                continue
            missed = covered = 0
            for number, (mi, ci) in lines.items():
                if function.body_start_line <= number <= function.end_line:
                    missed += mi
                    covered += ci
            if missed + covered:
                entry.coverage = 100.0 * covered / (missed + covered)
                entry.crap = entry.complexity ** 2 * (1 - entry.coverage / 100) ** 3 + entry.complexity

    def run(self, project_path: Path, options: AnalysisOptions) -> ProjectReport:
        project = project_path.resolve()
        started = time.perf_counter()
        deadline = started + options.timeout
        result = ProjectReport(project.name, str(project), self.language)
        try:
            source_root = (project / options.src_dir).resolve() if options.src_dir else project
            if not source_root.is_dir() or not source_root.is_relative_to(project):
                raise RuntimeError(f"源码目录不存在或不在项目内: {source_root}")
            sources = self._source_files(source_root)
            sources = [p for p in sources
                       if not any(pattern in p.relative_to(project).as_posix() for pattern in options.excludes)
                       and (not options.filters or any(pattern in p.relative_to(project).as_posix() for pattern in options.filters))]
            if options.changed_only:
                changed = self._changed_files(project, deadline)
                sources = [p for p in sources if p.resolve() in changed]
            if not sources:
                return result
            functions = extract_kotlin_functions([p for p in sources if p.suffix == '.kt'], deadline)
            from crap_everything.source_complexity import java_source_functions
            functions.extend(java_source_functions(project, [p for p in sources if p.suffix == '.java'], deadline))
            result.entries = [UnifiedCrapEntry(
                project.name, "kotlin" if function.source.suffix == '.kt' else "java",
                function.symbol, f"{function.source.relative_to(project).as_posix()}:{function.start_line}",
                function.complexity, None, None,
            ) for function in functions]
            if not result.entries:
                return result
            if not options.complexity_only:
                root = self._build_root(project)
                with tempfile.TemporaryDirectory(prefix="crap-kotlin-") as directory:
                    reports = self._coverage_reports(root, Path(directory), deadline)
                    available = [(module, report) for module, report in reports if report.is_file()]
                    if not available:
                        raise RuntimeError("未生成 JaCoCo XML；请确认 JVM 测试与覆盖率代理配置，Android、JS、Native 暂不支持")
                    for module, report in available:
                        self._apply_coverage(module, report, functions, result.entries)
                    if all(e.coverage is None for e in result.entries):
                        raise RuntimeError("JaCoCo 报告中没有匹配的源码行，请检查编译配置和 debug 信息")
            if options.complexity_only:
                for entry in result.entries:
                    entry.coverage = None
                    entry.crap = None
                result.entries.sort(key=lambda e: -e.complexity)
            else:
                result.entries.sort(key=lambda e: (e.crap is None, -(e.crap or 0)))
            if any(
                (options.fail_on_crap is not None and e.crap is not None and e.crap >= options.fail_on_crap)
                or (options.fail_on_complexity is not None and e.complexity >= options.fail_on_complexity)
                or (options.fail_on_coverage_below is not None and e.coverage is not None and e.coverage < options.fail_on_coverage_below)
                for e in result.entries
            ):
                result.exit_code = 2
        except subprocess.TimeoutExpired:
            result.exit_code = 1
            result.error_message = f"Kotlin 分析超时 ({options.timeout}s)"
        except (OSError, ValueError, RuntimeError, ET.ParseError) as ex:
            result.exit_code = 1
            result.error_message = str(ex)
        finally:
            result.elapsed_seconds = time.perf_counter() - started
        return result
