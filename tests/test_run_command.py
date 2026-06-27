from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import run as run_module
from run import Run


def make_runner(tmp_path, tag="3.22.0.3", checkout_ref=None, driver_type="scylla"):
    driver = tmp_path / "driver repo"
    driver.mkdir()
    return Run(
        csharp_driver_git=driver,
        driver_type=driver_type,
        tag=tag,
        tests=["integration"],
        scylla_version="2026.1.3",
        checkout_ref=checkout_ref,
    )


def test_test_command_keeps_filter_as_one_argv_entry(tmp_path):
    runner = make_runner(tmp_path)
    runner.__dict__["ignore_tests"] = {"ignore": ["BadTest; echo unsafe", "OtherTest"], "flaky": []}

    cmd = runner._test_command("integration")

    assert cmd[:3] == [
        "dotnet",
        "test",
        "src/Cassandra.IntegrationTests/Cassandra.IntegrationTests.csproj",
    ]
    assert cmd[cmd.index("--filter") + 1] == (
        "(FullyQualifiedName!~BadTest; echo unsafe & FullyQualifiedName!~OtherTest)"
    )


def test_test_command_omits_filter_when_no_ignores(tmp_path):
    runner = make_runner(tmp_path)
    runner.__dict__["ignore_tests"] = {"ignore": [], "flaky": []}

    assert "--filter" not in runner._test_command("integration")


def test_scylla_v_tag_uses_unprefixed_version_folder_name(tmp_path):
    runner = make_runner(tmp_path, tag="v3.22.0.3")

    assert runner.driver_version == "3.22.0.3"


def test_junit_dir_uses_matrix_repo_root_when_cwd_changes(monkeypatch, tmp_path):
    runner = make_runner(tmp_path, tag="9.9.9.9")

    monkeypatch.chdir(tmp_path)

    assert runner.junit_dir == REPO_ROOT / "test_results" / "9.9.9.9"


def test_run_restores_original_cwd(monkeypatch, tmp_path):
    runner = make_runner(tmp_path, tag="9.9.9.8")
    runner.__dict__["ignore_tests"] = {"ignore": [], "flaky": []}
    monkeypatch.setattr(runner, "_checkout_branch", lambda: False)
    original_cwd = Path.cwd()

    runner.run()

    assert Path.cwd() == original_cwd


def test_scylla_environment_sets_net8_build_target(tmp_path):
    runner = make_runner(tmp_path, driver_type="scylla")

    assert runner.environment["BuildTarget"] == "net8"
    assert runner.environment["SCYLLA_VERSION"] == "release:2026.1.3"


def test_datastax_environment_does_not_set_build_target(tmp_path):
    runner = make_runner(tmp_path, tag="3.22.0", driver_type="datastax")

    assert "BuildTarget" not in runner.environment
    assert runner.environment["SCYLLA_VERSION"] == "release:2026.1.3"


def test_scylla_version_preserves_explicit_ccm_prefix(tmp_path):
    runner = make_runner(tmp_path)
    runner._scylla_version = "unstable/master:2026-06-26"

    assert runner.environment["SCYLLA_VERSION"] == "unstable/master:2026-06-26"


def test_scylla_version_preserves_local_package_version(monkeypatch, tmp_path):
    monkeypatch.setenv("SCYLLA_UNIFIED_PACKAGE", "/tmp/scylla-unified.tar.gz")
    runner = make_runner(tmp_path)

    assert runner.environment["SCYLLA_VERSION"] == "2026.1.3"


def test_ensure_simulacron_download_uses_argv_command(monkeypatch, tmp_path):
    runner = make_runner(tmp_path)
    commands = []

    monkeypatch.setattr(run_module, "__file__", str(tmp_path / "run.py"))
    monkeypatch.setattr(runner, "_run_command", lambda cmd: commands.append([str(arg) for arg in cmd]))

    assert runner.ensure_simulacron("0.12.0") == str(tmp_path / "simulacron-standalone-0.12.0.jar")
    assert commands == [
        [
            "curl",
            "-sL",
            "-o",
            str(tmp_path / "simulacron-standalone-0.12.0.jar"),
            "https://github.com/datastax/simulacron/releases/download/0.12.0/simulacron-standalone-0.12.0.jar",
        ]
    ]


def test_run_command_invokes_subprocess_without_shell(monkeypatch, tmp_path):
    runner = make_runner(tmp_path, checkout_ref="feature/ref; echo unsafe")
    captured = {}

    class FakeProcess:
        returncode = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def communicate(self):
            return None, ""

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    runner._run_command(["git", "checkout", runner._full_driver_version])

    assert captured["cmd"] == ["git", "checkout", "feature/ref; echo unsafe"]
    assert "shell" not in captured["kwargs"]
    assert captured["kwargs"]["cwd"] == tmp_path / "driver repo"
