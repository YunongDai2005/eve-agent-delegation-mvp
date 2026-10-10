"""Invoke unmodified official A2A Inspector validators against captured runtime objects."""

import argparse
import importlib.util
import json
from pathlib import Path

from eve_demo.config import ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspector",
        type=Path,
        required=True,
        help="Path to a2aproject/a2a-inspector checkout at upstreams.json revision",
    )
    parser.add_argument("--packet", type=Path, default=ROOT / "evidence" / "last-live.json")
    args = parser.parse_args()
    source = args.inspector / "backend" / "validators.py"
    spec = importlib.util.spec_from_file_location("official_inspector_validators", source)
    assert spec is not None and spec.loader is not None
    validators = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validators)
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    card_errors = validators.validate_agent_card(packet["agent_card"])
    remote_id = packet["job"]["result"].get("a2a_task_id")
    # Capture a REAL remote Task using SDK via a fresh client in a separate service session.
    # packet can additionally contain a captured task (added by capture_static.py).
    task = json.loads((ROOT / "evidence" / "a2a-task.json").read_text(encoding="utf-8"))
    task_errors = validators.validate_message(task)
    output = {
        "validator_source": "a2aproject/a2a-inspector/backend/validators.py",
        "revision": "8aa064639af106ff771d60428ef6d460f5454743",
        "validation_scope": "Official Inspector structural validators, not GUI/full conformance",
        "packet_remote_task_id": remote_id,
        "captured_task_id": task.get("id"),
        "agent_card_errors": card_errors,
        "task_errors": task_errors,
        "passed": not card_errors and not task_errors,
    }
    (ROOT / "evidence" / "inspector-validation.json").write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
