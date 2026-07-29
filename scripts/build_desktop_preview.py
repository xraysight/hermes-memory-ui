#!/usr/bin/env python3
"""Build the development-only Hermes Memory UI provider-fixture preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "desktop" / "plugin.js"
DEFAULT_FIXTURES = ROOT / "tests" / "fixtures" / "providers"
DEFAULT_OUTPUT = ROOT / "build" / "desktop-preview" / "plugin.js"

REQUIRED_PROVIDERS = (
    "builtin",
    "holographic",
    "mem0",
    "honcho",
    "mnemosyne",
    "hindsight",
    "byterover",
)
REQUIRED_OPERATIONS = (
    "session_search",
    "hindsight_contents",
    "hindsight_recall",
    "hindsight_reflect",
    "mnemosyne_contents",
    "mnemosyne_recall",
    "mnemosyne_prefetch",
    "byterover_query",
)
REPLACEMENTS = {
    "const PLUGIN_ID = /* __PLUGIN_ID__ */ 'hermes-memory-ui'": (
        "const PLUGIN_ID = 'hermes-memory-ui-preview'"
    ),
    "const PLUGIN_NAME = /* __PLUGIN_NAME__ */ 'Hermes Memory UI'": (
        "const PLUGIN_NAME = 'Hermes Memory UI Preview'"
    ),
    "const PLUGIN_ROUTE = /* __PLUGIN_ROUTE__ */ '/memory'": (
        "const PLUGIN_ROUTE = '/memory-preview'"
    ),
}
CATALOG_MARKER = "export const PREVIEW_CATALOG = /* __PREVIEW_CATALOG__ */ null"

CASE_COLLECTION_MINIMUMS = {
    "normal": {
        "snapshot.builtin.stores": 2,
        "snapshot.builtin.stores.0.entries": 2,
        "snapshot.builtin.stores.1.entries": 2,
        "snapshot.holographic.facts": 6,
        "snapshot.holographic.categories": 3,
        "snapshot.mem0.memories": 6,
        "snapshot.honcho.user.card": 2,
        "snapshot.honcho.user.conclusions": 2,
        "snapshot.honcho.ai.card": 2,
        "snapshot.honcho.ai.conclusions": 2,
        "snapshot.honcho.search_results": 4,
        "snapshot.mnemosyne.memories": 5,
        "snapshot.mnemosyne.facts": 5,
        "snapshot.byterover.locations": 4,
        "snapshot.byterover.results": 6,
        "operations.session_search.results": 4,
        "operations.hindsight_contents.memories": 5,
        "operations.hindsight_contents.documents": 4,
        "operations.hindsight_recall.results": 5,
        "operations.mnemosyne_contents.memories": 5,
        "operations.mnemosyne_contents.facts": 5,
        "operations.mnemosyne_recall.results": 5,
        "operations.byterover_query.matched_docs": 3,
    },
    "long-content": {
        "snapshot.builtin.stores": 2,
        "snapshot.builtin.stores.0.entries": 3,
        "snapshot.builtin.stores.1.entries": 3,
        "snapshot.holographic.facts": 3,
        "snapshot.holographic.categories": 3,
        "snapshot.mem0.memories": 3,
        "snapshot.honcho.user.card": 3,
        "snapshot.honcho.user.conclusions": 3,
        "snapshot.honcho.ai.card": 3,
        "snapshot.honcho.ai.conclusions": 3,
        "snapshot.honcho.search_results": 3,
        "snapshot.mnemosyne.memories": 3,
        "snapshot.mnemosyne.facts": 3,
        "snapshot.byterover.locations": 3,
        "snapshot.byterover.results": 3,
        "operations.session_search.results": 3,
        "operations.hindsight_contents.memories": 3,
        "operations.hindsight_contents.documents": 3,
        "operations.hindsight_recall.results": 3,
        "operations.mnemosyne_contents.memories": 3,
        "operations.mnemosyne_contents.facts": 3,
        "operations.mnemosyne_recall.results": 3,
        "operations.byterover_query.matched_docs": 3,
    },
}

COLLECTION_COUNT_PATHS = (
    ("snapshot.builtin.stores.0.entries", "snapshot.builtin.stores.0.entry_count"),
    ("snapshot.builtin.stores.1.entries", "snapshot.builtin.stores.1.entry_count"),
    ("snapshot.holographic.facts", "snapshot.holographic.fact_count"),
    ("snapshot.mem0.memories", "snapshot.mem0.memory_count"),
    ("snapshot.honcho.search_results", "snapshot.honcho.search_result_count"),
    ("snapshot.mnemosyne.memories", "snapshot.mnemosyne.memory_count"),
    ("snapshot.mnemosyne.facts", "snapshot.mnemosyne.fact_count"),
    ("snapshot.byterover.locations", "snapshot.byterover.location_count"),
    ("snapshot.byterover.results", "snapshot.byterover.result_count"),
    ("operations.session_search.results", "operations.session_search.count"),
    (
        "operations.hindsight_contents.memories",
        "operations.hindsight_contents.memory_count",
    ),
    (
        "operations.hindsight_contents.documents",
        "operations.hindsight_contents.document_count",
    ),
    ("operations.hindsight_recall.results", "operations.hindsight_recall.result_count"),
    (
        "operations.mnemosyne_contents.memories",
        "operations.mnemosyne_contents.memory_count",
    ),
    (
        "operations.mnemosyne_contents.facts",
        "operations.mnemosyne_contents.fact_count",
    ),
    ("operations.mnemosyne_recall.results", "operations.mnemosyne_recall.result_count"),
)

REQUIRED_RENDER_MARKERS = {
    "normal": (
        ("Prefers concise release notes", "snapshot.builtin.stores.1.entries.0"),
        ("Dashboard accessibility audit", "snapshot.holographic.facts.0.content"),
        (
            "Hermes should preserve profile-scoped settings",
            "snapshot.mem0.memories.0.memory",
        ),
        (
            "The release checklist requires a smoke test",
            "snapshot.honcho.user.conclusions.0.content",
        ),
        ("Project Aurora uses SQLite", "snapshot.mnemosyne.memories.0.text"),
        ("hermes-demo", "snapshot.hindsight.bank_id"),
        ("Memory retention policy", "snapshot.byterover.results.0.title"),
        (
            "Session search found the migration discussion",
            "operations.session_search.results.0.title",
        ),
        (
            "Preview fixtures never contact provider APIs",
            "operations.hindsight_contents.documents.0.text",
        ),
        (
            "Tuesday morning is the preferred deployment window",
            "operations.hindsight_recall.results.0.text",
        ),
        (
            "Readiness is high because accessibility, syntax, render, and smoke "
            "checks are all represented",
            "operations.hindsight_reflect.reflection",
        ),
        (
            "Contents operation indexed the release planning conversation",
            "operations.mnemosyne_contents.memories.0.text",
        ),
        (
            "Deterministic preview generation is required before packaging",
            "operations.mnemosyne_recall.results.0.text",
        ),
        ("Prefetch context for release work", "operations.mnemosyne_prefetch.context"),
        (
            "Preview query summary: migration readiness depends on four verified checks",
            "operations.byterover_query.answer_summary",
        ),
    ),
    "long-content": (
        ("BUILTIN-LONG-CONTENT", "snapshot.builtin.stores.0.entries.0"),
        ("HOLOGRAPHIC-LONG-CONTENT", "snapshot.holographic.facts.0.content"),
        ("MEM0-LONG-CONTENT", "snapshot.mem0.memories.0.memory"),
        ("HONCHO-LONG-CONTENT", "snapshot.honcho.user.card.0"),
        ("MNEMOSYNE-LONG-CONTENT", "snapshot.mnemosyne.memories.0.text"),
        (
            "hermes-preview-bank-with-long-identifier",
            "snapshot.hindsight.bank_id",
        ),
        ("BYTEROVER-LONG-CONTENT", "snapshot.byterover.results.0.title"),
        ("SESSION-LONG-CONTENT", "operations.session_search.results.0.title"),
        (
            "HINDSIGHT-CONTENTS-LONG",
            "operations.hindsight_contents.memories.0.text",
        ),
        (
            "HINDSIGHT-RECALL-LONG",
            "operations.hindsight_recall.results.0.text",
        ),
        ("HINDSIGHT-REFLECT-LONG", "operations.hindsight_reflect.reflection"),
        (
            "MNEMOSYNE-CONTENTS-LONG",
            "operations.mnemosyne_contents.memories.0.text",
        ),
        (
            "MNEMOSYNE-RECALL-LONG",
            "operations.mnemosyne_recall.results.0.text",
        ),
        (
            "MNEMOSYNE-PREFETCH-LONG",
            "operations.mnemosyne_prefetch.context",
        ),
        ("BYTEROVER-QUERY-LONG", "operations.byterover_query.answer_summary"),
    ),
}


def _fixture_value(case: dict[str, Any], path: str) -> Any:
    value: Any = case
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError(f"Fixture {case.get('id')} is missing required path {path}")
    return value


def _validate_populated_case(case: dict[str, Any]) -> None:
    case_id = case["id"]
    for path, minimum in CASE_COLLECTION_MINIMUMS.get(case_id, {}).items():
        value = _fixture_value(case, path)
        if not isinstance(value, list):
            raise ValueError(f"Fixture {case_id} path {path} must be a list")
        if len(value) < minimum:
            raise ValueError(
                f"Fixture {case_id} path {path} requires at least {minimum} items; "
                f"found {len(value)}"
            )

    if case_id in CASE_COLLECTION_MINIMUMS:
        for collection_path, count_path in COLLECTION_COUNT_PATHS:
            collection = _fixture_value(case, collection_path)
            count = _fixture_value(case, count_path)
            if count != len(collection):
                raise ValueError(
                    f"Fixture {case_id} field {count_path} must equal the length of "
                    f"{collection_path}; expected {len(collection)}, found {count}"
                )
        stores = _fixture_value(case, "snapshot.builtin.stores")
        total_entries = _fixture_value(case, "snapshot.builtin.total_entries")
        expected_entries = sum(len(store["entries"]) for store in stores)
        if total_entries != expected_entries:
            raise ValueError(
                f"Fixture {case_id} field snapshot.builtin.total_entries must equal "
                f"the displayed entry total; expected {expected_entries}, "
                f"found {total_entries}"
            )
        prefetch = _fixture_value(case, "operations.mnemosyne_prefetch")
        if prefetch.get("context_char_count") != len(prefetch.get("context", "")):
            raise ValueError(
                f"Fixture {case_id} Mnemosyne prefetch context_char_count must "
                "match its context length"
            )

    assertions = case.get("assertions")
    if not isinstance(assertions, list) or not all(
        isinstance(assertion, str) and assertion for assertion in assertions
    ):
        raise ValueError(f"Fixture {case_id} must define non-empty string assertions")
    for marker, path in REQUIRED_RENDER_MARKERS.get(case_id, ()):
        if marker not in assertions:
            raise ValueError(
                f"Fixture {case_id} assertions must include render marker {marker!r}"
            )
        value = _fixture_value(case, path)
        if marker not in str(value):
            raise ValueError(
                f"Fixture {case_id} render marker {marker!r} is absent from {path}"
            )


def load_catalog(fixtures_dir: Path) -> dict[str, Any]:
    fixture_paths = sorted(fixtures_dir.glob("*.json"), key=lambda path: path.name)
    if not fixture_paths:
        raise ValueError(f"No provider fixtures found in {fixtures_dir}")

    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for fixture_path in fixture_paths:
        try:
            case = json.loads(fixture_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON fixture {fixture_path}: {exc}") from exc
        if not isinstance(case, dict):
            raise ValueError(f"Fixture {fixture_path} must contain a JSON object")

        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"Fixture {fixture_path} must define a non-empty string id")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate fixture id: {case_id}")
        seen_ids.add(case_id)

        snapshot = case.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError(f"Fixture {case_id} must define a snapshot object")
        missing_providers = [
            provider
            for provider in REQUIRED_PROVIDERS
            if not isinstance(snapshot.get(provider), dict)
        ]
        if missing_providers:
            raise ValueError(
                f"Fixture {case_id} is missing provider payloads: "
                + ", ".join(missing_providers)
            )

        operations = case.get("operations")
        if not isinstance(operations, dict):
            raise ValueError(f"Fixture {case_id} must define an operations object")
        missing_operations = [
            operation for operation in REQUIRED_OPERATIONS if operation not in operations
        ]
        if missing_operations:
            raise ValueError(
                f"Fixture {case_id} is missing operation payloads: "
                + ", ".join(missing_operations)
            )
        _validate_populated_case(case)
        cases.append(case)

    cases.sort(key=lambda case: (case["id"] != "normal", case["id"]))
    return {
        "development_only": True,
        "source": "tests/fixtures/providers",
        "cases": cases,
    }


def build_preview(source_path: Path, fixtures_dir: Path) -> str:
    source = source_path.read_text(encoding="utf-8")
    for marker, replacement in REPLACEMENTS.items():
        count = source.count(marker)
        if count != 1:
            raise ValueError(
                f"Expected exactly one production metadata marker {marker!r}; found {count}"
            )
        source = source.replace(marker, replacement)

    marker_count = source.count(CATALOG_MARKER)
    if marker_count != 1:
        raise ValueError(
            f"Expected exactly one preview catalog marker; found {marker_count}"
        )
    catalog_literal = json.dumps(
        load_catalog(fixtures_dir),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    source = source.replace(
        CATALOG_MARKER,
        f"export const PREVIEW_CATALOG = {catalog_literal}",
    )
    return source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = build_preview(args.source.resolve(), args.fixtures.resolve())
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
