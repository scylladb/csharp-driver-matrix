import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.pr_integration_changes import detect_changes


def test_runner_changes_include_shell_wrapper_and_workflows():
    for changed_file in [
        "scripts/run_test.sh",
        "scripts/image",
        ".github/workflows/integration-tests.yml",
        ".github/workflows/driver-integration-matrix.yml",
        ".github/workflows/pr-integration-tests.yml",
        "main.py",
    ]:
        outputs = detect_changes([changed_file], repo_root=REPO_ROOT)

        assert outputs["runner_changed"] == "true", changed_file


def test_changed_scylla_version_patch_expands_to_driver_matrix_entry():
    outputs = detect_changes(["versions/scylla/3.22.0.3/patch"], repo_root=REPO_ROOT)

    assert outputs["version_count"] == "1"
    matrix = json.loads(outputs["version_matrix"])
    assert matrix["include"] == [
        {
            "driver_type": "scylla",
            "driver_repository": "scylladb/csharp-driver",
            "driver_version": "3.22.0.3",
            "driver_ref": "v3.22.0.3",
        }
    ]


def test_changed_datastax_version_patch_expands_to_driver_matrix_entry():
    outputs = detect_changes(["versions/datastax/3.22.0/patch"], repo_root=REPO_ROOT)

    assert outputs["version_count"] == "1"
    matrix = json.loads(outputs["version_matrix"])
    assert matrix["include"] == [
        {
            "driver_type": "datastax",
            "driver_repository": "datastax/csharp-driver",
            "driver_version": "3.22.0",
            "driver_ref": "3.22.0",
        }
    ]


def test_candidate_version_uses_checkout_ref_for_all_scylla_targets(tmp_path):
    version_dir = tmp_path / "versions" / "scylla" / "3.22.0.5"
    version_dir.mkdir(parents=True)
    (version_dir / "checkout-ref").write_text("branch-3.22\n")

    outputs = detect_changes(["versions/scylla/3.22.0.5/patch"], repo_root=tmp_path)

    assert outputs["version_count"] == "4"
    assert json.loads(outputs["version_matrix"])["include"] == [
        {
            "driver_type": "scylla",
            "driver_repository": "scylladb/csharp-driver",
            "driver_version": "3.22.0.5",
            "driver_ref": "branch-3.22",
            "scylla_version": scylla_version,
        }
        for scylla_version in ("LATEST", "PRIOR", "LTS-LATEST", "LTS-PRIOR")
    ]


def test_candidate_version_rejects_empty_checkout_ref(tmp_path):
    version_dir = tmp_path / "versions" / "scylla" / "3.22.0.5"
    version_dir.mkdir(parents=True)
    (version_dir / "checkout-ref").write_text("\n")

    with pytest.raises(SystemExit, match="Empty checkout-ref"):
        detect_changes(["versions/scylla/3.22.0.5/patch"], repo_root=tmp_path)


def test_reusable_matrix_covers_the_same_five_lanes_as_pr_ci():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/driver-integration-matrix.yml").read_text())
    jobs = workflow["jobs"]

    assert jobs["datastax-integration-tests"]["with"] == {
        "driver_repository": "datastax/csharp-driver",
        "driver_type": "datastax",
        "scylla_version": "LATEST",
    }
    assert jobs["scylla-integration-tests"]["strategy"]["matrix"]["scylla_version"] == [
        "LATEST", "PRIOR", "LTS-LATEST", "LTS-PRIOR",
    ]
    assert jobs["scylla-integration-tests"]["with"]["driver_repository"] == "scylladb/csharp-driver"

    pr_workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/pr-integration-tests.yml").read_text())
    assert pr_workflow["jobs"]["current-workflow"]["uses"] == "./.github/workflows/driver-integration-matrix.yml"


def test_ccm_cache_restore_and_save_use_the_same_path():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/integration-tests.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integration-test"]["steps"]
    restore = next(step for step in steps if step.get("id") == "ccm-cache")
    save = next(step for step in steps if step.get("name") == "Save CCM download cache")

    assert restore["with"]["path"] == "~/.ccm/scylla-repository"
    assert save["with"]["path"] == restore["with"]["path"]


def test_integration_workflow_uploads_reports_after_failures():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/integration-tests.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["integration-test"]["steps"]
    reports = next(step for step in steps if step.get("name") == "Upload integration test reports")
    ccm_logs = next(step for step in steps if step.get("name") == "Upload CCM logs")

    for step in (reports, ccm_logs):
        assert step["if"] == "${{ always() }}"
        assert step["uses"].startswith("actions/upload-artifact@")
        assert len(step["uses"].removeprefix("actions/upload-artifact@")) == 40

    assert "test_results/" in reports["with"]["path"]
    assert "driver/**/TestResults/" in reports["with"]["path"]
    assert "~/.ccm/*/node*/logs/**" in ccm_logs["with"]["path"]


def test_integration_workflow_resolves_scylla_driver_v_tags():
    workflow_text = (REPO_ROOT / ".github/workflows/integration-tests.yml").read_text(encoding="utf-8")

    assert r"^v\d+\.\d+\.\d+\.\d+$" in workflow_text
    assert "git\", \"ls-remote\", \"--tags\", \"--refs\"" in workflow_text
