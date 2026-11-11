# Actual change inventory

The initial A+B delivery added the files in the inventory below. There was no pre-existing code to overwrite at that time. Later documentation changes are listed separately at the end.
The original development guide remains unchanged:

- `docs/architecture/AI_CO2_MeOH_Catalyst_Development_Guide_v0.2.md`

Current implementation and research status is summarized in [progress.md](progress.md). Earlier inventory entries describe their delivery date and do not represent the current database or model state.

## New project files and acceptance evidence

- `.env.example`
- `.gitignore`
- `.python-version`
- `README.md`
- `artifacts/reports/acceptance/cli_smoke.json`
- `artifacts/reports/acceptance/manifest.json`
- `artifacts/reports/acceptance/pytest.txt`
- `artifacts/reports/acceptance/pytest.xml`
- `artifacts/reports/acceptance/quality_report.json`
- `artifacts/reports/acceptance/quality_report.txt`
- `artifacts/reports/acceptance/quality_revalidated.json`
- `artifacts/reports/acceptance/quality_revalidated.txt`
- `artifacts/reports/acceptance/ruff.txt`
- `artifacts/reports/acceptance/wheel_install.txt`
- `configs/data_schema.yaml`
- `configs/project.yaml`
- `data/examples/synthetic_demo.csv`
- `data/examples/synthetic_demo.json`
- `docs/api_contracts.md`
- `docs/change_inventory.md`
- `docs/data_dictionary.md`
- `docs/decisions.md`
- `docs/progress.md`
- `docs/project_development_guide.md`
- `docs/source_audit.md`
- `pyproject.toml`
- `scripts/generate_demo.py`
- `scripts/generate_schema.py`
- `scripts/smoke_test.py`
- `src/catalyst_ai/__init__.py`
- `src/catalyst_ai/cli.py`
- `src/catalyst_ai/config.py`
- `src/catalyst_ai/governance/__init__.py`
- `src/catalyst_ai/governance/quality.py`
- `src/catalyst_ai/ingest.py`
- `src/catalyst_ai/interfaces.py`
- `src/catalyst_ai/reporting/__init__.py`
- `src/catalyst_ai/reporting/evidence.py`
- `src/catalyst_ai/review.py`
- `src/catalyst_ai/schemas/__init__.py`
- `src/catalyst_ai/schemas/domain.py`
- `src/catalyst_ai/sources/__init__.py`
- `src/catalyst_ai/sources/files.py`
- `src/catalyst_ai/storage/__init__.py`
- `src/catalyst_ai/storage/db.py`
- `src/catalyst_ai/storage/entities.py`
- `src/catalyst_ai/storage/models.py`
- `src/catalyst_ai/storage/snapshots.py`
- `tests/conftest.py`
- `tests/integration/test_cli.py`
- `tests/integration/test_ingest.py`
- `tests/integration/test_snapshot.py`
- `tests/unit/test_adapters.py`
- `tests/unit/test_boundaries.py`
- `tests/unit/test_contracts.py`
- `tests/unit/test_quality.py`
- `uv.lock`

## Local generated runtime files (ignored by version control)

- `data/raw/bd0864e39a040731645b3a6a8d90009bba99885917e411ebe27d95ba7e251170.csv`
- `data/staged/7b0e94cb01574237989e9f42f75cecfd.json`
- `data/curated/7b0e94cb01574237989e9f42f75cecfd.json`
- `data/catalog.sqlite`: one synthetic_demo record, pending; zero research approvals/snapshots.
- `dist/catalyst_ai-0.1.0-py3-none-any.whl`
- `dist/catalyst_ai-0.1.0.tar.gz`
- `.venv/`: development environment; `build/wheel-check/`: independent wheel installation.

Third-party environment files, caches and build intermediates are not individually listed.
Software verification evidence: docs/progress.md and artifacts/reports/acceptance/manifest.json.
Scientific results: none.

## 2026-11-09: paper-review integration documentation

