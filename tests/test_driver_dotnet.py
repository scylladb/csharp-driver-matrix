from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from driver_dotnet import DotnetPolicy, scylla_dotnet_policy


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("v3.22.0.1", DotnetPolicy("9.0.318", "net9")),
        ("3.22.0.4", DotnetPolicy("9.0.318", "net9")),
        ("3.22.0.5", DotnetPolicy("9.0.318", "net9")),
        ("4.0.0.0", DotnetPolicy("10.0.401", "net10.0")),
        ("v4.1.2.3", DotnetPolicy("10.0.401", "net10.0")),
    ],
)
def test_scylla_version_policy(version, expected):
    assert scylla_dotnet_policy(version) == expected


@pytest.mark.parametrize("version", ["3.21.0.0", "5.0.0.0", "master", "deadbeef"])
def test_unknown_versions_fail_closed(version):
    with pytest.raises(ValueError, match="version|policy"):
        scylla_dotnet_policy(version)


def test_workflow_outputs_resolve_tag_without_global_json(tmp_path):
    output = tmp_path / "github-output"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "driver_dotnet.py"),
            "--driver-type", "scylla",
            "--driver-ref", "v3.22.0.4",
            "--github-output", str(output),
        ],
        check=True,
    )

    assert output.read_text(encoding="utf-8").splitlines() == [
        "driver_version=3.22.0.4",
        "sdk_version=9.0.318",
        "target_framework=net9",
    ]


def test_untagged_ref_requires_explicit_release_version(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "driver_dotnet.py"),
            "--driver-type", "scylla",
            "--driver-ref", "abcdef123456",
            "--github-output", str(tmp_path / "github-output"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Expected a Scylla driver release version" in result.stderr


def test_untagged_v4_commit_uses_explicit_version(tmp_path):
    output = tmp_path / "github-output"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "driver_dotnet.py"),
            "--driver-type", "scylla",
            "--driver-version", "4.0.0.0",
            "--driver-ref", "abcdef123456",
            "--github-output", str(output),
        ],
        check=True,
    )

    assert output.read_text(encoding="utf-8").splitlines() == [
        "driver_version=4.0.0.0",
        "sdk_version=10.0.401",
        "target_framework=net10.0",
    ]
