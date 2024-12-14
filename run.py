import json
import logging
import os
import re
import shutil
import subprocess
from functools import cached_property
from pathlib import Path
from typing import Dict, List

import yaml
from packaging.version import Version, InvalidVersion

from configurations import test_config_map
from processjunit import ProcessJUnit


class Run:
    def __init__(self, csharp_driver_git, driver_type, tag, tests, scylla_version):
        self.driver_version = tag.split("-", maxsplit=1)[0]
        self._full_driver_version = tag
        self._csharp_driver_git = csharp_driver_git
        self._scylla_version = scylla_version
        self._tests = tests
        self._driver_type = driver_type

    @cached_property
    def version_folder(self) -> Path:
        version_pattern = re.compile(r"\d+\.\d+\.\d+$")
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

        raise ValueError(f"Not found directory for gocql-driver version '{self.driver_version}'")

    @cached_property
    def ignore_tests(self) -> Dict[str, List[str]]:
        ignore_file = self.version_folder / "ignore.yaml"
        if not ignore_file.exists():
            logging.info("Cannot find ignore file for version '%s'", self.driver_version)
            return {}

        with ignore_file.open(mode="r", encoding="utf-8") as file:
            content = yaml.safe_load(file)
        ignore_tests = content.get("tests", []) or {'ignore': [], 'flaky': []}
        if not ignore_tests.get("ignore", None):
            logging.info("The file '%s' for version tag '%s' doesn't contain any test to ignore",
                         ignore_file, self.driver_version)
        return ignore_tests

    @cached_property
    def environment(self) -> Dict:
        return {**os.environ, "SCYLLA_VERSION": self._scylla_version}

    def _run_command_in_shell(self, cmd: str) -> None:
        logging.debug("Execute the cmd '%s'", cmd)
        with subprocess.Popen(cmd, shell=True, executable="/bin/bash", env=self.environment,
                              cwd=self._csharp_driver_git, stderr=subprocess.PIPE) as proc:
            _, stderr = proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd, stderr)

    def _checkout_branch(self) -> bool:
        try:
            self._run_command_in_shell("git checkout .")
            logging.info("git checkout to '%s' tag branch", self._full_driver_version)
            self._run_command_in_shell(f"git checkout {self._full_driver_version}")
            return True
        except Exception as exc:
            logging.error("Failed to branch for version '%s', with: '%s'", self.driver_version, str(exc))
            return False

    def _apply_patch_files(self) -> bool:
        for file_path in self.version_folder.iterdir():
            if file_path.name.startswith("patch"):
                try:
                    logging.info("Show patch's statistics for file '%s'", file_path)
                    self._run_command_in_shell(f"git apply --stat {file_path}")
                    logging.info("Detect patch's errors for file '%s'", file_path)
                    self._run_command_in_shell(f"git apply --check {file_path}")
                except subprocess.CalledProcessError as exc:
                        if 'tests/integration/conftest.py' in exc.stderr.decode():
                            self._run_command_in_shell(f"rm tests/integration/conftest.py")
                        else:
                            logging.exception(
                                "Failed to apply patch '%s' to version '%s'", file_path, self.driver_version)
                        raise
                logging.info("Applying patch file '%s'", file_path)
                self._run_command_in_shell(f"patch -p1 -i {file_path}")
        return True

    @cached_property
    def junit_dir(self) -> Path:
        return Path.cwd() / "test_results" / self.driver_version

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

    def run(self) -> ProcessJUnit | None:
        junit = ProcessJUnit(self.junit_dir / self.junit_file, self.driver_version, self.ignore_tests)
        logging.info("Changing the current working directory to the '%s' path", self._csharp_driver_git)
        os.chdir(self._csharp_driver_git)
        if self._checkout_branch() and self._apply_patch_files():
            for test in self._tests:
                test_config = test_config_map[test]
                add_junit_logger_cmd = f'dotnet add {test_config.test_project} package JUnitXml.TestLogger'
                logging.info("Running '%s' command to add JUnit logger to the '%s' tests", add_junit_logger_cmd, test)
                subprocess.call(f"{add_junit_logger_cmd}", shell=True, executable="/bin/bash",
                                env=self.environment, cwd=self._csharp_driver_git)

                logging.info("Run tests for tag '%s'", test)
                junit_logger = f'-l "junit;LogFilePath={self.junit_dir / self.junit_file}"'
                ignore_filter = " | ".join(
                    f"FullyQualifiedName!~{test}" for test in self.ignore_tests.get("ignore", []))
                test_cmd = f'dotnet test {test_config.test_project} {test_config.test_command_args} {junit_logger} --filter "{ignore_filter}"'
                logging.info("Running the test command '%s'", test_cmd)
                subprocess.call(f"{test_cmd}", shell=True, executable="/bin/bash",
                                env=self.environment, cwd=self._csharp_driver_git)
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
