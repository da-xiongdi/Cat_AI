from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceDocumentRow(Base):
    __tablename__ = "source_document"
    id: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ExtractionRow(Base):
    __tablename__ = "extraction_record"
    id: Mapped[str] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.id"))
    payload: Mapped[dict] = mapped_column(JSON)


class RecipeRow(Base):
    __tablename__ = "catalyst_recipe"
    id: Mapped[str] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)


class SynthesisRow(Base):
    __tablename__ = "synthesis_run"
    id: Mapped[str] = mapped_column(primary_key=True)
    recipe_id: Mapped[str] = mapped_column(ForeignKey("catalyst_recipe.id"))
    payload: Mapped[dict] = mapped_column(JSON)


class TestRow(Base):
    __test__ = False
    __tablename__ = "test_run"
    id: Mapped[str] = mapped_column(primary_key=True)
    synthesis_id: Mapped[str] = mapped_column(ForeignKey("synthesis_run.id"))
    payload: Mapped[dict] = mapped_column(JSON)


class ObservationRow(Base):
    __tablename__ = "performance_observation"
    id: Mapped[str] = mapped_column(primary_key=True)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_run.id"))
    payload: Mapped[dict] = mapped_column(JSON)


class CharacterizationRow(Base):
    __tablename__ = "characterization"
    id: Mapped[str] = mapped_column(primary_key=True)
    synthesis_id: Mapped[str] = mapped_column(ForeignKey("synthesis_run.id"))
    payload: Mapped[dict] = mapped_column(JSON)


class ImportRunRow(Base):
    __tablename__ = "import_run"
    id: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[str]
    input_sha256: Mapped[str]
    input_name: Mapped[str]
    metadata_json: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)


class StagedRow(Base):
    __tablename__ = "staged_record"
    id: Mapped[str] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("import_run.id"))
    input_locator: Mapped[str]
    fingerprint: Mapped[str] = mapped_column(index=True)
    dataset_kind: Mapped[str]
    status: Mapped[str]
    raw_payload: Mapped[dict | list | str | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    issues: Mapped[list] = mapped_column(JSON)


class RevisionRow(Base):
    __tablename__ = "record_revision"
    id: Mapped[str] = mapped_column(ForeignKey("staged_record.id"), primary_key=True)
    parent_record_id: Mapped[str] = mapped_column(ForeignKey("staged_record.id"), unique=True)
    request_sha256: Mapped[str]
    details: Mapped[dict] = mapped_column(JSON)


class CuratedRow(Base):
    __tablename__ = "curated_record"
    id: Mapped[str] = mapped_column(ForeignKey("staged_record.id"), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.id"))
    extraction_id: Mapped[str] = mapped_column(ForeignKey("extraction_record.id"))
    recipe_id: Mapped[str] = mapped_column(ForeignKey("catalyst_recipe.id"))
    synthesis_id: Mapped[str] = mapped_column(ForeignKey("synthesis_run.id"))
    test_id: Mapped[str] = mapped_column(ForeignKey("test_run.id"))
    dataset_kind: Mapped[str]
    review_status: Mapped[str] = mapped_column(String, default="pending")


class ReviewRow(Base):
    __tablename__ = "review_event"
    id: Mapped[str] = mapped_column(primary_key=True)
    record_id: Mapped[str] = mapped_column(ForeignKey("curated_record.id"))
    reviewer: Mapped[str]
    decision: Mapped[str]
    evidence: Mapped[str]
    created_at: Mapped[str]
    payload_sha256: Mapped[str]
    metadata_json: Mapped[dict] = mapped_column(JSON)


class SnapshotRow(Base):
    __tablename__ = "dataset_snapshot"
    __table_args__ = (UniqueConstraint("content_sha256"),)
    id: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[str]
    content_sha256: Mapped[str]
    manifest: Mapped[dict] = mapped_column(JSON)
