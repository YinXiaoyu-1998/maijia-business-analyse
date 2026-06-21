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
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--company", default="麦家小馆")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    run([
        sys.executable,
        str(script_dir / "profile_weekly_meeting_data.py"),
        "--input",
        *[str(path) for path in args.input],
        "--output-dir",
        str(args.output_dir),
    ])
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
