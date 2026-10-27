"""Run mypy for one service and compare its errors with a committed baseline.

Run from a service directory, inside its venv (roadmap F6):

    uv run --extra dev python ../../scripts/mypy_check.py [--update]

Errors are stored as `path: error: message  [code]`, without line numbers, so
edits elsewhere in a file don't change the baseline. The check fails on any
error that isn't in the baseline, and on baseline entries that no longer
occur, so the baseline can only shrink. `--update` rewrites it.

Exit codes: 0 matches the baseline, 1 new or stale errors, 2 mypy crashed or
stopped before checking everything.
"""

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASELINE = Path("mypy-baseline.txt")
HEADER = "# mypy errors accepted for now (roadmap F6). Regenerate with --update.\n"
ERROR_LINE = re.compile(r"^(?P<path>[^:\s]+):\d+(?::\d+)?: error: (?P<rest>.*)$")


def run_mypy() -> list[tuple[str, str]]:
    """Return (raw line, baseline entry) per error. Exit 2 if mypy didn't finish."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--no-pretty",
            "--no-color-output",
            "--no-error-summary",
            "--show-error-codes",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # mypy exits 1 for type errors and 2 for crashes, config errors and
    # "errors prevented further checking" (for example a duplicate module).
    if result.returncode not in (0, 1):
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        print(f"mypy did not finish (exit {result.returncode})", file=sys.stderr)
        sys.exit(2)
    errors = []
    for line in result.stdout.splitlines():
        if match := ERROR_LINE.match(line):
            errors.append((line, f"{match['path']}: error: {match['rest']}"))
    return errors


def read_baseline() -> Counter[str]:
    if not BASELINE.exists():
        return Counter()
    lines = BASELINE.read_text().splitlines()
    return Counter(line for line in lines if line and not line.startswith("#"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args()

    errors = run_mypy()
    current = Counter(entry for _, entry in errors)

    if args.update:
        entries = sorted(current.elements())
        BASELINE.write_text(HEADER + "".join(f"{entry}\n" for entry in entries))
        print(f"{BASELINE}: {current.total()} entries")
        return 0

    baseline = read_baseline()
    new = current - baseline
    stale = baseline - current

    if new:
        print(f"{new.total()} new mypy error(s) not in {BASELINE}:")
        # A repeated entry can't tell which occurrence is new, so print them all.
        for line, entry in errors:
            if entry in new:
                print(f"  {line}")
    if stale:
        print(f"{stale.total()} {BASELINE} entr(y/ies) no longer occur:")
        for entry in sorted(stale.elements()):
            print(f"  {entry}")
        print("Run with --update to shrink the baseline.")
    if new or stale:
        return 1

    print(f"mypy matches {BASELINE} ({current.total()} known errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
