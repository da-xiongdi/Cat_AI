from catalyst_ai.storage.models import (
    CharacterizationRow,
    ExtractionRow,
    ObservationRow,
    RecipeRow,
    SourceDocumentRow,
    SynthesisRow,
    TestRow,
)


def entities(record):
    """Insertion order follows the foreign keys. Payloads are immutable by application policy."""
    yield SourceDocumentRow, record.source.source_id, record.source, {}
    yield (
        ExtractionRow,
        record.extraction.extraction_id,
        record.extraction,
        {"source_id": record.source.source_id},
    )
    yield RecipeRow, record.recipe.recipe_id, record.recipe, {}
    yield (
        SynthesisRow,
        record.synthesis.synthesis_id,
        record.synthesis,
        {"recipe_id": record.recipe.recipe_id},
    )
    yield TestRow, record.test.test_id, record.test, {"synthesis_id": record.synthesis.synthesis_id}
    for obs in record.observations:
        yield ObservationRow, obs.observation_id, obs, {"test_id": obs.test_id}
    for char in record.characterizations:
        yield (
            CharacterizationRow,
            char.characterization_id,
            char,
            {"synthesis_id": char.synthesis_id},
        )


def insert_entities(session, record):
    for cls, identifier, model, links in entities(record):
        if session.get(cls, identifier) is None:
            session.add(cls(id=identifier, payload=model.model_dump(mode="json"), **links))
            session.flush()
