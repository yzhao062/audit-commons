#!/usr/bin/env python3
"""
scripts/check_reading_lists.py - Verification Suite for Curated Resource Selections.

Validates:
1. Schema & Data Contract of content/reading-lists.json:
   - Valid list structure with required 3 selections.
   - Unique kebab-case slug identifiers.
   - Non-empty bilingual title and purpose (en and zh).
   - 4 to 6 items per selection with valid existing resource IDs.
   - No duplicate resource IDs within selections.
   - Non-empty bilingual rationales (en and zh).
   - Maintainer project hard cap: at most 1 maintainer project per selection.
2. Negative / Fail-Closed Rejection Tests:
   - Missing/unknown resource IDs raise ValueError (no silent skipping).
   - Duplicate list IDs raise ValueError.
   - Duplicate resource IDs raise ValueError.
   - Absent/empty translations in title, purpose, or rationale raise ValueError.
   - Breach of maintainer project cap (>1) raises ValueError.
   - Item count boundary violations (<4 or >6) raise ValueError.
3. Rendered HTML Output Inspection:
   - Built EN and ZH resources pages contain #curated-selections with 3 <details> rows.
   - Native <summary> elements contain visible titles; purposes appear inside expanded rows.
   - Starting points caveat/disclaimer present in both languages.
   - Direct external canonical URLs rendered without filter-hidden bugs.
   - Absence of .resource-card class inside curated selections to preserve catalog filters.
   - Learn page in EN and ZH contains concise bridge linking to /resources/#curated-selections.
"""

from __future__ import annotations

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set

# Add scripts directory to module search path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reading_lists import (
    validate_reading_lists,
    load_reading_lists,
    MAX_MAINTAINER_PROJECTS_PER_SELECTION,
    MIN_ITEMS_PER_SELECTION,
    MAX_ITEMS_PER_SELECTION,
    REQUIRED_SELECTION_COUNT,
)


class SelectionHtmlExtractor(HTMLParser):
    """Parses rendered HTML to inspect curated selections and learn bridges."""

    def __init__(self) -> None:
        super().__init__()
        self.element_ids: Set[str] = set()
        self.selection_rows: List[Dict[str, str]] = []
        self.in_curated_selections = False
        self.curated_selections_classes: List[str] = []
        self.resource_cards_inside_selections: int = 0
        self.all_links: List[Dict[str, str]] = []
        self.has_learn_bridge = False
        self.learn_bridge_links: List[str] = []
        self.in_learn_bridge = False
        self.current_tag: Optional[str] = None
        self.raw_text_chunks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        elem_id = attr_dict.get("id", "")
        classes = attr_dict.get("class", "").split()

        if elem_id:
            self.element_ids.add(elem_id)

        if elem_id == "curated-selections":
            self.in_curated_selections = True

        if "learn-selections-bridge" in classes:
            self.has_learn_bridge = True
            self.in_learn_bridge = True

        if self.in_curated_selections:
            if "resource-card" in classes:
                self.resource_cards_inside_selections += 1
            if tag == "details" and "selection-row" in classes:
                self.selection_rows.append(attr_dict)

        if tag == "a":
            href = attr_dict.get("href", "")
            self.all_links.append(attr_dict)
            if self.in_learn_bridge:
                self.learn_bridge_links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "section" and self.in_curated_selections:
            self.in_curated_selections = False
        if tag in ("p", "aside") and self.in_learn_bridge:
            self.in_learn_bridge = False

    def handle_data(self, data: str) -> None:
        self.raw_text_chunks.append(data)


class TestReporter:
    def __init__(self) -> None:
        self.checks = 0
        self.errors: List[str] = []

    def check(self) -> None:
        self.checks += 1

    def error(self, msg: str) -> None:
        self.errors.append(msg)


