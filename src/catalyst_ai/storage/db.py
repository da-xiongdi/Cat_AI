from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from catalyst_ai.storage.models import Base


def engine_for(path: Path, *, initialize: bool = False):
    if initialize:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise ValueError("数据库不存在，请先运行init或ingest")
    engine = create_engine("sqlite:///" + path.resolve().as_posix(), poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    if initialize:
        Base.metadata.create_all(engine)
    return engine


@contextmanager
def transaction(path: Path, *, initialize=False):
    engine = engine_for(path, initialize=initialize)
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            yield session
    finally:
        engine.dispose()
