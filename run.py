import json
import logging
import os
import re
import shutil
import shlex
import subprocess
from functools import cached_property
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import yaml
from packaging.version import Version, InvalidVersion

from configurations import test_config_map
from processjunit import ProcessJUnit


IGNORE_TEST_CATEGORIES = ("ignore", "flaky")


def _empty_ignore_tests() -> Dict[str, List[str]]:
    return {category: [] for category in IGNORE_TEST_CATEGORIES}


def load_ignore_tests(ignore_file: Path) -> Dict[str, List[str]]:
    if not ignore_file.is_file():
        return _empty_ignore_tests()

    text = ignore_file.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if re.match(r"^\s*-\s+[^'\"#\n][^#\n]*\s+#\S", line):
            raise ValueError(
                f"Invalid test selector in '{ignore_file}' at line {line_number}: "
                "entries containing '#' must be quoted"
            )

    content = yaml.safe_load(text)
    if content is None:
        return _empty_ignore_tests()
    if not isinstance(content, dict):
        raise ValueError(f"The '{ignore_file}' file must contain a YAML mapping")

    tests = content.get("tests")
    if tests is None:
        return _empty_ignore_tests()
    if not isinstance(tests, dict):
        raise ValueError(f"The 'tests' entry in '{ignore_file}' must be a mapping")

    result = _empty_ignore_tests()
    seen = set()
    invalid_entries = []
    duplicates = []
    for category in IGNORE_TEST_CATEGORIES:
        entries = tests.get(category) or []
        if not isinstance(entries, list):
            raise ValueError(f"The 'tests.{category}' entry in '{ignore_file}' must be a list")

        for index, test_name in enumerate(entries, start=1):
            if not isinstance(test_name, str) or not test_name.strip():
                invalid_entries.append(f"{category}[{index}]")
                continue
            test_name = test_name.strip()
            if test_name in seen:
                duplicates.append(test_name)
                continue
            seen.add(test_name)
            result[category].append(test_name)

    if invalid_entries or duplicates:
        details = []
        if invalid_entries:
            details.append(f"empty or non-string entries at indexes: {', '.join(invalid_entries)}")
        if duplicates:
            details.append(f"duplicate entries: {', '.join(duplicates)}")
        raise ValueError(f"Invalid ignore tests in '{ignore_file}': {'; '.join(details)}")

    return result