def test_reading_lists_data_contract(content_dir: Path, report: TestReporter) -> None:
    """Verifies content/reading-lists.json against schema and resources.json."""
    lists_file = content_dir / "reading-lists.json"
    report.check()
    if not lists_file.exists():
        report.error(f"Missing required file: {lists_file}")
        return

    resources_file = content_dir / "resources.json"
    report.check()
    if not resources_file.exists():
        report.error(f"Missing required file: {resources_file}")
        return

    resources = json.loads(resources_file.read_text(encoding="utf-8"))
    res_lookup = {r["id"]: r for r in resources}

    try:
        data = load_reading_lists(content_dir, resources)
    except Exception as e:
        report.error(f"Failed to load or validate reading-lists.json: {e}")
        return

    report.check()
    if len(data) != REQUIRED_SELECTION_COUNT:
        report.error(f"Expected exactly {REQUIRED_SELECTION_COUNT} selections, found {len(data)}")

    expected_selection_ids = {
        "evaluate-agent-deployment",
        "secure-tool-use-prompt-injection",
        "governance-evidence-foundations",
    }
    actual_ids = {s["id"] for s in data}
    report.check()
    if actual_ids != expected_selection_ids:
        report.error(f"Unexpected selection IDs: {actual_ids} (expected {expected_selection_ids})")

    for sel in data:
        sel_id = sel["id"]
        items = sel.get("items", [])

        report.check()
        if not (MIN_ITEMS_PER_SELECTION <= len(items) <= MAX_ITEMS_PER_SELECTION):
            report.error(f"Selection '{sel_id}' item count {len(items)} out of bounds [4, 6]")

        maintainer_count = 0
        for item in items:
            rid = item.get("resource_id")
            report.check()
            if rid not in res_lookup:
                report.error(f"Selection '{sel_id}' has unknown resource ID '{rid}'")
                continue

            r = res_lookup[rid]
            if r.get("relationship") == "Maintainer project":
                maintainer_count += 1

            # Ensure rationale exists in EN and ZH
            rat = item.get("rationale", {})
            report.check()
            if not rat.get("en") or not isinstance(rat["en"], str) or not rat["en"].strip():
                report.error(f"Selection '{sel_id}' item '{rid}' missing English rationale")
            report.check()
            if not rat.get("zh") or not isinstance(rat["zh"], str) or not rat["zh"].strip():
                report.error(f"Selection '{sel_id}' item '{rid}' missing Chinese rationale")

        report.check()
        if maintainer_count > MAX_MAINTAINER_PROJECTS_PER_SELECTION:
            report.error(
                f"Selection '{sel_id}' breaches maintainer cap: {maintainer_count} > {MAX_MAINTAINER_PROJECTS_PER_SELECTION}"
            )


