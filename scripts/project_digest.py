from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    ROOT / "Docs" / "Goals.md",
    ROOT / "Docs" / "CurrentTask.md",
    ROOT / "Docs" / "ErrorLog.md",
    ROOT / "Docs" / "DecisionLog.md",
    ROOT / "Docs" / "Architecture.md",
    ROOT / "README.md",
]


def read_preview(path: Path, max_lines: int = 18) -> str:
    if not path.exists():
        return f"## {path.relative_to(ROOT)}\nMissing\n"
    lines = path.read_text(encoding="utf-8").splitlines()
    preview = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        preview += "\n..."
    return f"## {path.relative_to(ROOT)}\n{preview}\n"


def git_output(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout.strip() or result.stderr.strip()
    return output if output else "(none)"


def main() -> None:
    print("# SoundScrapper Project Digest")
    print()
    print("## Git Status")
    print(git_output(["status", "--short"]))
    print()
    print("## Current Branch")
    print(git_output(["branch", "--show-current"]))
    print()
    print("## Document Preview")
    for path in DOCS:
        print(read_preview(path))


if __name__ == "__main__":
    main()
