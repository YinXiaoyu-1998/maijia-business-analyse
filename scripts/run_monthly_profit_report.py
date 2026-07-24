#!/usr/bin/env python3
"""Run the standalone monthly profit and profit-rate report pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> None:
    print("+ " + " ".join(map(str, command)))
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profit-file", required=True, type=Path)
    parser.add_argument("--business-input", required=True, nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--company", default="麦家小馆")
    args = parser.parse_args()
    scripts = Path(__file__).resolve().parent
    run([sys.executable, str(scripts / "profile_monthly_profit_data.py"), "--profit-file", str(args.profit_file), "--business-input", *map(str, args.business_input), "--output-dir", str(args.output_dir)])
    run([sys.executable, str(scripts / "generate_monthly_profit_report_html.py"), "--input-dir", str(args.output_dir), "--output", str(args.report), "--company", args.company])


if __name__ == "__main__":
    main()
