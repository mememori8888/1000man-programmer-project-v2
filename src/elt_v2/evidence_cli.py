from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from elt_v2.evidence import build_evidence_template, validate_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate v2 release evidence for demo compatibility.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("template", help="Print a release evidence JSON template.")
    template_parser.add_argument("--output", type=Path)

    validate_parser = subparsers.add_parser("validate", help="Validate a release evidence JSON file.")
    validate_parser.add_argument("--file", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "template":
        encoded = json.dumps(build_evidence_template(), ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0

    if args.command == "validate":
        try:
            payload = json.loads(args.file.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "valid": False,
                        "errors": [f"release evidence JSON could not be read: {exc}"],
                        "warnings": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            sys.stderr.write("release evidence is incomplete\n")
            return 1
        if not isinstance(payload, dict):
            print(
                json.dumps(
                    {
                        "valid": False,
                        "errors": ["release evidence JSON must be an object"],
                        "warnings": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            sys.stderr.write("release evidence is incomplete\n")
            return 1
        result = validate_evidence(payload)
        print(
            json.dumps(
                {
                    "valid": result.valid,
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if not result.valid:
            sys.stderr.write("release evidence is incomplete\n")
            return 1
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
