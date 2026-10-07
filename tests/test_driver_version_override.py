import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import main as matrix_main


def test_explicit_driver_version_uses_untagged_ref_without_resolving_tag(monkeypatch):
    observed = {}

    class FakeRun:
        def __init__(self, **kwargs):
            observed.update(kwargs)

        def run(self):
            return SimpleNamespace(summary={"testsuite_summary": {"time": 0}}, is_failed=False)

    monkeypatch.setattr(matrix_main, "Run", FakeRun)
    monkeypatch.setattr(matrix_main, "resolve_driver_version", lambda *_: pytest.fail("tag lookup is not needed"))

    arguments = matrix_main.argparse.Namespace(
        csharp_driver_git="driver",
        driver_type="scylla",
        versions=["3.22.0.5"],
        tests=["integration"],
        scylla_version="2026.1.3",
        checkout_ref="candidate-sha",
        recipients=None,
    )

    assert matrix_main.main(arguments) == 0
    assert observed["tag"] == "3.22.0.5"
    assert observed["checkout_ref"] == "candidate-sha"


def test_driver_version_argument_overrides_tag_lookup(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "main.py", "driver", "--scylla-version", "2026.1.3",
        "--driver-type", "scylla", "--checkout-ref", "candidate-sha",
        "--driver-version", "3.22.0.5",
    ])
    monkeypatch.setattr(matrix_main, "resolve_driver_version", lambda *_: pytest.fail("tag lookup is not needed"))

    assert matrix_main.get_arguments().versions == ["3.22.0.5"]


def test_driver_version_requires_checkout_ref(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "main.py", "driver", "--scylla-version", "2026.1.3",
        "--driver-version", "3.22.0.5",
    ])

    with pytest.raises(SystemExit, match="2"):
        matrix_main.get_arguments()
