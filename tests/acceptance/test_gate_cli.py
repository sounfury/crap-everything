"""以真实 CLI 和 Git 提交验证配置及门禁，不新增单元测试。"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def _env():
    env = dict(os.environ, PYTHONUTF8="1")
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    return env


def _cli(project, *args):
    return subprocess.run([sys.executable, "-m", "crap_everything", *args], cwd=project,
                          env=_env(), capture_output=True, text=True, encoding="utf-8", timeout=30)


def _project(path):
    source = path / "src/main.py"
    source.parent.mkdir(parents=True)
    source.write_text("def classify(value):\n    return 1 if value else 0\n", encoding="utf-8")
    result = _cli(path, "init", "--lang", "python", "--max-complexity", "2")
    assert result.returncode == 0, result.stdout + result.stderr
    return source


def test_config_thresholds_and_validation(tmp_path):
    source = _project(tmp_path)
    result = _cli(tmp_path, "check", "--json")
    report = json.loads(result.stdout)
    assert result.returncode == 0 and report["gate"]["passed"]
    assert report["projects"][0]["entries"][0]["complexity"] == 2
    source.write_text("def classify(value):\n    return 1 if value and value > 0 else 0\n", encoding="utf-8")
    result = _cli(tmp_path, "check", "--json")
    assert result.returncode == 2
    assert "CC 3 > 2" in json.loads(result.stdout)["gate"]["violations"][0]
    assert json.loads(result.stdout)["gate"]["help"]["guide"] == str(tmp_path / "CRAP_GUIDE.md")
    text_result = _cli(tmp_path, "check")
    assert "CRAP_GUIDE.md" in text_result.stdout and "crap check --staged" in text_result.stdout
    config = tmp_path / "crap.toml"
    original = config.read_bytes()
    assert _cli(tmp_path, "init", "--lang", "python").returncode == 1
    assert config.read_bytes() == original
    for text in (
        '[gate]\nmax_complexitty = 12\n',
        '[gate]\nmode = "complexity"\nmax_crap = 12\n',
        '[gate]\nmax_complexity = 1.5\n',
        '[gate]\nmax_crap = nan\n',
        '[gate]\nmode = "complexity"\n',
        'NOT VALID TOML !!!',
    ):
        config.write_text(text, encoding="utf-8")
        result = _cli(tmp_path, "check", "--json")
        assert result.returncode == 1, result.stdout + result.stderr
        assert not json.loads(result.stdout)["gate"]["passed"]
    config.write_bytes(original)
    source.unlink()
    assert _cli(tmp_path, "check").returncode == 1


def test_hook_blocks_commit_of_staged_code_and_preserves_worktree(tmp_path):
    source = _project(tmp_path)
    env = _env()
    # 钩子使用 PATH 上的 crap；验收直接调用当前源码，不依赖全局已安装版本。
    bin_dir = tmp_path / "test-bin"
    bin_dir.mkdir()
    launcher = bin_dir / "crap"
    launcher.write_text(f"#!/bin/sh\nexec {shlex.quote(Path(sys.executable).as_posix())} -m crap_everything \"$@\"\n", encoding="utf-8")
    launcher.chmod(0o755)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)

    for args in (("init",), ("config", "user.name", "Gate acceptance"),
                 ("config", "user.email", "gate@example.invalid"),
                 ("config", "commit.gpgSign", "false"),
                 ("config", "core.hooksPath", ".custom hooks")):
        assert git(*args).returncode == 0
    installed = _cli(tmp_path, "hook", "install")
    assert installed.returncode == 0, installed.stdout + installed.stderr
    hook = tmp_path / ".custom hooks/pre-commit"
    assert hook.is_file() and b"\r\n" not in hook.read_bytes()
    guide = tmp_path / "CRAP_GUIDE.md"
    assert guide.is_file()
    guide_text = guide.read_text(encoding="utf-8")
    assert "### Kotlin" in guide_text and "### Python" in guide_text and "### Java" in guide_text
    assert "CRAP = CC²" in guide_text
    # 团队可补充自己的建议，重复安装保留内容。
    guide.write_text(guide_text + "\n团队补充说明\n", encoding="utf-8")
    preserved = guide.read_bytes()
    assert _cli(tmp_path, "hook", "install").returncode == 0
    assert guide.read_bytes() == preserved
    assert git("add", "src/main.py", "crap.toml").returncode == 0
    commit = git("commit", "-m", "passing gate")
    assert commit.returncode == 0, commit.stdout + commit.stderr
    head = git("rev-parse", "HEAD").stdout
    bad = "def classify(value):\n    return 1 if value and value > 0 else 0\n"
    good = "def classify(value):\n    return 1 if value else 0\n# next commit\n"
    source.write_text(bad, encoding="utf-8")
    assert git("add", "src/main.py").returncode == 0
    source.write_text(good, encoding="utf-8")
    commit = git("commit", "-m", "must be blocked")
    assert commit.returncode != 0 and "CC 3 > 2" in commit.stdout + commit.stderr
    assert "CRAP_GUIDE.md" in commit.stdout + commit.stderr
    assert git("rev-parse", "HEAD").stdout == head
    assert source.read_text(encoding="utf-8") == good
    assert "value and value" in git("show", ":src/main.py").stdout
    assert git("add", "src/main.py").returncode == 0
    source.write_text(bad, encoding="utf-8")
    commit = git("commit", "-m", "only staged good source matters")
    assert commit.returncode == 0, commit.stdout + commit.stderr
    assert source.read_text(encoding="utf-8") == bad

    # 配置也使用暂存区版本，工作区里调低阈值不会改变本次提交判定。
    config = tmp_path / "crap.toml"
    original = config.read_text(encoding="utf-8")
    config.write_text(original.replace("max_complexity = 2", "max_complexity = 3"), encoding="utf-8")
    assert git("add", "crap.toml", "src/main.py").returncode == 0
    config.write_text(original, encoding="utf-8")
    assert _cli(tmp_path, "check", "--staged", "--json").returncode == 0
    assert _cli(tmp_path, "check", "--json").returncode == 2
    assert git("rm", "--cached", "-f", "crap.toml").returncode == 0
    assert _cli(tmp_path, "check", "--staged").returncode == 1

    # 保留已有钩子，用户可手动接入。
    custom = "#!/bin/sh\necho existing hook\n"
    hook.write_text(custom, encoding="utf-8")
    assert _cli(tmp_path, "hook", "install").returncode == 1
    assert hook.read_text(encoding="utf-8") == custom


def test_hook_for_project_inside_parent_repository(tmp_path):
    def git(*args):
        result = subprocess.run(["git", *args], cwd=tmp_path, env=_env(), capture_output=True,
                                text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    git("init")
    project = tmp_path / "backend with spaces"
    project.mkdir()
    _project(project)
    result = _cli(project, "hook", "install")
    assert result.returncode == 0, result.stdout + result.stderr
    hook = tmp_path / ".git/hooks/pre-commit"
    assert "'backend with spaces'" in hook.read_text(encoding="utf-8")
    assert (project / "CRAP_GUIDE.md").is_file()
    assert not (tmp_path / "CRAP_GUIDE.md").exists()
    result = _cli(project, "check", "--staged", "--if-changed", "--json")
    assert result.returncode == 0 and json.loads(result.stdout)["gate"]["skipped"]
    git("add", "backend with spaces")
    result = _cli(project, "check", "--staged", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["projects"][0]["project_name"] == project.name


def test_installed_kotlin_guide_example_can_be_checked(tmp_path):
    source = tmp_path / "src/main/kotlin/Example.kt"
    source.parent.mkdir(parents=True)
    source.write_text("fun initial() = 1\n", encoding="utf-8")
    result = _cli(tmp_path, "init", "--lang", "kotlin", "--max-complexity", "4")
    assert result.returncode == 0, result.stdout + result.stderr
    subprocess.run(["git", "init"], cwd=tmp_path, env=_env(), check=True, capture_output=True)
    result = _cli(tmp_path, "hook", "install")
    assert result.returncode == 0, result.stdout + result.stderr
    guide = (tmp_path / "CRAP_GUIDE.md").read_text(encoding="utf-8")
    example = re.search(r"```kotlin\n(.*?)```", guide, re.DOTALL).group(1)
    source.write_text(example, encoding="utf-8")
    result = _cli(tmp_path, "check", "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["total_methods"] == 1 and report["global_max_complexity"] == 4
    assert "CC = 1 + 1 + 1 + 1 = 4" in guide
