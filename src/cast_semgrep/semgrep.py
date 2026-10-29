"""Semgrep Community Edition Git archive and YAML rule importer."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import yaml

from .config import Settings
from .db import connect, create_snapshot, initialize, upsert_rules
from .normalization import canonical_owasp


REPOSITORY = "https://github.com/semgrep/semgrep-rules.git"
CWE_RE = re.compile(r"CWE-\d+", re.IGNORECASE)


def _git(*args: str, cwd: Path | None = None) -> str:
    command = ["git", *( ["-C", str(cwd)] if cwd else [] ), *args]
    return subprocess.run(command, text=True, capture_output=True, check=True).stdout.strip()


def local_checkout(settings: Settings) -> Path:
    return settings.data_dir / "semgrep" / "repo"


def sync_semgrep(settings: Settings, *, refresh: bool = False) -> dict:
    checkout = local_checkout(settings)
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not (checkout / ".git").exists():
        _git("clone", "--depth", "1", "--single-branch", REPOSITORY, str(checkout))
    elif refresh:
        if _git("status", "--porcelain", cwd=checkout):
            raise RuntimeError("Semgrep archive has local changes; refusing to replace them")
        _git("fetch", "--depth", "1", "origin", "develop", cwd=checkout)
        _git("checkout", "--detach", "FETCH_HEAD", cwd=checkout)
    revision = _git("rev-parse", "HEAD", cwd=checkout)
    yaml_files = sorted(p for p in checkout.rglob("*") if p.is_file() and p.suffix.lower() in (".yaml", ".yml") and ".git" not in p.parts)
    manifest = {
        "source": REPOSITORY, "revision": revision, "checkout": str(checkout),
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "yaml_files": len(yaml_files),
    }
    manifest_path = checkout.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [str(x) for x in value if isinstance(x, (str, int, float))]
    return []


def _refs(value: object, pattern: re.Pattern) -> list[str]:
    return sorted({x.upper() for item in _string_list(value) for x in pattern.findall(item)})


def normalize_semgrep(rule: dict, *, relative_path: str, checkout: Path, revision: str, duplicate_id: bool) -> dict:
    rule_id = str(rule["id"])
    metadata = rule.get("metadata") if isinstance(rule.get("metadata"), dict) else {}
    languages = _string_list(rule.get("languages"))
    technologies = _string_list(metadata.get("technology"))
    category = metadata.get("category") if isinstance(metadata.get("category"), str) else None
    key = f"Semgrep:{rule_id}@{relative_path}" if duplicate_id else f"Semgrep:{rule_id}"
    return {
        "rule_key": key,
        "source": "Semgrep",
        "rule_id": rule_id,
        "title": metadata.get("title") if isinstance(metadata.get("title"), str) else rule_id,
        "description": rule.get("message") if isinstance(rule.get("message"), str) else None,
        "rationale": None,
        "remediation": rule.get("fix") if isinstance(rule.get("fix"), str) else None,
        "severity": str(rule["severity"]) if rule.get("severity") is not None else None,
        "category": category,
        "classification_origin": "Semgrep" if category else "unknown",
        "categories_json": json.dumps(_string_list(metadata.get("category")), ensure_ascii=False),
        "languages_json": json.dumps(languages, ensure_ascii=False),
        "frameworks_json": json.dumps([x for x in technologies if x.lower() not in {v.lower() for v in languages}], ensure_ascii=False),
        "technologies_json": json.dumps(technologies, ensure_ascii=False),
        "cwe_json": json.dumps(_refs(metadata.get("cwe"), CWE_RE)),
        "owasp_json": json.dumps(canonical_owasp(_string_list(metadata.get("owasp")))),
        "owasp_raw_json": json.dumps(_string_list(metadata.get("owasp")), ensure_ascii=False),
        "standards_json": json.dumps(_string_list(metadata.get("standards")), ensure_ascii=False),
        "detection_method": str(rule.get("mode", "search")),
        "source_url": f"https://github.com/semgrep/semgrep-rules/blob/{revision}/{quote(relative_path)}",
        "source_version": revision,
        "raw_path": str(checkout / relative_path),
        "definition_hash": hashlib.sha256(json.dumps(rule, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest(),
        "source_confidence": str(metadata["confidence"]) if metadata.get("confidence") is not None else None,
    }


def import_semgrep(settings: Settings) -> dict:
    checkout = local_checkout(settings)
    if not (checkout / ".git").is_dir():
        raise FileNotFoundError("No local Semgrep checkout. Run sync-semgrep first.")
    revision = _git("rev-parse", "HEAD", cwd=checkout)
    yaml_files = sorted(p for p in checkout.rglob("*") if p.is_file() and p.suffix.lower() in (".yaml", ".yml") and ".git" not in p.parts)
    found: list[tuple[dict, str]] = []
    errors: list[dict[str, str]] = []
    files_with_rules = 0
    ignored_files = 0
    for path in yaml_files:
        relative = path.relative_to(checkout).as_posix()
        if path.name.endswith((".test.yaml", ".test.yml")):
            ignored_files += 1
            continue
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (UnicodeError, yaml.YAMLError) as error:
            errors.append({"file": relative, "kind": "parse", "reason": str(error)[:300]})
            continue
        file_has_rules = False
        for document in documents:
            if not isinstance(document, dict) or "rules" not in document:
                continue
            if not isinstance(document["rules"], list):
                errors.append({"file": relative, "kind": "structure", "reason": "rules is not a list"})
                continue
            for index, rule in enumerate(document["rules"]):
                if not isinstance(rule, dict):
                    errors.append({"file": relative, "kind": "rule", "reason": f"rules[{index}] is not an object"})
                    continue
                required = ("id", "message", "severity", "languages")
                missing = [key for key in required if not rule.get(key)]
                if missing or not isinstance(rule.get("id"), str) or not isinstance(rule.get("languages"), list):
                    errors.append({"file": relative, "kind": "rule", "reason": f"rules[{index}] lacks valid required fields: {', '.join(missing) or 'id/languages'}"})
                    continue
                found.append((rule, relative))
                file_has_rules = True
        if file_has_rules:
            files_with_rules += 1
    duplicate_counts = Counter(str(rule["id"]) for rule, _ in found)
    rules = [normalize_semgrep(rule, relative_path=path, checkout=checkout, revision=revision,
                               duplicate_id=duplicate_counts[str(rule["id"])] > 1)
             for rule, path in found]
    # A duplicate ID within the same file still needs a unique stable key.
    seen: Counter[str] = Counter()
    for rule in rules:
        seen[rule["rule_key"]] += 1
        if seen[rule["rule_key"]] > 1:
            rule["rule_key"] += f"#{seen[rule['rule_key']]}"
    stats = {
        "revision": revision, "yaml_files": len(yaml_files), "files_with_rules": files_with_rules,
        "rule_objects": len(found), "imported": len(rules), "duplicate_ids": sum(n-1 for n in duplicate_counts.values() if n > 1),
        "ignored_test_files": ignored_files, "errors": len(errors),
    }
    report_path = checkout.parent / "import-report.json"
    report_path.write_text(json.dumps({"stats": stats, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    with connect(settings.db_path) as conn:
        initialize(conn)
        snapshot_id = create_snapshot(conn, source="Semgrep", revision=revision, archive_path=checkout,
                                      status="partial" if errors else "complete", stats=stats)
        upsert_rules(conn, rules, source="Semgrep", snapshot_id=snapshot_id, mark_missing=not errors)
    return stats