- Added `docs/implementation_amendment.md`: mapping to existing tasks, ordered implementation slices, compatibility boundaries and acceptance criteria; all algorithm work remains planned.
- Updated `README.md`, `docs/progress.md`, `docs/decisions.md` and this inventory to connect the plan to ongoing work and preserve the historical acceptance status.
- Updated the existing `docs/Yan2026_Repository_Architecture_Review_and_Codex_Amendment.md` with implementation context, corrected execution paths and incremental task instructions.
- No changes to the baseline development guides, Python code, tests, configuration, database or historical acceptance reports. No new scientific results.

## 2026-11-09: I1 target eligibility delivery

- Added `src/catalyst_ai/datasets/__init__.py` and `src/catalyst_ai/datasets/eligibility.py` for explicit target eligibility, observation context, evidence checks, coverage and snapshot association receipts.
- Updated `src/catalyst_ai/cli.py` with dataset qualify; the existing dataset build and storage/snapshots.py remain unchanged.
- Added `tests/integration/test_eligibility.py` (20 cases including parameterized cases); extended `scripts/smoke_test.py` with pending-qualification and empty-freeze checks.
- Updated README, api_contracts, implementation_amendment, progress, decisions and this inventory with implemented behavior, evidence and limitations.
- Added `artifacts/reports/i1-20261109/`: pytest.xml, pytest.txt, ruff.txt, format.txt, smoke.txt, cli_smoke.json, manifest.json, workspace_pending_qualification.json and workspace_pending_qualification.txt.
- Verification: 75 pytest cases passed, ruff passed, 33 files formatted, 16 CLI smoke steps passed. All successful approval/freeze tests use isolated synthetic fixtures. The workspace demo remains pending; no research records, approvals, snapshots or scientific results were added.

## 2026-11-10: TheMeCat supplied materials and implementation plan

- Archived the supplied Markdown and pandas script byte-for-byte in `docs/references/themecat/`, with a reference index and hash receipt.
- Added `docs/themecat_implementation_plan.md`: evidence reconciliation, all 25 input fields, existing architecture mapping, B1–B4 prerequisites, I2–I5 dependencies and acceptance criteria.
- Added standard-library `scripts/validate_themecat.py` and boundary tests in `tests/unit/test_themecat_audit.py`; the archived script is not the production audit entry point.
- Updated README, implementation_amendment, data_dictionary, themecat_v1_audit, api_contracts, decisions, progress and this inventory to link the coordinated route and distinguish planned contracts from current behavior.
- New evidence is under `artifacts/reports/themecat-20261110/`; actual checks are recorded in progress and validation_manifest.json. Existing database, raw files, baseline guides and historical acceptance evidence are preserved. No model, candidate, research approval or research snapshot was created.

## 2026-11-10: current progress and research entry documentation

- Updated `docs/progress.md` with the A–F stage mapping, current data/model evidence, the preceding status-check results (106 tests passed, ruff and formatting passed), outstanding acceptance requirements and a proposed composition-versus-conditions research slice.
- Synchronized `docs/themecat_implementation_plan.md`, `docs/implementation_amendment.md` and `README.md`: B0–B2 and B4/I1 have run; I2 paper grouping, I3 features, I4 exploratory CO2-conversion baselines and I5 initial diagnostics have run. B3 remains deferred; published-source acceptance and the pressure assumption are not manual row verification.
- Recorded that E has an initial screening interface and exploratory compositions, while formal experimental recommendations, batch workflows and F feedback remain unfinished. Next-step research tasks are plans, not newly executed analyses.
- Documentation only: no Python, baseline guide, raw data, database, snapshot, model or historical report changes; no new review approvals, training, screening or experiments. Documentation links and baseline guide hashes are checked separately from prior software tests.

## 2026-11-10: upstream priority clarification

- Updated progress, TheMeCat plan, implementation amendment and README to reflect the user's reiterated priority: improve feature engineering, predictive modeling/evaluation and an independent prediction entry point before downstream screening or experiments.
- Added ADR-015 in `docs/decisions.md`: Extra Trees is the selected model for the initial baseline run, not the final platform model; feature/model selection remains open and E/F remain later-stage work.
- Documentation only; no new feature implementation, training, prediction, screening or experimental result is claimed.
