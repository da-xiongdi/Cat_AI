"""Versioned, non-persistent contract for the first import preview."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Source(StrictModel):
    id: str
    path: str
    section: str
    role: Literal["document", "artifact"]
    note: str


class Criterion(StrictModel):
    description: str
    required: bool = True


class Task(StrictModel):
    id: str
    title: str
    goal: str
    milestone: Literal["S1-A", "S1-B", "S2", "S3"]
    stages: list[Literal["A", "B", "C", "D", "E", "F"]] = Field(min_length=1)
    primary_stage: Literal["A", "B", "C", "D", "E", "F"]
    status: Literal["planned", "ready", "in_progress", "in_review", "done", "blocked", "cancelled"]
    dependencies: list[str] = Field(default_factory=list)
    criteria: list[Criterion] = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
    owner: str | None = None
    planned_date: str | None = None

    @model_validator(mode="after")
    def primary_in_stages(self):
        if self.primary_stage not in self.stages:
            raise ValueError("primary stage must belong to stages")
        return self


class Difference(StrictModel):
    id: str
    summary: str
    sources: list[str] = Field(min_length=2)
    proposed_disposition: str


class ImportDraft(StrictModel):
    schema_version: Literal["1.0"]
    project_id: str
    sources: list[Source]
    tasks: list[Task]
    differences: list[Difference]

    @model_validator(mode="after")
    def references_valid(self):
        source_ids = {s.id for s in self.sources}
        tasks = {t.id: t for t in self.tasks}
        if len(source_ids) != len(self.sources) or len(tasks) != len(self.tasks):
            raise ValueError("duplicate source or task ID")
        for item in [*self.tasks, *self.differences]:
            if not set(item.sources) <= source_ids:
                raise ValueError("unknown source")

        def visit(task_id: str, stack: set[str]) -> None:
            if task_id in stack:
                raise ValueError("cyclic dependency")
            if task_id not in tasks:
                raise ValueError("unknown dependency")
            for dep in tasks[task_id].dependencies:
                visit(dep, stack | {task_id})

        for task_id in tasks:
            visit(task_id, set())
        return self
