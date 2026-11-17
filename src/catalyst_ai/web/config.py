"""Configuration for the local workbench server."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class WebSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace: str = "."
    database: str = "data/workbench.sqlite"
    project_id: str = Field(default="cat-ai", min_length=1)
    project_name: str = Field(default="Cat AI", min_length=1)
    port: int = Field(default=8765, ge=1024, le=65535)


def load(path: Path):
    path = path.resolve(strict=True)
    settings = WebSettings.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    )
    root = (path.parent / settings.workspace).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("workspace must be a directory")
    db = (root / settings.database).resolve()
    if not db.is_relative_to(root):
        raise ValueError("management database must be within workspace")
    return settings, root, db
