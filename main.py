import sys
import argparse
import logging
import os
import subprocess
from datetime import timedelta
from typing import List
import traceback

from run import Run
from email_sender import create_report, get_driver_origin_remote, send_mail

logging.basicConfig(level=logging.INFO)


class EmptyTestResult(Exception):
    pass


def main(arguments: argparse.Namespace) -> int:
    status = 0
    results = dict()
    driver_type = get_driver_type(arguments.csharp_driver_git)

    for driver_version in arguments.versions:
        results[driver_version] = dict()
        for test in arguments.tests:
            logging.info("=== %s C# DRIVER VERSION %s. TEST: %s ===", driver_type.upper(), driver_version, test)
            runner = Run(csharp_driver_git=arguments.csharp_driver_git,
                         driver_type=driver_type,
                         tag=driver_version,
                         tests=arguments.tests,
                         scylla_version=arguments.scylla_version)
            try:
                report = runner.run()

                logging.info("=== %s C# DRIVER MATRIX RESULTS FOR DRIVER VERSION %s ===",
                             driver_type.upper(), driver_version)
                logging.info("\n%s", "\n".join(f"{key}: {value}" for key, value in report.summary.items()))
                if report.is_failed:
                    status = 1
                results[driver_version][test] = report.summary
                results[driver_version][test]["time"] = \
                    str(timedelta(seconds=results[driver_version][test]["testsuite_summary"]["time"]))[:-3]
            except Exception:
                logging.exception("%s failed", driver_version)
                status = 1
                failure_reason = traceback.format_exception(*sys.exc_info())
                results[driver_version] = dict(exception=failure_reason)
                runner.create_metadata_for_failure(reason="\n".join(failure_reason))

    if arguments.recipients:
        email_report = create_report(results=results)
        email_report["driver_remote"] = get_driver_origin_remote(arguments.csharp_driver_git)
        email_report["status"] = "SUCCESS" if status == 0 else "FAILED"
        send_mail(arguments.recipients, email_report)

    return status


def extract_n_latest_repo_tags(repo_directory: str, latest_tags_size: int = 2) -> List[str]:
    commands = [f"cd {repo_directory}", "git checkout .", "git tag --sort=-creatordate"]
    selected_tags = {}
    ignore_tags = set()
    result = []
    commands_in_line = "\n".join(commands)

    try:
        lines = subprocess.check_output(commands_in_line, shell=True, stderr=subprocess.STDOUT).decode().splitlines()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {e.output.decode()}") from e

    for repo_tag in lines:
        if "." in repo_tag:
            version = tuple(repo_tag.split(".", maxsplit=2)[:2])
            if version not in ignore_tags:
                ignore_tags.add(version)
                selected_tags.setdefault(version, []).append(repo_tag)

    for major_version in selected_tags:
        result.extend(selected_tags[major_version][:latest_tags_size])
        if len(result) == latest_tags_size:
            break

    return result


def get_arguments() -> argparse.Namespace:
    versions = ["3.22.0", "3.21.0"]
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("csharp_driver_git", help="Folder with Git repository of C# driver")
    parser.add_argument("--versions", default=versions, type=str,
                        help=f"Comma-separated C# driver versions to test, or number of latest tags. Default={','.join(versions)}")
    parser.add_argument("--tests", default="integration", choices=["integration"], nargs="*", type=str,
                        help="Tests to run (default: integration)")
    parser.add_argument("--scylla-version", default=os.environ.get("SCYLLA_VERSION", None),
                        help="Relocatable Scylla version to use (or set via SCYLLA_VERSION env variable)")
    parser.add_argument("--recipients",   nargs="+", default=None,
                        help="Email recipients for the test report")
    arguments = parser.parse_args()
    if not arguments.scylla_version:
        logging.error("--scylla-version is required if SCYLLA_VERSION environment variable is not set")
        sys.exit(1)

    versions = str(arguments.versions).replace(" ", "")
    if versions.isdigit():
        arguments.versions = extract_n_latest_repo_tags(
            repo_directory=arguments.csharp_driver_git, latest_tags_size=int(versions))
    else:
        arguments.versions = versions.split(",")

    return arguments


def get_driver_type(gocql_driver_git: str) -> str:
    return "scylla" if "scylladb" in get_driver_origin_remote(gocql_driver_git) else "datastax"


if __name__ == "__main__":
    sys.exit(main(get_arguments()))
