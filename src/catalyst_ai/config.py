from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: Path = Path("data/catalog.sqlite")
    data_dir: Path = Path("data")
    report_dir: Path = Path("artifacts/reports")
    batch_capacity: int = Field(default=4, ge=1, le=6, strict=True)
    closure_tolerance_pct: float = Field(default=0.5, ge=0, le=5)
    governance_version: str = "1"


def load_settings(path: Path | None = None) -> Settings:
    return (
        Settings.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        if path
        else Settings()
    )
