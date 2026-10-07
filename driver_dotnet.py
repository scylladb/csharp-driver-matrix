"""Select the Scylla C# driver's test SDK and framework from its version."""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")


@dataclass(frozen=True)
class DotnetPolicy:
    sdk_version: str
    target_framework: str


def scylla_dotnet_policy(version: str) -> DotnetPolicy:
    match = _VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"Expected a Scylla driver release version, got {version!r}")

    major, minor = map(int, match.group(1, 2))
    if (major, minor) == (3, 22):
        return DotnetPolicy("9.0.318", "net9")
    if major == 4:
        return DotnetPolicy("10.0.401", "net10.0")
    raise ValueError(f"No .NET compatibility policy for Scylla driver {version!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-type", required=True, choices=("scylla", "datastax"))
    parser.add_argument("--driver-version", default="")
    parser.add_argument("--driver-ref", required=True)
    parser.add_argument("--github-output", required=True, type=Path)
    args = parser.parse_args()

    version = args.driver_version or args.driver_ref
    if args.driver_type == "scylla":
        policy = scylla_dotnet_policy(version)
        version = version.removeprefix("v")
        sdk_version = policy.sdk_version
        target_framework = policy.target_framework
    else:
        sdk_version = ""
        target_framework = "net8"
        version = args.driver_version

    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"driver_version={version}\n")
        output.write(f"sdk_version={sdk_version}\n")
        output.write(f"target_framework={target_framework}\n")


if __name__ == "__main__":
    main()
