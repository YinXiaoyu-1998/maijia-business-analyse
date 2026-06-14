#!/usr/bin/env python3
"""Run the Maijia business analysis pipeline end to end."""

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
    parser.add_argument("--input", required=True, type=Path, help="Meituan exported .xlsx file")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for fact tables")
    parser.add_argument("--report", required=True, type=Path, help="HTML report output path")
    parser.add_argument("--company", default="麦家小馆")
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parents[1]
    profile_script = skill_dir / "scripts" / "profile_business_data.py"
    report_script = skill_dir / "scripts" / "generate_business_report_html.py"

    run([
        sys.executable,
        str(profile_script),
        "--input",
        str(args.input),
        "--output-dir",
        str(args.output_dir),
    ])
    run([
        sys.executable,
        str(report_script),
        "--input-dir",
        str(args.output_dir),
        "--output",
        str(args.report),
        "--company",
        args.company,
        "--source-name",
        args.input.name,
    ])
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
