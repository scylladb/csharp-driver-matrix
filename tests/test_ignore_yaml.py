from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from run import load_ignore_tests


@pytest.mark.parametrize("selector", ["DriverIT #should_fail", "DriverIT # should_fail"])
def test_load_ignore_tests_rejects_unquoted_method_selector(tmp_path, selector):
    ignore_file = tmp_path / "ignore.yaml"
    ignore_file.write_text(
        f"""\
tests:
  ignore:
    - {selector}
  flaky: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entries containing '#' must be quoted"):
        load_ignore_tests(ignore_file)


def test_load_ignore_tests_rejects_empty_and_duplicate_entries(tmp_path):
    ignore_file = tmp_path / "ignore.yaml"
    ignore_file.write_text(
        """\
tests:
  ignore:
    - DriverIT
    -
  flaky:
    - DriverIT
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="empty or non-string entries.*duplicate entries: DriverIT"):
        load_ignore_tests(ignore_file)


def test_load_ignore_tests_accepts_nested_ignore_and_flaky_lists(tmp_path):
    ignore_file = tmp_path / "ignore.yaml"
    ignore_file.write_text(
        """\
tests:
  ignore:
    - DriverIT
  flaky:
    - FlakyIT
""",
        encoding="utf-8",
    )

    assert load_ignore_tests(ignore_file) == {"ignore": ["DriverIT"], "flaky": ["FlakyIT"]}


def test_all_ignore_files_are_valid():
    for ignore_file in sorted((REPO_ROOT / "versions").glob("*/*/ignore.yaml")):
        load_ignore_tests(ignore_file)
