from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

SENSITIVE_ASSIGNMENT = re.compile(
    r"""
    \b[A-Z][A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY)[A-Z0-9_]*\b
    \s*[:=]\s*
    (?P<value>"[^"\r\n]*"|'[^'\r\n]*'|[^\s#;]+)
    """,
    flags=re.VERBOSE,
)
URI_CREDENTIAL = re.compile(
    r"\b[a-z][a-z0-9+.-]*://[^\s/@:]+:(?P<value>[^\s/@]+)@",
    flags=re.IGNORECASE,
)
SYNTHETIC_VALUES = frozenset(
    {
        "application",
        "dummy",
        "example",
        "migration",
        "postgres",
        "test",
    }
)
DEFAULT_EXCLUSIONS = frozenset({".env.example"})


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    kind: str


def scan_paths(paths: tuple[Path, ...]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            assignment = SENSITIVE_ASSIGNMENT.search(line)
            if assignment and not _is_safe_reference(assignment.group("value")):
                findings.append(
                    Finding(path, line_number, "sensitive environment assignment")
                )
            uri = URI_CREDENTIAL.search(line)
            if uri and not _is_safe_reference(uri.group("value")):
                findings.append(Finding(path, line_number, "URI credential"))
    return findings


def repository_paths(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    relative_paths = result.stdout.decode("utf-8").split("\0")
    return tuple(
        root / relative_path
        for relative_path in relative_paths
        if relative_path and relative_path.replace("\\", "/") not in DEFAULT_EXCLUSIONS
    )


def _is_safe_reference(raw_value: str) -> bool:
    value = unquote(raw_value.strip().strip("\"'")).strip()
    lowered = value.casefold()
    if not value:
        return True
    if value.startswith(("$", "<")) or lowered.startswith(
        ("os.getenv(", "os.environ[")
    ):
        return True
    return lowered in SYNTHETIC_VALUES or lowered.startswith("change-me")


def main() -> int:
    root = Path.cwd()
    findings = scan_paths(repository_paths(root))
    for finding in findings:
        relative_path = finding.path.relative_to(root)
        print(f"{relative_path}:{finding.line_number}: {finding.kind}")
    if findings:
        print(f"Secret scan failed with {len(findings)} finding(s).")
        return 1
    print("Secret scan passed: no literal credentials detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
