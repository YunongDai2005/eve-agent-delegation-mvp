import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eve_demo.processes import Services  # noqa: E402


@pytest.fixture(scope="session")
def services(tmp_path_factory):
    with Services(9130, 9131, tmp_path_factory.mktemp("e2e")) as instance:
        yield instance


def load_cases():
    return json.loads((Path(__file__).parent / "cases.json").read_text())
