"""Migrate, validate, import, query and report feature catalogs."""

import argparse
import json
from pathlib import Path

from catalyst_ai.reporting.evidence import write_json
from catalyst_ai.sources.files import strict_json
from catalyst_ai.storage.feature_catalog import (
    coverage,
    get_catalog,
    get_evidence,
    import_catalog,
    import_evidence,
    migrate,
    query_entries,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    load = commands.add_parser("import")
    load.add_argument("input", type=Path)
    load.add_argument("--commit", action="store_true", help="persist; default is dry-run")
    query = commands.add_parser("query")
    query.add_argument("kind", choices=("properties", "species"))
    query.add_argument("version")
    query.add_argument("--identity", help="species or element:property; returns indexed facts")
    evidence = commands.add_parser("import-evidence")
    evidence.add_argument("input", type=Path)
    evidence.add_argument("--commit", action="store_true")
    evidence_query = commands.add_parser("query-evidence")
    evidence_query.add_argument("version")
    report = commands.add_parser("coverage")
    report.add_argument("--snapshot", type=Path, required=True)
    report.add_argument("--properties", required=True)
    report.add_argument("--species", required=True)
    report.add_argument("--output", type=Path, required=True)
    qualification = commands.add_parser("qualify", help="formal data/mapping qualification")
    for name in ("snapshot", "qualification", "split", "output"):
        qualification.add_argument("--" + name, type=Path, required=True)
    for name in ("properties", "species", "review"):
        qualification.add_argument("--" + name, required=True)
    qualification.add_argument("--evidence-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.command == "migrate":
        result = {"integrity_check": migrate(args.database)}
        if result["integrity_check"] != "ok":
            raise ValueError("database integrity check failed")
    elif args.command == "import":
        result = import_catalog(args.database, args.input, dry_run=not args.commit)
    elif args.command == "query":
        result = query_entries(args.database, args.kind, args.version, args.identity)
    elif args.command == "import-evidence":
        result = import_evidence(args.database, args.input, dry_run=not args.commit)
    elif args.command == "query-evidence":
        result = get_evidence(args.database, args.version)
    elif args.command == "qualify":
        from catalyst_ai.features.qualification import qualify

        result = qualify(
            strict_json(args.snapshot.read_text(encoding="utf-8-sig")),
            strict_json(args.qualification.read_text(encoding="utf-8-sig")),
            strict_json(args.split.read_text(encoding="utf-8-sig")),
            get_catalog(args.database, "properties", args.properties),
            get_catalog(args.database, "species", args.species),
            get_evidence(args.database, args.review),
            root=args.evidence_root,
        )
        write_json(args.output, result)
    else:
        result = coverage(
            strict_json(args.snapshot.read_text(encoding="utf-8-sig")),
            get_catalog(args.database, "properties", args.properties),
            get_catalog(args.database, "species", args.species),
        )
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