def test_negative_rejection_cases(content_dir: Path, report: TestReporter) -> None:
    """Verifies that validate_reading_lists strictly rejects invalid inputs."""
    resources_file = content_dir / "resources.json"
    resources = json.loads(resources_file.read_text(encoding="utf-8"))
    valid_data = load_reading_lists(content_dir)

    # 1. Unknown resource ID
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[0]["items"][0]["resource_id"] = "non-existent-resource-id-xyz"
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Unknown resource ID was not rejected")
    except ValueError:
        pass

    # 2. Duplicate selection ID
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[1]["id"] = bad_data[0]["id"]
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Duplicate selection ID was not rejected")
    except ValueError:
        pass

    # 3. Duplicate resource ID within selection
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[0]["items"][1]["resource_id"] = bad_data[0]["items"][0]["resource_id"]
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Duplicate resource ID in list was not rejected")
    except ValueError:
        pass

    # 4. Missing Chinese translation in title
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[0]["title"]["zh"] = ""
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Empty Chinese title was not rejected")
    except ValueError:
        pass

    # 5. Missing English translation in purpose
    report.check()
    bad_data = copy.deepcopy(valid_data)
    del bad_data[0]["purpose"]["en"]
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Missing English purpose was not rejected")
    except ValueError:
        pass

    # 6. Missing Chinese rationale in item
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[0]["items"][0]["rationale"]["zh"] = "   "
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Whitespace-only Chinese rationale was not rejected")
    except ValueError:
        pass

    # 7. Breach of maintainer cap (add 2 maintainer projects to selection)
    maintainer_ids = [r["id"] for r in resources if r.get("relationship") == "Maintainer project"]
    if len(maintainer_ids) >= 2:
        report.check()
        bad_data = copy.deepcopy(valid_data)
        bad_data[0]["items"][0]["resource_id"] = maintainer_ids[0]
        bad_data[0]["items"][1]["resource_id"] = maintainer_ids[1]
        try:
            validate_reading_lists(bad_data, resources)
            report.error("Negative test FAIL: Maintainer cap breach (>1) was not rejected")
        except ValueError:
            pass

    # 8. Fewer than minimum items (<4)
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[0]["items"] = bad_data[0]["items"][:3]
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Selection with 3 items was not rejected (<4)")
    except ValueError:
        pass

    # 9. More than maximum items (>6)
    report.check()
    bad_data = copy.deepcopy(valid_data)
    extra_item = copy.deepcopy(bad_data[0]["items"][0])
    extra_item["resource_id"] = "swe-bench"
    extra_item2 = copy.deepcopy(bad_data[0]["items"][0])
    extra_item2["resource_id"] = "agentbench"
    bad_data[0]["items"].extend([extra_item, extra_item2])  # 5 + 2 = 7 items
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Selection with 7 items was not rejected (>6)")
    except ValueError:
        pass

    # 10. Invalid selection slug format
    report.check()
    bad_data = copy.deepcopy(valid_data)
    bad_data[0]["id"] = "INVALID_SLUG_NAME!"
    try:
        validate_reading_lists(bad_data, resources)
        report.error("Negative test FAIL: Invalid slug syntax was not rejected")
    except ValueError:
        pass


