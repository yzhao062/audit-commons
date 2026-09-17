#!/usr/bin/env python3
"""
scripts/reading_lists.py - Task-Oriented Curated Resource Selections Helper.

Provides validation, loading, and static HTML rendering for task-oriented
reading lists on Audit Commons. Conforms to standard library Python 3.12 only.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

VALID_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_MAINTAINER_PROJECTS_PER_SELECTION = 1
MIN_ITEMS_PER_SELECTION = 4
MAX_ITEMS_PER_SELECTION = 6
REQUIRED_SELECTION_COUNT = 3

FORMAT_LABELS_EN = {
    "Paper": "Paper",
    "Tool": "Tool",
    "Benchmark": "Benchmark",
    "Dataset": "Dataset",
    "Standard": "Standard",
    "Collection": "Collection",
}

FORMAT_LABELS_ZH = {
    "Paper": "论文",
    "Tool": "工具",
    "Benchmark": "基准",
    "Dataset": "数据集",
    "Standard": "规范",
    "Collection": "合集",
}

DISCLAIMER_EN = "Reading suggestions, not certification."
DISCLAIMER_ZH = "仅供阅读参考，不构成认证。"


def validate_reading_lists(reading_lists: Any, resources: List[Dict[str, Any]]) -> None:
    """
    Validates curated reading lists data against schema contracts and existing catalog records.

    Enforces:
    - Top-level list structure with at least REQUIRED_SELECTION_COUNT items.
    - Unique, valid kebab-case slug IDs for selections.
    - Bilingual 'title' and 'purpose' with non-empty 'en' and 'zh' strings.
    - 4 to 6 items per selection.
    - Unique resource IDs within each selection.
    - All resource IDs must exist in the provided resources catalog (no unknown IDs).
    - Bilingual 'rationale' for each item with non-empty 'en' and 'zh' strings.
    - Hard cap: at most 1 maintainer project per selection.
    """
    if not isinstance(reading_lists, list):
        raise ValueError("reading-lists.json must be a JSON list of selection objects")

    if len(reading_lists) < REQUIRED_SELECTION_COUNT:
        raise ValueError(
            f"Expected at least {REQUIRED_SELECTION_COUNT} selections, found {len(reading_lists)}"
        )

    res_lookup: Dict[str, Dict[str, Any]] = {
        r.get("id"): r for r in resources if isinstance(r, dict) and "id" in r
    }

    seen_list_ids: Set[str] = set()

    for idx, sel in enumerate(reading_lists):
        if not isinstance(sel, dict):
            raise ValueError(f"Selection #{idx} must be a JSON object")

        sel_id = sel.get("id")
        if not sel_id or not isinstance(sel_id, str) or not VALID_SLUG_PATTERN.match(sel_id):
            raise ValueError(f"Selection #{idx} has invalid or missing 'id': {sel_id!r}")
        if sel_id in seen_list_ids:
            raise ValueError(f"Duplicate selection ID detected: {sel_id!r}")
        seen_list_ids.add(sel_id)

        # Validate bilingual title
        title = sel.get("title")
        if not isinstance(title, dict) or not title.get("en") or not title.get("zh"):
            raise ValueError(
                f"Selection '{sel_id}' must have bilingual 'title' with non-empty 'en' and 'zh'"
            )
        if not isinstance(title["en"], str) or not isinstance(title["zh"], str) or not title["en"].strip() or not title["zh"].strip():
            raise ValueError(f"Selection '{sel_id}' 'title' fields must be non-empty strings")

        # Validate bilingual purpose
        purpose = sel.get("purpose")
        if not isinstance(purpose, dict) or not purpose.get("en") or not purpose.get("zh"):
            raise ValueError(
                f"Selection '{sel_id}' must have bilingual 'purpose' with non-empty 'en' and 'zh'"
            )
        if not isinstance(purpose["en"], str) or not isinstance(purpose["zh"], str) or not purpose["en"].strip() or not purpose["zh"].strip():
            raise ValueError(f"Selection '{sel_id}' 'purpose' fields must be non-empty strings")

        # Validate items
        items = sel.get("items")
        if not isinstance(items, list):
            raise ValueError(f"Selection '{sel_id}' 'items' must be a list")
        if not (MIN_ITEMS_PER_SELECTION <= len(items) <= MAX_ITEMS_PER_SELECTION):
            raise ValueError(
                f"Selection '{sel_id}' must contain {MIN_ITEMS_PER_SELECTION}-{MAX_ITEMS_PER_SELECTION} items, found {len(items)}"
            )

        seen_item_ids: Set[str] = set()
        maintainer_count = 0

        for item_idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"Selection '{sel_id}' item #{item_idx} must be a JSON object")

            rid = item.get("resource_id")
            if not rid or not isinstance(rid, str):
                raise ValueError(f"Selection '{sel_id}' item #{item_idx} missing 'resource_id'")
            if rid in seen_item_ids:
                raise ValueError(f"Selection '{sel_id}' contains duplicate resource ID: '{rid}'")
            seen_item_ids.add(rid)

            if rid not in res_lookup:
                raise ValueError(f"Selection '{sel_id}' references unknown resource ID: '{rid}'")

            res = res_lookup[rid]
            if res.get("relationship") == "Maintainer project":
                maintainer_count += 1

            # Validate bilingual rationale
            rationale = item.get("rationale")
            if not isinstance(rationale, dict) or not rationale.get("en") or not rationale.get("zh"):
                raise ValueError(
                    f"Selection '{sel_id}' item '{rid}' must have bilingual 'rationale' with non-empty 'en' and 'zh'"
                )
            if not isinstance(rationale["en"], str) or not isinstance(rationale["zh"], str) or not rationale["en"].strip() or not rationale["zh"].strip():
                raise ValueError(f"Selection '{sel_id}' item '{rid}' 'rationale' fields must be non-empty strings")

        if maintainer_count > MAX_MAINTAINER_PROJECTS_PER_SELECTION:
            raise ValueError(
                f"Selection '{sel_id}' exceeds maintainer project cap: allowed at most "
                f"{MAX_MAINTAINER_PROJECTS_PER_SELECTION}, found {maintainer_count}"
            )


def load_reading_lists(
    content_dir: Path,
    resources: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Loads and optionally validates reading-lists.json from the content directory."""
    path = content_dir / "reading-lists.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing reading lists configuration: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e

    if resources is not None:
        validate_reading_lists(data, resources)

    return data


