import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from catalyst_ai import __version__


def now():
    return datetime.now(UTC).isoformat()


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def metadata(settings):
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unversioned"
    code_files = sorted(Path(__file__).parents[1].rglob("*.py"))
    return {
        "package_version": __version__,
        "code_revision": revision,
        "code_sha256": digest(
            {
                p.relative_to(Path(__file__).parents[1]).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in code_files
            }
        ),
        "config_sha256": digest(settings.model_dump(mode="json")),
        "config": settings.model_dump(mode="json"),
        "model_run_id": None,
        "governance_version": settings.governance_version,
    }


def write_new(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)


def write_json(path: Path, payload):
    write_new(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"),
    )


def summary(report):
    counts = report["counts"]
    lines = [
        "数据质量报告（软件流程验证，不是科研结论）",
        f"run_id: {report['run_id']}",
        f"dry_run: {report['dry_run']}",
        f"dataset_kind: {', '.join(report['dataset_kinds']) or 'unknown'}",
        " / ".join(f"{k}={v}" for k, v in counts.items()),
    ]
    for row in report["rows"]:
        lines.append(f"{row['input_locator']} → {row['status']} [{row['record_id']}]")
        lines.extend(
            f"  {i['severity']} {i['code']} {i['path']}: {i['message']}" for i in row["issues"]
        )
    return "\n".join(lines) + "\n"
