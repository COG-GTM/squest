#!/usr/bin/env python3
"""Compute patch coverage: the share of lines added or changed by a PR that the test suite executes.

Reads a `coverage json` report and the unified diff against the merge base, then reports the
uncovered symbols (module-level functions, classes and methods) the PR touched.

Usage:
    coverage json -o coverage.json
    python scripts/patch_coverage.py --base-ref origin/master --fail-under 85
"""
import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def changed_lines(base_ref):
    """Map each changed Python file to the set of line numbers it added or modified."""
    # HEAD is explicit so an earlier step touching a tracked file cannot leak into the patch
    diff = run("git", "diff", "--merge-base", "--unified=0", base_ref, "HEAD", "--", "*.py")
    per_file = {}
    current = None
    in_hunks = False
    for line in diff.splitlines():
        # only the lines before the first hunk of a file are headers; afterwards a body line may
        # legitimately start with --- or +++ and must not be mistaken for one
        if line.startswith("diff --git "):
            current, in_hunks = None, False
        elif not in_hunks and line.startswith("+++ b/"):
            current = line[len("+++ b/"):]
            per_file.setdefault(current, set())
        elif current is not None:
            match = HUNK_HEADER.match(line)
            if match:
                in_hunks = True
                start = int(match.group(1))
                count = 1 if match.group(2) is None else int(match.group(2))
                per_file[current].update(range(start, start + count))
    return {path: lines for path, lines in per_file.items() if lines and Path(path).exists()}


def symbol_ranges(path):
    """Yield (qualified_name, first_line, last_line) for every function and class in a file."""
    try:
        tree = ast.parse(Path(path).read_text())
    except SyntaxError:
        return []
    symbols = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                first_line = min([child.lineno] + [decorator.lineno for decorator in child.decorator_list])
                symbols.append((name, first_line, child.end_lineno))
                walk(child, f"{name}.")

    walk(tree, "")
    return symbols


def symbols_for_lines(path, lines):
    """Name the smallest symbol containing each line; lines outside any symbol get '<module>'."""
    ranges = symbol_ranges(path)
    named = {}
    for line in sorted(lines):
        candidates = [(end - start, name) for name, start, end in ranges if start <= line <= end]
        name = min(candidates)[1] if candidates else "<module>"
        named.setdefault(name, []).append(line)
    return named


def format_lines(lines):
    """Collapse a sorted list of line numbers into compact ranges: [1,2,3,7] -> '1-3, 7'."""
    ranges = []
    for line in lines:
        if ranges and line == ranges[-1][1] + 1:
            ranges[-1][1] = line
        else:
            ranges.append([line, line])
    return ", ".join(str(start) if start == end else f"{start}-{end}" for start, end in ranges)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-json", default="coverage.json")
    parser.add_argument("--base-ref", default="origin/master")
    parser.add_argument("--fail-under", type=float, default=85.0)
    parser.add_argument("--report", help="Write the human readable report to this file as well")
    args = parser.parse_args()

    report = json.loads(Path(args.coverage_json).read_text())["files"]
    changed = changed_lines(args.base_ref)

    total_relevant = 0
    total_covered = 0
    uncovered = {}
    for path, lines in changed.items():
        # files coverage did not measure (tests, settings, migrations - see .coveragerc) are ignored
        if path not in report:
            continue
        executed = set(report[path]["executed_lines"])
        missing = set(report[path]["missing_lines"])
        relevant = lines & (executed | missing)
        if not relevant:
            continue
        total_relevant += len(relevant)
        total_covered += len(relevant & executed)
        if relevant & missing:
            uncovered[path] = symbols_for_lines(path, relevant & missing)

    if total_relevant == 0:
        print("Patch coverage: no measured lines changed by this PR - nothing to gate.")
        return 0

    percent = 100.0 * total_covered / total_relevant
    lines = [
        f"Patch coverage: {percent:.1f}% ({total_covered}/{total_relevant} changed lines covered), "
        f"threshold {args.fail_under:.1f}%",
    ]
    if uncovered:
        lines.append("")
        lines.append("Uncovered symbols touched by this PR:")
        for path in sorted(uncovered):
            for symbol, symbol_lines in sorted(uncovered[path].items()):
                lines.append(f"  - {path}::{symbol} (lines {format_lines(symbol_lines)})")
    text = "\n".join(lines)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n")

    return 0 if percent >= args.fail_under else 1


if __name__ == "__main__":
    # exit 1 means "below threshold" and drives the gate; anything unexpected exits 2 so the workflow
    # can tell a coverage regression apart from a broken check
    try:
        sys.exit(main())
    except Exception as error:
        print(f"patch coverage check failed to run: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
