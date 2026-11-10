from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID = Annotated[str, Field(min_length=1, pattern=r"^\S+$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=False)


class ValueState(StrEnum):
    REPORTED = "reported"
    ZERO = "zero"
    UNKNOWN = "unknown"
    NOT_REPORTED = "not_reported"
    NOT_APPLICABLE = "not_applicable"
    NOT_MEASURED = "not_measured"
    INVALID = "invalid"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class Measurement(Contract):
    # Raw numeric text is deliberately not coerced, so decimal formatting survives.
    raw_value: str | None = None
    raw_unit: str | None = None
    state: ValueState = ValueState.NOT_REPORTED
    normalized_value: float | None = None
    normalized_unit: str | None = None
    definition: str | None = None
    source_locator: ID | None = None
    extraction_status: ReviewStatus = ReviewStatus.PENDING
    quality_flags: list[str] = Field(default_factory=list)
    uncertainty: str | None = None
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def state_consistency(self):
        if self.state in {ValueState.REPORTED, ValueState.ZERO} and self.raw_value is None:
            raise ValueError("reported/zero requires raw_value")
        if self.state not in {ValueState.REPORTED, ValueState.ZERO, ValueState.INVALID}:
            if self.raw_value is not None:
                raise ValueError("missing/unknown states require null raw_value")
        return self


class SourceDocument(Contract):
    source_id: ID
    kind: Literal["literature", "internal"]
    title: str = Field(min_length=1)
    doi: str | None = None
    year: int | None = Field(default=None, ge=1800, le=2200)
    internal_reference: str | None = None
    license: str = "unknown"
    access: str = "unspecified"
    file_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ExtractionRecord(Contract):
    extraction_id: ID
    source_id: ID
    locator: str = Field(min_length=1)
    method: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    original_excerpt: str | None = None
    status: ReviewStatus = ReviewStatus.PENDING


class Component(Contract):
    species: str = Field(min_length=1)
    role: Literal["element", "compound", "support", "promoter", "gas"]
    amount: Measurement


class Recipe(Contract):
    recipe_id: ID
    material_family: str = Field(min_length=1)
    composition_basis: Literal["wt_pct", "mol_pct", "atomic_pct", "ratio", "unknown"]
    composition_scope: str | None = None
    components: list[Component] = Field(min_length=1)
    supports: list[str] = Field(default_factory=list)
    promoters: list[str] = Field(default_factory=list)


class SynthesisStep(Contract):
    name: str = Field(min_length=1)
    parameters: dict[str, Measurement] = Field(default_factory=dict)
    atmosphere: str | None = None


class SynthesisRun(Contract):
    synthesis_id: ID
    recipe_id: ID
    route: str | None = None
    precursors: list[str] = Field(default_factory=list)
    steps: list[SynthesisStep] = Field(default_factory=list)
    batch_label: str | None = None


class GHSVBasis(Contract):
    """Reported flow reference conditions, not an assumed universal standard state."""

    reference_temperature: Measurement = Field(default_factory=Measurement)
    reference_pressure: Measurement = Field(default_factory=Measurement)
    reference_pressure_type: Literal["absolute", "gauge", "unknown"] = "unknown"
    catalyst_volume_basis: Literal["packed_bed", "catalyst_solid", "unknown"] = "unknown"
    description: str | None = None


class TestRun(Contract):
    __test__ = False
    test_id: ID
    synthesis_id: ID
    reactor: str | None = None
    temperature: Measurement = Field(default_factory=Measurement)
    pressure: Measurement = Field(default_factory=Measurement)
    pressure_type: Literal["absolute", "gauge", "unknown"] = "unknown"
    ghsv: Measurement = Field(default_factory=Measurement)
    ghsv_basis: GHSVBasis | None = None
    feed_basis: Literal["mol_pct", "vol_pct", "ratio", "unknown"] = "unknown"
    feed: list[Component] = Field(default_factory=list)
    catalyst_mass: Measurement = Field(default_factory=Measurement)
    dilution: str | None = None
    stabilization_time: Measurement = Field(default_factory=Measurement)
    time_on_stream: Measurement = Field(default_factory=Measurement)


class Observation(Contract):
    observation_id: ID
    test_id: ID
    metric: str = Field(min_length=1)
    value: Measurement
    time_on_stream: Measurement = Field(default_factory=Measurement)
    carbon_balance: Measurement = Field(default_factory=Measurement)


class Characterization(Contract):
    characterization_id: ID
    synthesis_id: ID
    technique: str = Field(min_length=1)
    properties: dict[str, Measurement]
    conditions: str | None = None


class ImportRecord(Contract):
    schema_version: Literal["1"] = "1"
    dataset_kind: Literal["synthetic_demo", "research"]
    source: SourceDocument | None = None
    extraction: ExtractionRecord | None = None
    recipe: Recipe
    synthesis: SynthesisRun
    test: TestRun
    observations: list[Observation] = Field(min_length=1)
    characterizations: list[Characterization] = Field(default_factory=list)

    @model_validator(mode="after")
    def relations(self):
        if self.synthesis.recipe_id != self.recipe.recipe_id:
            raise ValueError("synthesis.recipe_id mismatch")
        if self.test.synthesis_id != self.synthesis.synthesis_id:
            raise ValueError("test.synthesis_id mismatch")
        if any(o.test_id != self.test.test_id for o in self.observations):
            raise ValueError("observation.test_id mismatch")
        if any(c.synthesis_id != self.synthesis.synthesis_id for c in self.characterizations):
            raise ValueError("characterization.synthesis_id mismatch")
        if self.source and self.extraction and self.source.source_id != self.extraction.source_id:
            raise ValueError("extraction.source_id mismatch")
        for items, key in [
            (self.observations, "observation_id"),
            (self.characterizations, "characterization_id"),
        ]:
            ids = [getattr(item, key) for item in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {key}")
        return self


class SynthesisRunV2(SynthesisRun):
    initial_materials: list[str] = Field(default_factory=list)


class RecipeV2(Recipe):
    composition_available_raw: str | None = None
    composition_available: Literal["yes", "no", "unknown"] = "unknown"
    composition_definition_source: str | None = None
    orphan_amount_fields: list[str] = Field(default_factory=list)


class MassNormalizedFlow(Contract):
    value: Measurement = Field(default_factory=Measurement)
    reference_temperature: Measurement = Field(default_factory=Measurement)
    reference_pressure: Measurement = Field(default_factory=Measurement)
    reference_pressure_type: Literal["absolute", "gauge", "unknown"] = "unknown"
    mass_basis: Literal["catalyst", "unknown"] = "unknown"
    gas_scope: Literal["reactants_only", "unknown"] = "unknown"
    definition_source: str | None = None


class ReactantRatio(Contract):
    value: Measurement = Field(default_factory=Measurement)
    numerator: Literal["H2"] = "H2"
    denominator: Literal["CO2"] = "CO2"
    definition_source: str | None = None


class TestRunV2(TestRun):
    flow_mode: Literal["volume_ghsv", "mass_normalized_reactants"] = "volume_ghsv"
    mass_normalized_volume_flow: MassNormalizedFlow | None = None
    reactant_ratio: ReactantRatio | None = None


class ImportRecordV2(ImportRecord):
    schema_version: Literal["2"] = "2"
    recipe: RecipeV2
    synthesis: SynthesisRunV2
    test: TestRunV2


class ExperimentBatch(Contract):
    """Capacity contract only; no candidate recommendation or equipment control."""

    capacity: int = Field(default=4, ge=1, le=6, strict=True)
    candidate_ids: list[ID]

    @model_validator(mode="after")
    def slots(self):
        if len(self.candidate_ids) > self.capacity:
            raise ValueError("batch exceeds configured capacity")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("duplicate candidate ID; repeats require distinct planned sample IDs")
        return self