def render_reading_lists_html(
    reading_lists: List[Dict[str, Any]],
    resources_lookup: Dict[str, Dict[str, Any]],
    locale: str = "en",
) -> str:
    """
    Renders compact, accessible static HTML for curated task selections.
    Uses native <details>/<summary> elements without JavaScript dependency.
    Does NOT use .resource-card class to prevent collision with catalog filters.
    """
    is_zh = (locale == "zh")

    heading = "从任务开始" if is_zh else "Start with a task"
    desc = (
        "三条按任务组织的阅读路径，用于部署前检查、工具安全与审计证据。"
        if is_zh else
        "Three reading paths through the catalog for pre-deployment checks, tool security, and audit evidence."
    )
    disclaimer = DISCLAIMER_ZH if is_zh else DISCLAIMER_EN
    items_suffix = "项资源" if is_zh else "resources"
    owner_prefix = "归属：" if is_zh else "Attribution:"
    maintainer_label = "维护者项目" if is_zh else "Maintainer project"

    format_labels = FORMAT_LABELS_ZH if is_zh else FORMAT_LABELS_EN

    rows_html: List[str] = []

    for sel in reading_lists:
        sel_id = sel["id"]
        title_text = sel["title"]["zh"] if is_zh else sel["title"]["en"]
        purpose_text = sel["purpose"]["zh"] if is_zh else sel["purpose"]["en"]
        items = sel.get("items", [])
        badge_text = f"{len(items)} {items_suffix}"

        item_rows: List[str] = []
        for seq_idx, item in enumerate(items, 1):
            rid = item["resource_id"]
            res = resources_lookup.get(rid, {})
            res_name = res.get("name", rid)
            res_url = res.get("url", "#")
            res_format = res.get("format", "Collection")
            fmt_label = format_labels.get(res_format, res_format)
            rel = res.get("relationship", "External resource")

            owner = res.get("owner", "")
            if is_zh and owner == "Authors listed in the paper":
                owner_display = "见论文作者名单"
            else:
                owner_display = owner

            rationale_text = item["rationale"]["zh"] if is_zh else item["rationale"]["en"]

            maintainer_badge = ""
            if rel == "Maintainer project":
                maintainer_badge = f'<span class="tag tag-maintainer">{maintainer_label}</span>'

            item_html = f"""          <li class="selection-item">
            <div class="selection-item-header">
              <span class="selection-item-num" aria-hidden="true">{seq_idx:02d}</span>
              <div class="selection-item-title-wrap">
                <a href="{html.escape(res_url)}" class="selection-item-link" rel="noopener noreferrer">{html.escape(res_name)} <span class="external-arrow" aria-hidden="true">&nearr;</span></a>
                <span class="selection-item-tags">
                  <span class="tag tag-format tag-format-{html.escape(res_format.lower())}">{html.escape(fmt_label)}</span>
                  {maintainer_badge}
                </span>
              </div>
            </div>
            <p class="selection-item-rationale">{html.escape(rationale_text)}</p>
            <div class="selection-item-meta">
              <span class="selection-owner">{owner_prefix} {html.escape(owner_display)}</span>
            </div>
          </li>"""
            item_rows.append(item_html)

        items_markup = "\n".join(item_rows)

        row_html = f"""      <details class="selection-row" id="selection-{html.escape(sel_id)}">
        <summary class="selection-summary">
          <span class="selection-summary-main">
            <span class="selection-summary-title">{html.escape(title_text)}</span>
          </span>
          <span class="selection-summary-meta">
            <span class="selection-badge">{badge_text}</span>
            <span class="selection-chevron" aria-hidden="true">&rsaquo;</span>
          </span>
        </summary>
        <div class="selection-content">
          <p class="selection-summary-purpose">{html.escape(purpose_text)}</p>
          <ol class="selection-list">
{items_markup}
          </ol>
        </div>
      </details>"""
        rows_html.append(row_html)

    all_rows = "\n".join(rows_html)

    return f"""    <section class="curated-selections" id="curated-selections" aria-labelledby="curated-selections-heading">
      <div class="curated-selections-header">
        <h2 id="curated-selections-heading">{heading}</h2>
        <p class="curated-selections-desc">{desc} <span class="curated-selections-disclaimer">{disclaimer}</span></p>
      </div>
      <div class="curated-selections-rows">
{all_rows}
      </div>
    </section>
"""


def render_learn_selections_bridge(locale: str = "en") -> str:
    """
    Renders a concise cross-link on Learn pointing to the curated reading
    paths on Resources without duplicating curricula.
    """
    is_zh = (locale == "zh")
    target_url = "/zh/resources/#curated-selections" if is_zh else "/resources/#curated-selections"

    if is_zh:
        return f"""      <p class="learn-selections-bridge">
        正在按任务寻找工具与标准？可以从资源库中关于评估、安全与治理的<a href="{target_url}">精选阅读路径</a>开始。
      </p>"""
    else:
        return f"""      <p class="learn-selections-bridge">
        Looking for tools and standards by task? Start with <a href="{target_url}">curated reading paths</a> for evaluation, security, and governance in the catalog.
      </p>"""
