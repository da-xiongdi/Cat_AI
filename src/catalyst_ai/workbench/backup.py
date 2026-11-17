"""Create and verify a standalone SQLite management database backup."""

import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from catalyst_ai.storage.workbench import SCHEMA_VERSION, migrate, now


def backup_database(source: Path, destination: Path):
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination or destination.exists():
        raise FileExistsError("backup destination must be a new file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb"):
        pass
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(destination)) as backup:
            original.backup(backup)
            result = backup.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError(f"backup integrity check failed: {result}")
    return {
        "path": str(destination),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }


def create_bundle(source: Path, root: Path) -> bytes:
    """Snapshot management history and all indexed local files into one archive."""
    root = root.resolve(strict=True)
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory) / "workbench.sqlite"
        backup_database(source, snapshot)
        files = {"workbench.sqlite": snapshot.read_bytes()}
        missing = []
        with closing(sqlite3.connect(snapshot)) as conn:
            locations = conn.execute(
                "SELECT DISTINCT l.path, a.kind FROM artifact_location l "
                "JOIN artifact a ON a.id=l.artifact_id"
            ).fetchall()
        for location, kind in locations:
            path = (root / location).resolve()
            if not path.is_relative_to(root):
                missing.append({"path": location, "reason": "outside_workspace"})
            elif not path.is_file():
                missing.append({"path": location, "reason": "missing"})
            elif path == source.resolve():
                continue
            else:
                data = path.read_bytes()
                files["workspace/" + path.relative_to(root).as_posix()] = data
                if kind == "model":
                    model = (path.parent / "model.pkl").resolve()
                    try:
                        expected = json.loads(data)["artifact_sha256"]
                        if not model.is_relative_to(root):
                            raise ValueError("outside_workspace")
                        model_data = model.read_bytes()
                        if hashlib.sha256(model_data).hexdigest() != expected:
                            raise ValueError("hash_mismatch")
                        files["workspace/" + model.relative_to(root).as_posix()] = model_data
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        missing.append({"path": str(model), "reason": str(exc)})
        manifest = {
            "version": 1,
            "schema": SCHEMA_VERSION,
            "created_at": now(),
            "missing": missing,
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        return output.getvalue()


def preview_bundle(content: bytes) -> dict:
    """Verify every entry before allowing extraction or database restoration."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("备份存在重复文件名")
        manifest = json.loads(archive.read("manifest.json"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("version") != 1
            or not isinstance(manifest.get("schema"), int)
            or not 3 <= manifest["schema"] <= SCHEMA_VERSION
        ):
            raise ValueError("备份版本不兼容")
        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ValueError("备份清单无效")
        if "workbench.sqlite" not in files or set(names) != {*files, "manifest.json"}:
            raise ValueError("备份清单不完整")
        for name, digest in files.items():
            path = Path(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or (name != "workbench.sqlite" and not name.startswith("workspace/"))
            ):
                raise ValueError("备份路径无效")
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"备份文件哈希不匹配：{name}")
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "workbench.sqlite"
            snapshot.write_bytes(archive.read("workbench.sqlite"))
            with closing(sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True)) as conn:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("备份数据库完整性检查失败")
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("备份数据库关联检查失败")
                if conn.execute("PRAGMA user_version").fetchone()[0] != manifest["schema"]:
                    raise ValueError("备份数据库版本不匹配")
    return {"sha256": hashlib.sha256(content).hexdigest(), "manifest": manifest}


def restore_bundle(content: bytes, destination: Path, expected_sha256: str) -> dict:
    preview = preview_bundle(content)
    if preview["sha256"] != expected_sha256:
        raise ValueError("恢复预览哈希不匹配")
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("恢复目录需要为新目录")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        staging = Path(directory) / "restored"
        staging.mkdir()
        (staging / "workspace").mkdir()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in preview["manifest"]["files"]:
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
        migrate(staging / "workbench.sqlite")
        with closing(sqlite3.connect(staging / "workbench.sqlite")) as conn:
            conn.execute("UPDATE index_workspace SET root=?", (str(destination / "workspace"),))
            conn.commit()
        staging.rename(destination)
    return {"path": str(destination), **preview}
