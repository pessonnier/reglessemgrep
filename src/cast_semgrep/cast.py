"""CAST Rules API collector and offline archive importer.

The current site exposes JSON beneath /api. Login follows its documented web
form; no session cookie, username, or password is written to the archive.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .config import Settings
from .db import connect, create_snapshot, initialize, upsert_rules
from .normalization import canonical_owasp


BASE = "https://technologies.castsoftware.com"
USER_AGENT = "cast-semgrep-comparator/0.1 (personal rules inventory)"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class CastClient:
    def __init__(self, interval: float = 0.35):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.interval = interval
        self.last_request = 0.0

    def _wait(self) -> None:
        remaining = self.interval - (time.monotonic() - self.last_request)
        if remaining > 0:
            time.sleep(remaining)
        self.last_request = time.monotonic()

    def _open(self, path: str, *, form: dict[str, str] | None = None) -> bytes:
        data = urlencode(form).encode("utf-8") if form is not None else None
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html"}
        if form is not None:
            headers.update({"Content-Type": "application/x-www-form-urlencoded", "HX-Request": "true"})
        request = Request(BASE + path, data=data, headers=headers)
        last_error: Exception | None = None
        for attempt in range(4):
            self._wait()
            try:
                with self.opener.open(request, timeout=25) as response:
                    return response.read()
            except HTTPError as error:
                last_error = error
                if error.code not in (429, 500, 502, 503, 504):
                    break
            except (URLError, TimeoutError) as error:
                last_error = error
            if attempt < 3:
                time.sleep(min(8, 2**attempt))
        raise RuntimeError(f"CAST request failed: {path} ({type(last_error).__name__})") from last_error

    def get_json(self, path: str) -> dict:
        result = json.loads(self._open(path))
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected CAST response at {path}")
        return result

    def login(self, username: str, password: str) -> bool:
        # The site's own form posts these exact names; xpwd is base64 encoded by
        # its JavaScript before submission. HTTPS protects the request in transit.
        self._open("/api/sso/authenticate", form={
            "uid": username,
            "xtkn": "tokex",
            "xpwd": base64.b64encode(password.encode("utf-8")).decode("ascii"),
        })
        index = self.get_json("/api/quality-rules")
        first = next((item for item in index.get("qualityRules", []) if item.get("id") is not None), None)
        if first is None:
            return False
        probe = self.get_json(f"/api/quality-rules/{first['id']}")
        return "technicalCriteria" in probe or "qualityStandards" in probe


def latest_archive(data_dir: Path, *, auth_mode: str | None = None) -> Path | None:
    cast_dir = data_dir / "cast"
    if not cast_dir.is_dir():
        return None
    for directory in sorted((p for p in cast_dir.iterdir() if p.is_dir()), reverse=True):
        manifest_file = directory / "manifest.json"
        if not manifest_file.is_file():
            continue
        manifest = _read_json(manifest_file)
        if auth_mode is None or manifest.get("auth_mode") == auth_mode:
            return directory
    return None


def collect_cast(settings: Settings, *, refresh: bool = False, progress=print) -> Path:
    wanted_mode = "authenticated" if settings.cast_credentials_available else "public"
    existing = latest_archive(settings.data_dir, auth_mode=wanted_mode)
    if existing and not refresh:
        manifest = _read_json(existing / "manifest.json")
        if manifest.get("status") == "complete":
            progress(f"CAST: using complete local archive {existing}")
            return existing

    client = CastClient(settings.cast_request_interval)
    auth_mode = "public"
    if settings.cast_credentials_available:
        try:
            if client.login(settings.cast_username, settings.cast_password):
                auth_mode = "authenticated"
                progress("CAST: authenticated session established")
            else:
                progress("CAST: authentication did not expose the extended fields; using public data")
        except Exception as error:
            progress(f"CAST: authentication unavailable ({type(error).__name__}); using public data")

    archive = existing if existing and auth_mode == wanted_mode and not refresh else None
    if archive is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive = settings.data_dir / "cast" / f"{stamp}-{auth_mode}"
    archive.mkdir(parents=True, exist_ok=True)
    index_file = archive / "index.json"
    technologies_file = archive / "technologies.json"
    if not index_file.exists() or refresh:
        try:
            _write_json(index_file, client.get_json("/api/quality-rules"))
            _write_json(technologies_file, client.get_json("/api/aip/technologies"))
        except Exception:
            if existing and (existing / "index.json").exists():
                progress(f"CAST: network unavailable; using local archive {existing}")
                return existing
            raise
    index = _read_json(index_file)
    items = index.get("qualityRules", [])
    if not isinstance(items, list):
        raise ValueError("CAST index has no qualityRules list")

    rules_dir = archive / "rules"
    errors: list[dict[str, str]] = []
    total = len(items)
    for offset, item in enumerate(items, 1):
        rule_id = str(item.get("id", ""))
        if not rule_id:
            errors.append({"id": "", "reason": "index entry has no id"})
            continue
        target = rules_dir / f"{rule_id}.json"
        if not target.exists():
            try:
                _write_json(target, client.get_json(f"/api/quality-rules/{rule_id}"))
            except Exception as error:
                errors.append({"id": rule_id, "reason": type(error).__name__})
        if offset % 100 == 0 or offset == total:
            completed = sum(1 for entry in items if (rules_dir / f"{entry.get('id')}.json").exists())
            _write_json(archive / "manifest.json", {
                "source": BASE,
                "index_url": BASE + "/api/quality-rules",
                "auth_mode": auth_mode,
                "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "complete" if completed == total else "partial",
                "listed": total,
                "archived_details": completed,
                "errors": errors,
            })
            progress(f"CAST: archived {completed}/{total} rule details")
    return archive


def _names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item.get("name")) for item in value if isinstance(item, dict) and item.get("name")})


def _references(value: object, standard: str) -> list[str]:
    if not isinstance(value, list):
        return []
    result: set[str] = set()
    for item in value:
        if isinstance(item, dict) and str(item.get("standard", "")).upper() == standard:
            if item.get("id"):
                result.add(str(item["id"]))
    return canonical_owasp(result) if standard == "OWASP" else sorted(result)


def normalize_cast(item: dict, detail: dict, archive: Path, revision: str) -> dict:
    rule_id = str(item["id"])
    standards = detail.get("qualityStandards") or []
    business = _names(detail.get("businessCriteria"))
    technology = _names(detail.get("technologies")) or [str(x) for x in item.get("technologies", [])]
    category = next((name for name in business if name.lower() in {
        "security", "performance", "robustness", "architecture", "maintainability", "reliability",
    }), None)
    return {
        "rule_key": f"CAST:{rule_id}", "source": "CAST", "rule_id": rule_id,
        "title": detail.get("name") or item.get("name"),
        "description": detail.get("description"),
        "rationale": detail.get("rationale"),
        "remediation": detail.get("remediation"),
        "severity": str(detail["severity"]) if detail.get("severity") is not None else None,
        "category": category,
        "classification_origin": "CAST" if category else "unknown",
        "categories_json": json.dumps(business, ensure_ascii=False),
        "languages_json": json.dumps(technology, ensure_ascii=False),
        "frameworks_json": "[]",
        "technologies_json": json.dumps(technology, ensure_ascii=False),
        "cwe_json": json.dumps(_references(standards, "CWE")),
        "owasp_json": json.dumps(_references(standards, "OWASP")),
        "owasp_raw_json": json.dumps(sorted({str(x.get("id")) for x in standards if isinstance(x, dict) and str(x.get("standard", "")).upper() == "OWASP" and x.get("id")}), ensure_ascii=False),
        "standards_json": json.dumps(sorted({str(x.get("standard")) + ":" + str(x.get("id")) for x in standards if isinstance(x, dict) and x.get("standard") and x.get("id")})),
        "detection_method": None,
        "source_url": BASE + f"/api/quality-rules/{rule_id}",
        "source_version": revision,
        "raw_path": str(archive / "rules" / f"{rule_id}.json"),
    }


def import_cast(settings: Settings, archive: Path | None = None) -> dict:
    archive = archive or latest_archive(settings.data_dir)
    if archive is None:
        raise FileNotFoundError("No local CAST archive. Run sync-cast first.")
    manifest = _read_json(archive / "manifest.json")
    index = _read_json(archive / "index.json")
    revision = archive.name
    rules = []
    missing = []
    for item in index.get("qualityRules", []):
        detail_path = archive / "rules" / f"{item.get('id')}.json"
        if not detail_path.is_file():
            missing.append(str(item.get("id")))
            continue
        rules.append(normalize_cast(item, _read_json(detail_path), archive, revision))
    if not rules:
        raise ValueError("CAST archive contains no rule details")
    stats = {"listed": len(index.get("qualityRules", [])), "imported": len(rules), "missing": len(missing)}
    with connect(settings.db_path) as conn:
        initialize(conn)
        snapshot_id = create_snapshot(
            conn, source="CAST", revision=revision, archive_path=archive,
            auth_mode=manifest.get("auth_mode", "public"),
            status="complete" if not missing else "partial", stats=stats,
        )
        upsert_rules(conn, rules, source="CAST", snapshot_id=snapshot_id, mark_missing=not missing)
    return stats
