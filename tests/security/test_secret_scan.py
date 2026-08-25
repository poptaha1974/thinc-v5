from pathlib import Path

from scripts.secret_scan import scan_paths


def test_secret_scan_detects_env_assignments_and_uri_credentials(
    tmp_path: Path,
) -> None:
    env_names = (
        "DATABASE_" + "PASSWORD",
        "CLIENT_" + "SECRET",
        "ACCESS_" + "TOKEN",
        "SERVICE_" + "API_KEY",
    )
    uri = "postgresql://app:" + "private-value@db.example.test/app"
    candidate = tmp_path / "candidate.env"
    candidate.write_text(
        "\n".join(f"{name}=private-value" for name in env_names)
        + f"\nDATABASE_URL={uri}\n",
        encoding="utf-8",
    )

    findings = scan_paths((candidate,))

    assert [(finding.line_number, finding.kind) for finding in findings] == [
        (1, "sensitive environment assignment"),
        (2, "sensitive environment assignment"),
        (3, "sensitive environment assignment"),
        (4, "sensitive environment assignment"),
        (5, "URI credential"),
    ]


def test_secret_scan_allows_references_and_explicit_synthetic_placeholders(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "safe.env"
    candidate.write_text(
        "DATABASE_PASSWORD=${DATABASE_PASSWORD}\n"
        "DATABASE_URL=postgresql://app:change-me-app@localhost/test\n",
        encoding="utf-8",
    )

    assert scan_paths((candidate,)) == []