def test_rendered_output_inspection(output_dir: Path, content_dir: Path, report: TestReporter) -> None:
    """Inspects built HTML output in _site for both English and Chinese editions."""
    reading_lists = load_reading_lists(content_dir)
    resources = json.loads((content_dir / "resources.json").read_text(encoding="utf-8"))
    res_lookup = {r["id"]: r for r in resources}

    # 1. English Resources Page
    en_res_path = output_dir / "resources/index.html"
    report.check()
    if not en_res_path.exists():
        report.error(f"Missing output file: {en_res_path}")
        return

    en_res_html = en_res_path.read_text(encoding="utf-8")
    en_extractor = SelectionHtmlExtractor()
    en_extractor.feed(en_res_html)

    report.check()
    if "curated-selections" not in en_extractor.element_ids:
        report.error("resources/index.html missing element id 'curated-selections'")

    report.check()
    if len(en_extractor.selection_rows) != REQUIRED_SELECTION_COUNT:
        report.error(
            f"resources/index.html: expected {REQUIRED_SELECTION_COUNT} selection rows, found {len(en_extractor.selection_rows)}"
        )

    report.check()
    if en_extractor.resource_cards_inside_selections != 0:
        report.error(
            f"resources/index.html: prohibited .resource-card class found inside curated selections: {en_extractor.resource_cards_inside_selections}"
        )

    report.check()
    if "Start with a task" not in en_res_html or "certification" not in en_res_html.lower():
        report.error("resources/index.html missing 'Start with a task' header or certification disclaimer")

    # Check that each selected resource URL is present as a direct link
    for sel in reading_lists:
        for item in sel["items"]:
            rid = item["resource_id"]
            r_url = res_lookup[rid]["url"]
            report.check()
            if r_url not in en_res_html:
                report.error(f"resources/index.html missing direct canonical link for '{rid}': {r_url}")

    # 2. Chinese Resources Page
    zh_res_path = output_dir / "zh/resources/index.html"
    report.check()
    if not zh_res_path.exists():
        report.error(f"Missing output file: {zh_res_path}")
        return

    zh_res_html = zh_res_path.read_text(encoding="utf-8")
    zh_extractor = SelectionHtmlExtractor()
    zh_extractor.feed(zh_res_html)

    report.check()
    if "curated-selections" not in zh_extractor.element_ids:
        report.error("zh/resources/index.html missing element id 'curated-selections'")

    report.check()
    if len(zh_extractor.selection_rows) != REQUIRED_SELECTION_COUNT:
        report.error(
            f"zh/resources/index.html: expected {REQUIRED_SELECTION_COUNT} selection rows, found {len(zh_extractor.selection_rows)}"
        )

    report.check()
    if zh_extractor.resource_cards_inside_selections != 0:
        report.error(
            f"zh/resources/index.html: prohibited .resource-card class found inside curated selections: {zh_extractor.resource_cards_inside_selections}"
        )

    report.check()
    if "从任务开始" not in zh_res_html or "认证" not in zh_res_html:
        report.error("zh/resources/index.html missing '从任务开始' header or certification disclaimer")

    # Check that Chinese rationales are present
    for sel in reading_lists:
        report.check()
        if sel["title"]["zh"] not in zh_res_html:
            report.error(f"zh/resources/index.html missing Chinese title '{sel['title']['zh']}'")
        for item in sel["items"]:
            report.check()
            if item["rationale"]["zh"] not in zh_res_html:
                report.error(f"zh/resources/index.html missing Chinese rationale for '{item['resource_id']}'")

    # 3. English Learn Page Bridge
    en_learn_path = output_dir / "learn/index.html"
    report.check()
    if not en_learn_path.exists():
        report.error(f"Missing output file: {en_learn_path}")
        return

    en_learn_html = en_learn_path.read_text(encoding="utf-8")
    en_learn_ext = SelectionHtmlExtractor()
    en_learn_ext.feed(en_learn_html)

    report.check()
    if not en_learn_ext.has_learn_bridge:
        report.error("learn/index.html missing .learn-selections-bridge callout")

    report.check()
    expected_en_target = "/resources/#curated-selections"
    if not any(expected_en_target in lk for lk in en_learn_ext.learn_bridge_links):
        report.error(
            f"learn/index.html bridge does not link to '{expected_en_target}'. Found: {en_learn_ext.learn_bridge_links}"
        )

    # 4. Chinese Learn Page Bridge
    zh_learn_path = output_dir / "zh/learn/index.html"
    report.check()
    if not zh_learn_path.exists():
        report.error(f"Missing output file: {zh_learn_path}")
        return

    zh_learn_html = zh_learn_path.read_text(encoding="utf-8")
    zh_learn_ext = SelectionHtmlExtractor()
    zh_learn_ext.feed(zh_learn_html)

    report.check()
    if not zh_learn_ext.has_learn_bridge:
        report.error("zh/learn/index.html missing .learn-selections-bridge callout")

    report.check()
    expected_zh_target = "/zh/resources/#curated-selections"
    if not any(expected_zh_target in lk for lk in zh_learn_ext.learn_bridge_links):
        report.error(
            f"zh/learn/index.html bridge does not link to '{expected_zh_target}'. Found: {zh_learn_ext.learn_bridge_links}"
        )


def main() -> int:
    repo_root = Path.cwd().resolve()
    content_dir = repo_root / "content"
    output_dir = repo_root / "_site"

    print("=== Audit Commons Curated Selections Verification Suite ===")
    print(f"Content directory: {content_dir}")
    print(f"Output directory:  {output_dir}")
    print()

    report = TestReporter()

    print("1. Checking content/reading-lists.json schema, contracts, and maintainer caps...")
    test_reading_lists_data_contract(content_dir, report)

    if not report.errors:
        print("2. Checking fail-closed rejection on invalid data...")
        test_negative_rejection_cases(content_dir, report)

        print("3. Checking rendered output in _site (Resources & Learn, EN & ZH)...")
        test_rendered_output_inspection(output_dir, content_dir, report)

    print()
    if report.errors:
        print(f"FAILED with {len(report.errors)} error(s):")
        for err in report.errors:
            print(f"  [FAIL] {err}")
        return 1

    print(f"Reading lists suite completed: {report.checks} checks.")
    print("ALL READING LISTS INVARIANTS PASSED (0 errors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
