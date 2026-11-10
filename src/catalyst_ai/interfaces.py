"""Future extension contracts. These protocols provide no scientific implementation."""

from typing import Protocol

from catalyst_ai.schemas.domain import ImportRecord


class DesignFeatureBuilder(Protocol):
    def build(self, record: ImportRecord) -> dict[str, float | str | None]:
        """A+B only; never include characterization or observed targets."""
        ...


class PerformancePredictor(Protocol):
    def predict(self, design_features: dict, *, snapshot_id: str) -> dict:
        """Require a validated model, uncertainty and applicability metadata."""
        ...


class CandidateRecommender(Protocol):
    def recommend(self, *, model_run_id: str, capacity: int = 4) -> list[dict]:
        """Future proposed candidates; capacity must obey ExperimentBatch."""
        ...