class Run:
    def __init__(self, csharp_driver_git, driver_type, tag, tests, scylla_version, checkout_ref=None):
        self.driver_version = tag.removeprefix("v").split("-", maxsplit=1)[0]
        self._full_driver_version = checkout_ref or tag
        self._csharp_driver_git = Path(csharp_driver_git)
        self._scylla_version = scylla_version
        self._tests = [tests] if isinstance(tests, str) else tests
        self._driver_type = driver_type

    @cached_property
    def version_folder(self) -> Path:
        # Match both 3-part (3.22.0) and 4-part (3.22.0.2) version patterns
        version_pattern = re.compile(r"\d+\.\d+\.\d+(\.\d+)?$")
        target_version_folder = Path(__file__).parent / "versions" / self._driver_type
        try:
            target_version = Version(self.driver_version)
        except InvalidVersion:
            target_dir = target_version_folder / self.driver_version
            if target_dir.is_dir():
                return target_dir
            return target_version_folder / "master"

        tags_defined = sorted(
            (
                Version(folder_path.name)
                for folder_path in target_version_folder.iterdir() if version_pattern.match(folder_path.name)
            ),
            reverse=True
        )
        for tag in tags_defined:
            if tag <= target_version:
                return target_version_folder / str(tag)

        raise ValueError(f"Not found directory for {self._driver_type}-csharp-driver version '{self.driver_version}'")

    @cached_property
    def ignore_tests(self) -> Dict[str, List[str]]:
        ignore_file = self.version_folder / "ignore.yaml"
        if not ignore_file.is_file():
            logging.info("Cannot find ignore file for version '%s'", self.driver_version)
            return _empty_ignore_tests()

        ignore_tests = load_ignore_tests(ignore_file)
        if not ignore_tests.get("ignore", None):
            logging.info("The file '%s' for version tag '%s' doesn't contain any test to ignore",
                         ignore_file, self.driver_version)
        return ignore_tests

    @cached_property
    def environment(self) -> Dict:
        env = {**os.environ, "SCYLLA_VERSION": self._scylla_version_for_ccm()}
        # For ScyllaDB driver: set BuildTarget to net8 to avoid requiring .NET 9 SDK
        # ScyllaDB driver defaults to net9 when BuildTarget is not set
        if self._driver_type == "scylla":
            env["BuildTarget"] = "net8"
        return env

    def _scylla_version_for_ccm(self) -> str:
        if (
                self._scylla_version
                and ":" not in self._scylla_version
                and os.environ.get("SCYLLA_UNIFIED_PACKAGE") is None
        ):
            return f"release:{self._scylla_version}"
        return self._scylla_version

    def _run_command(self, cmd: Sequence[str]) -> None:
        cmd = [str(arg) for arg in cmd]
        logging.debug("Execute the cmd '%s'", shlex.join(cmd))
        with subprocess.Popen(cmd, env=self.environment, cwd=self._csharp_driver_git,
                              stderr=subprocess.PIPE, text=True) as proc:
            _, stderr = proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=stderr)

    def _call_command(self, cmd: Sequence[str], env: Optional[Dict[str, str]] = None) -> int:
        cmd = [str(arg) for arg in cmd]
        logging.info("Running the command '%s'", shlex.join(cmd))
        return subprocess.call(cmd, env=env or self.environment, cwd=self._csharp_driver_git)

    def _checkout_branch(self) -> bool:
        try:
            self._run_command(["git", "checkout", "."])
            logging.info("git checkout to '%s' tag branch", self._full_driver_version)
            self._run_command(["git", "checkout", self._full_driver_version])
            return True
        except Exception as exc:
            logging.error("Failed to branch for version '%s', with: '%s'", self.driver_version, str(exc))
            return False

    def _apply_patch_files(self) -> bool:
        for file_path in self.version_folder.iterdir():
            if file_path.name.startswith("patch"):
                try:
                    logging.info("Show patch's statistics for file '%s'", file_path)
                    self._run_command(["git", "apply", "--stat", file_path])
                    logging.info("Detect patch's errors for file '%s'", file_path)
                    self._run_command(["git", "apply", "--check", file_path])
                except subprocess.CalledProcessError as exc:
                    if "tests/integration/conftest.py" in (exc.stderr or ""):
                        (self._csharp_driver_git / "tests/integration/conftest.py").unlink()
                    else:
                        logging.exception(
                            "Failed to apply patch '%s' to version '%s'", file_path, self.driver_version)
                    raise
                logging.info("Applying patch file '%s'", file_path)
                self._run_command(["patch", "-p1", "-i", file_path])
        return True

    @cached_property
    def junit_dir(self) -> Path:
        dir_path = Path.cwd() / "test_results" / self.driver_version
        if dir_path.exists():
            shutil.rmtree(dir_path)
        return dir_path

    @cached_property
    def junit_file(self) -> str:
        return f"{self._driver_type}_{self.driver_version}.xml"

    @cached_property
    def metadata_file_name(self) -> str:
        return f'metadata_{self._driver_type}_{self.driver_version}.json'

    def create_metadata_for_failure(self, reason: str) -> None:
        metadata_file = self.junit_dir / self.metadata_file_name
        self.junit_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "driver_name": self.junit_file.replace(".xml", ""),
            "driver_type": "csharp",
            "failure_reason": reason,
        }
        metadata_file.write_text(json.dumps(metadata))

    def ensure_simulacron(self, version: str = '0.12.0') -> str:
        simulacron_path = Path(__file__).parent / f"simulacron-standalone-{version}.jar"
        if not simulacron_path.exists():
            logging.info("Simulacron version %s is not found. Downloading to %s.", version, str(simulacron_path))
            try:
                self._run_command(
                    [
                        "curl",
                        "-sL",
                        "-o",
                        simulacron_path,
                        f"https://github.com/datastax/simulacron/releases/download/{version}/simulacron-standalone-{version}.jar",
                    ])
            except Exception as exc:
                logging.error("Failed to download Simulacron: %s", str(exc))
                raise
        return str(simulacron_path)

    def _restore_dotnet_dependencies(self) -> None:
        for project in sorted((self._csharp_driver_git / "src").glob("**/*.csproj")):
            self._call_command(["dotnet", "restore", project])

    def _setup_development_snk(self) -> None:
        snk_file = self._csharp_driver_git / "build/scylladb.snk"
        if not snk_file.is_file():
            shutil.copyfile(self._csharp_driver_git / "build/scylladb-dev.snk", snk_file)

    def _ignore_filter(self) -> str:
        ignore_tests = " & ".join(
            f"FullyQualifiedName!~{test}" for test in self.ignore_tests.get("ignore") or [])
        return f"({ignore_tests})" if ignore_tests else ""

    def _test_command(self, test: str) -> List[str]:
        test_config = test_config_map[test]
        cmd = ["dotnet", "test", test_config.test_project]
        cmd.extend(shlex.split(test_config.test_command_args))
        cmd.extend(["-l", f"junit;LogFilePath={self.junit_dir / self.junit_file}"])
        if ignore_filter := self._ignore_filter():
            cmd.extend(["--filter", ignore_filter])
        return cmd

    def _test_environment(self, simulacron_path: str) -> Dict[str, str]:
        return {
            **self.environment,
            "SIMULACRON_PATH": simulacron_path,
            "CCM_DISTRIBUTION": "scylla",
        }

    def run(self) -> ProcessJUnit | None:
        junit = ProcessJUnit(self.junit_dir / self.junit_file, self.driver_version, self.ignore_tests)
        logging.info("Changing the current working directory to the '%s' path", self._csharp_driver_git)
        os.chdir(self._csharp_driver_git)
        if self._checkout_branch() and self._apply_patch_files():
            simulacron_path = self.ensure_simulacron()
            for test in self._tests:
                test_config = test_config_map[test]
                logging.info("Add JUnit logger for tests %s.", test)
                self._call_command(["dotnet", "add", test_config.test_project, "package", "JUnitXml.TestLogger"])

                logging.info("Restore dotnet dependencies to finish all lazy initialization before tests are started.")
                self._restore_dotnet_dependencies()

                # For ScyllaDB driver, ensure development SNK is set up before running tests
                if self._driver_type == "scylla":
                    logging.info("Setting up development SNK for ScyllaDB driver")
                    self._setup_development_snk()

                logging.info("Run tests for tag '%s'", test)
                self._call_command(self._test_command(test), env=self._test_environment(simulacron_path))
            junit.save_after_analysis()

            try:
                metadata_file = self.junit_dir / self.metadata_file_name
                metadata_file.write_text(json.dumps({
                    "driver_name": self.junit_file.replace(".xml", ""),
                    "driver_type": "csharp",
                    "junit_result": f"./{self.junit_file}",
                }))
            except Exception as e:
                logging.error("Failed to write metadata: %s", str(e))

        return junit
