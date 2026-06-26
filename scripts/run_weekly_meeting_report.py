#!/usr/bin/env python3
"""Run the weekly meeting report pipeline end to end."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print("+ " + " ".join(str(part) for part in cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, nargs="+", type=Path)
    parser.add_argument("--dish-input", nargs="+", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--company", default="麦家小馆")
    parser.add_argument("--current-start")
    parser.add_argument("--current-end")
    parser.add_argument("--previous-start")
    parser.add_argument("--previous-end")
    parser.add_argument("--yoy-start")
    parser.add_argument("--yoy-end")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    profile_cmd = [
        sys.executable,
        str(script_dir / "profile_weekly_meeting_data.py"),
        "--input",
        *[str(path) for path in args.input],
        "--output-dir",
        str(args.output_dir),
    ]
    if args.dish_input:
        profile_cmd.extend(["--dish-input", *[str(path) for path in args.dish_input]])
    if args.catalog:
        profile_cmd.extend(["--catalog", str(args.catalog)])
    for option in [
        "current_start",
        "current_end",
        "previous_start",
        "previous_end",
        "yoy_start",
        "yoy_end",
    ]:
        value = getattr(args, option)
        if value:
            profile_cmd.extend([f"--{option.replace('_', '-')}", value])
    run(profile_cmd)
    run([
        sys.executable,
        str(script_dir / "generate_weekly_meeting_report_html.py"),
        "--input-dir",
        str(args.output_dir),
        "--output",
        str(args.report),
        "--company",
        args.company,
    ])
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
