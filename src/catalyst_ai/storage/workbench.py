"""Versioned SQLite storage for the workbench management service."""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 7


def now():
    return datetime.now(UTC).isoformat()


def connect(path: Path):
    db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def migrate(path: Path):
    """Initialize or upgrade explicitly; existing databases are backed up first."""
    path = Path(path)
    existed = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError("unsupported workbench schema version")
        if version == SCHEMA_VERSION:
            return
        if existed:
            backup_path = path.with_name(path.name + f".v{version}.backup")
            if backup_path.exists():
                raise FileExistsError(f"backup already exists: {backup_path}")
            backup = sqlite3.connect(str(backup_path))
            try:
                db.backup(backup)
            finally:
                backup.close()
        if version == 0:
            db.executescript("""
        BEGIN IMMEDIATE;
        CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE task (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
          title TEXT NOT NULL, goal TEXT NOT NULL, deliverables TEXT NOT NULL,
          milestone TEXT, stages TEXT NOT NULL, primary_stage TEXT,
          status TEXT NOT NULL, priority TEXT NOT NULL, owner TEXT, planned_date TEXT,
          criteria_version INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1,
          blocker TEXT, recovery_condition TEXT, recovery_date TEXT
        );
        CREATE TABLE dependency (
          task_id TEXT NOT NULL REFERENCES task(id),
          prerequisite_id TEXT NOT NULL REFERENCES task(id),
          PRIMARY KEY(task_id, prerequisite_id), CHECK(task_id != prerequisite_id)
        );
        CREATE TABLE criterion (
          task_id TEXT NOT NULL REFERENCES task(id), version INTEGER NOT NULL,
          criterion_id TEXT NOT NULL, description TEXT NOT NULL, required INTEGER NOT NULL,
          PRIMARY KEY(task_id, version, criterion_id)
        );
        CREATE TABLE evidence (
          id TEXT NOT NULL, version TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES project(id),
          description TEXT NOT NULL, status TEXT NOT NULL, observed_at TEXT NOT NULL,
          PRIMARY KEY(id, version)
        );
        CREATE TABLE review (
          id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES task(id),
          criteria_version INTEGER NOT NULL, kind TEXT NOT NULL, conclusion TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL, results TEXT NOT NULL
        );
        CREATE TABLE activity (
          id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
          task_id TEXT REFERENCES task(id), action TEXT NOT NULL, actor TEXT NOT NULL,
          created_at TEXT NOT NULL, summary TEXT NOT NULL, revision INTEGER
        );
        CREATE TABLE request_log (
          request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL
        );
        PRAGMA user_version=1;
        COMMIT;
        """)
        if version < 2:
            db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE index_workspace (
              project_id TEXT PRIMARY KEY REFERENCES project(id), root TEXT NOT NULL
            );
            CREATE TABLE artifact (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
              kind TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE artifact_location (
              artifact_id TEXT NOT NULL REFERENCES artifact(id), path TEXT NOT NULL,
              PRIMARY KEY(artifact_id,path), UNIQUE(path, artifact_id)
            );
            CREATE TABLE artifact_revision (
              artifact_id TEXT NOT NULL REFERENCES artifact(id), file_sha256 TEXT NOT NULL,
              content_id TEXT, content_sha256 TEXT, metadata TEXT NOT NULL,
              created_at TEXT NOT NULL,
              PRIMARY KEY(artifact_id,file_sha256)
            );
            CREATE TABLE index_scan (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
              started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, error TEXT
            );
            CREATE TABLE index_observation (
              scan_id TEXT NOT NULL REFERENCES index_scan(id),
              artifact_id TEXT NOT NULL REFERENCES artifact(id), path TEXT NOT NULL,
              status TEXT NOT NULL, file_sha256 TEXT, error TEXT, observed_at TEXT NOT NULL,
              PRIMARY KEY(scan_id,artifact_id,path)
            );
            CREATE TABLE published_index (
              project_id TEXT PRIMARY KEY REFERENCES project(id),
              scan_id TEXT NOT NULL REFERENCES index_scan(id)
            );
            PRAGMA user_version=2;
            COMMIT;
            """)
        if version < 3:
            db.executescript("""
            BEGIN IMMEDIATE;
            ALTER TABLE project ADD COLUMN focus_task_id TEXT REFERENCES task(id);
            CREATE TABLE decision (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
              revision INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE decision_revision (
              decision_id TEXT NOT NULL REFERENCES decision(id), revision INTEGER NOT NULL,
              title TEXT NOT NULL, background TEXT NOT NULL, conclusion TEXT NOT NULL,
              rationale TEXT NOT NULL, impact TEXT NOT NULL, source TEXT NOT NULL,
              supersedes TEXT, actor TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(decision_id,revision)
            );
            CREATE TABLE task_decision (
              task_id TEXT NOT NULL REFERENCES task(id),
              decision_id TEXT NOT NULL REFERENCES decision(id),
              impact TEXT NOT NULL, PRIMARY KEY(task_id,decision_id)
            );
            PRAGMA user_version=3;
            COMMIT;
            """)
        if version < 4:
            db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE foundation_import (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
              format TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
              actor TEXT NOT NULL, original BLOB NOT NULL, report TEXT NOT NULL,
              status TEXT NOT NULL, UNIQUE(project_id, format, sha256)
            );
            CREATE TABLE foundation_record (
              project_id TEXT NOT NULL REFERENCES project(id), kind TEXT NOT NULL,
              legacy_id TEXT NOT NULL, revision INTEGER NOT NULL, content TEXT NOT NULL,
              import_id TEXT NOT NULL REFERENCES foundation_import(id),
              created_at TEXT NOT NULL,
              PRIMARY KEY(project_id,kind,legacy_id,revision)
            );
            PRAGMA user_version=4;
            COMMIT;
            """)
        if version < 5:
            db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE model_run (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
              revision INTEGER NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE model_run_revision (
              run_id TEXT NOT NULL REFERENCES model_run(id), revision INTEGER NOT NULL,
              content TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(run_id, revision)
            );
            PRAGMA user_version=5;
            COMMIT;
            """)
        if version < 6:
            db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE research_record (
              project_id TEXT NOT NULL REFERENCES project(id), kind TEXT NOT NULL,
              id TEXT NOT NULL, revision INTEGER NOT NULL, content TEXT NOT NULL,
              actor TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(project_id,kind,id,revision)
            );
            PRAGMA user_version=6;
            COMMIT;
            """)
        if version < 7:
            db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE prediction_job (
              id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES project(id),
              status TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
              actor TEXT NOT NULL, created_at TEXT NOT NULL, heartbeat TEXT,
              lease TEXT, pid INTEGER, error TEXT, result TEXT
            );
            CREATE TABLE prediction_event (
              id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES prediction_job(id),
              created_at TEXT NOT NULL, message TEXT NOT NULL
            );
            PRAGMA user_version=7;
            COMMIT;
            """)
    finally:
        db.close()


@contextmanager
def transaction(path: Path):
    if not Path(path).is_file():
        raise ValueError("workbench database does not exist; run migrate first")
    db = connect(path)
    try:
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ValueError("workbench schema requires migration")
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
