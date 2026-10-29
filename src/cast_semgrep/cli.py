"""Local command line entry point."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .cast import collect_cast, import_cast, latest_archive
from .config import load_settings
from .db import connect, initialize
from .matching import calculate_matches
from .semgrep import import_semgrep, local_checkout, sync_semgrep


def main() -> None:
    parser = argparse.ArgumentParser(description="CAST–Semgrep rules comparator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Create the local database")
    cast_sync = sub.add_parser("sync-cast", help="Archive CAST data and import it")
    cast_sync.add_argument("--refresh", action="store_true", help="Start a new collection")
    cast_sync.add_argument("--offline", action="store_true", help="Only import the local archive")
    sub.add_parser("import-cast", help="Rebuild CAST records from the local archive")
    semgrep_sync = sub.add_parser("sync-semgrep", help="Clone/fetch Semgrep rules and import them")
    semgrep_sync.add_argument("--refresh", action="store_true", help="Fetch the current develop revision")
    semgrep_sync.add_argument("--offline", action="store_true", help="Only import the local checkout")
    sub.add_parser("import-semgrep", help="Rebuild Semgrep records from the local checkout")
    match = sub.add_parser("match", help="Recalculate deterministic candidates")
    match.add_argument("--top-k", type=int, default=15)
    match.add_argument("--min-score", type=int, default=18)
    serve = sub.add_parser("serve", help="Start the local web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    schema = sub.add_parser("schema-mermaid", help="Generate a Mermaid ER diagram without reading database records")
    source = schema.add_mutually_exclusive_group()
    source.add_argument("--database", type=Path, help="Existing SQLite file (read-only; defaults to COMPARATOR_DB)")
    source.add_argument("--from-migrations", action="store_true", help="Generate from migrations in memory without a local database")
    schema.add_argument("--output", type=Path, help="Write to this file instead of standard output")
    schema.add_argument("--format", choices=("mermaid", "markdown"), default="mermaid")
    schema.add_argument("--tables-only", action="store_true", help="Exclude views")
    sub.add_parser("semantic-sync", help="Snapshot current rule titles/descriptions without generating embeddings")
    sub.add_parser("semantic-status", help="Show vector coverage by model")
    embed = sub.add_parser("embed-openai", help="Calculate and resume title/description vectors with OpenAI")
    embed.add_argument("--model", choices=("text-embedding-3-small", "text-embedding-3-large"), default="text-embedding-3-small")
    embed.add_argument("--dimensions", type=int)
    embed.add_argument("--revision", default="alias-v1", help="Local generation label; not a pinned OpenAI model revision")
    embed.add_argument("--batch-size", type=int, default=64)
    embed.add_argument("--limit", type=int, help="Maximum number of missing field vectors to compute")
    embed.add_argument("--dry-run", action="store_true", help="Count missing vectors without calling OpenAI")
    sub.add_parser("status", help="Show local import status")
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "embed-openai":
        import sys
        from .openai_embeddings import run_embeddings, EmbeddingError
        try:
            result = run_embeddings(settings, model=args.model, dimensions=args.dimensions, revision=args.revision,
                                    batch_size=args.batch_size, limit=args.limit, dry_run=args.dry_run,
                                    progress=lambda state: print(json.dumps(state), file=sys.stderr, flush=True))
        except EmbeddingError as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2))
        if result['oversized_fields'] or result['stale_vectors']:
            raise SystemExit(1)
    elif args.command == "schema-mermaid":
        from .schema_mermaid import generate_schema
        database = None if args.from_migrations else (args.database or settings.db_path)
        if database and args.output and args.output.resolve() == database.resolve():
            parser.error("The output must not overwrite the database")
        try:
            output = generate_schema(database=database, include_views=not args.tables_only, markdown=args.format == "markdown")
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(output, encoding="utf-8")
            else:
                print(output, end="")
        except (OSError, sqlite3.Error) as error:
            parser.error(f"Cannot generate schema: {error}. Use --from-migrations for an empty model.")
    elif args.command in ("semantic-sync", "semantic-status"):
        from .semantic import sync_documents, semantic_status
        with connect(settings.db_path) as conn:
            initialize(conn)
            added = sync_documents(conn) if args.command == "semantic-sync" else 0
            result = semantic_status(conn)
            if args.command == "semantic-sync":
                result["new_document_versions"] = added
        print(json.dumps(result, indent=2))
    elif args.command == "init":
        with connect(settings.db_path) as conn:
            initialize(conn)
        print(settings.db_path)
    elif args.command == "sync-cast":
        if args.offline:
            archive = latest_archive(settings.data_dir)
            if archive is None:
                parser.error("No CAST archive is available for offline import")
        else:
            archive = collect_cast(settings, refresh=args.refresh)
        print(json.dumps(import_cast(settings, archive), indent=2))
    elif args.command == "import-cast":
        print(json.dumps(import_cast(settings), indent=2))
    elif args.command == "sync-semgrep":
        if args.offline:
            if not (local_checkout(settings) / ".git").is_dir():
                parser.error("No Semgrep checkout is available for offline import")
        else:
            print(json.dumps(sync_semgrep(settings, refresh=args.refresh), indent=2))
        print(json.dumps(import_semgrep(settings), indent=2))
    elif args.command == "import-semgrep":
        print(json.dumps(import_semgrep(settings), indent=2))
    elif args.command == "match":
        print(json.dumps(calculate_matches(settings, top_k=args.top_k, min_score=args.min_score), indent=2))
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("cast_semgrep.api:app", host=args.host, port=args.port, reload=False)
    elif args.command == "status":
        with connect(settings.db_path) as conn:
            initialize(conn)
            counts = {row["source"]: row["count"] for row in conn.execute(
                "SELECT source,COUNT(*) AS count FROM rules WHERE status='present' GROUP BY source"
            )}
            snapshots = [dict(row) for row in conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 4")]
            candidate_count = conn.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0]
        for snapshot in snapshots:
            snapshot["stats"] = json.loads(snapshot.pop("stats_json"))
        print(json.dumps({"rules": counts, "candidates": candidate_count, "snapshots": snapshots}, indent=2))


if __name__ == "__main__":
    main()
