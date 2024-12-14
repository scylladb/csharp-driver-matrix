from dataclasses import dataclass
from typing import List, Dict


@dataclass
class TestConfiguration:
    tags: List[str]
    test_project: str
    test_command_args: str
    cluster_configuration: Dict[str, str]


integration_tests = TestConfiguration(
    tags=["integration"],
    test_project='src/Cassandra.IntegrationTests/Cassandra.IntegrationTests.csproj',
    test_command_args='-f net8 -l "console;verbosity=detailed"',
    cluster_configuration={})

test_config_map = {
    "integration": integration_tests,
}
