from pathlib import Path
from xml.etree import ElementTree
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from processjunit import ProcessJUnit


def write_junit_report(path: Path, failures: str = "1", include_error: bool = True) -> None:
    errors = "1" if include_error else "0"
    error_testcase = """\
    <testcase classname="C.Tests" name="errors" time="0.200">
      <error message="bad" type="RuntimeError">error line 1
error line 2</error>
      <system-err>stderr details</system-err>
    </testcase>
""" if include_error else ""
    path.write_text(
        f"""\
<testsuites>
  <testsuite name="CSharpTests" tests="2" errors="{errors}" skipped="0" failures="{failures}" time="1.500">
    <testcase classname="C.Tests" name="fails" time="0.100">
      <failure message="boom" type="AssertionError">stack line 1
stack line 2</failure>
      <system-out>stdout details</system-out>
    </testcase>
{error_testcase.rstrip()}
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )


def test_create_report_preserves_testcase_diagnostics(tmp_path):
    junit_file = tmp_path / "datastax_3.22.0.xml"
    write_junit_report(junit_file)

    report = ProcessJUnit(junit_file_xml=junit_file, tag="3.22.0", ignore_set={"ignore": [], "flaky": []})

    assert report.summary["testsuite_summary"] == {
        "time": 1.5,
        "tests": 2,
        "errors": 1,
        "skipped": 0,
        "failures": 1,
        "ignored_on_failure": 0,
    }

    root = ElementTree.parse(junit_file).getroot()
    testcases = root.findall("./testsuite/testcase")
    assert testcases[0].attrib["classname"] == "3.22.0.C.Tests"
    assert testcases[0].find("failure").text == "stack line 1\nstack line 2"
    assert testcases[0].find("system-out").text == "stdout details"
    assert testcases[1].find("error").text == "error line 1\nerror line 2"
    assert testcases[1].find("system-err").text == "stderr details"


def test_flaky_failure_is_marked_ignored_on_failure(tmp_path):
    junit_file = tmp_path / "scylla_3.22.0.3.xml"
    write_junit_report(junit_file, include_error=False)

    report = ProcessJUnit(junit_file_xml=junit_file, tag="3.22.0.3", ignore_set={"ignore": [], "flaky": ["fails"]})

    assert report.summary["testsuite_summary"]["failures"] == 0
    assert report.summary["testsuite_summary"]["ignored_on_failure"] == 1
    assert not report.is_failed

    root = ElementTree.parse(junit_file).getroot()
    suite = root.find("./testsuite")
    assert suite.attrib["failures"] == "0"
    assert suite.find("./testcase/ignored_on_failure").text == "stack line 1\nstack line 2"


def test_summary_counts_previously_marked_flaky_failures(tmp_path):
    junit_file = tmp_path / "scylla_3.22.0.3.xml"
    write_junit_report(junit_file, include_error=False)

    report = ProcessJUnit(junit_file_xml=junit_file, tag="3.22.0.3", ignore_set={"ignore": [], "flaky": ["fails"]})
    report.save_after_analysis()

    assert report.summary["testsuite_summary"]["failures"] == 0
    assert report.summary["testsuite_summary"]["ignored_on_failure"] == 1


def test_flaky_testcase_with_multiple_failure_nodes_decrements_failures_once(tmp_path):
    junit_file = tmp_path / "scylla_3.22.0.3.xml"
    junit_file.write_text(
        """\
<testsuites>
  <testsuite name="CSharpTests" tests="1" errors="0" skipped="0" failures="1" time="0.100">
    <testcase classname="C.Tests" name="fails" time="0.100">
      <failure message="boom 1" type="AssertionError">stack line 1</failure>
      <failure message="boom 2" type="AssertionError">stack line 2</failure>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    report = ProcessJUnit(junit_file_xml=junit_file, tag="3.22.0.3", ignore_set={"ignore": [], "flaky": ["fails"]})
    report.save_after_analysis()

    root = ElementTree.parse(junit_file).getroot()
    suite = root.find("./testsuite")
    ignored = suite.findall("./testcase/ignored_on_failure")
    assert suite.attrib["failures"] == "0"
    assert len(ignored) == 2
    assert report.summary["testsuite_summary"]["failures"] == 0
    assert report.summary["testsuite_summary"]["ignored_on_failure"] == 1
    assert not report.is_failed


def test_summary_preserves_testsuite_skipped_attribute_without_skipped_elements(tmp_path):
    junit_file = tmp_path / "datastax_3.22.0.xml"
    junit_file.write_text(
        """\
<testsuites>
  <testsuite name="CSharpTests" tests="3" errors="0" skipped="3" failures="0" time="0.100">
    <testcase classname="C.Tests" name="skipped_by_attribute" time="0.000" />
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    report = ProcessJUnit(junit_file_xml=junit_file, tag="3.22.0", ignore_set={"ignore": [], "flaky": []})

    assert report.summary["testsuite_summary"]["skipped"] == 3
