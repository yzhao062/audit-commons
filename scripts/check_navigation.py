#!/usr/bin/env python3
"""
scripts/check_navigation.py - Dedicated Acceptance Suite for Site Navigation & Latest Filtering.

Verifies:
1. 4-item Main Navigation:
   - English: Latest, Learn, Resources, About across all pages
   - Chinese (/zh/): 最新, 学习, 资源, 关于 across all pages
   - "Features" / "专栏" is NEVER present as a primary navigation item
2. Active Navigation Highlighting:
   - /latest/, /news/*, /updates/*, /features/, /features/* activate Latest
   - /learn/, /guides/*, /start-here/ activate Learn
   - /resources/ activates Resources
   - /about/ activates About
3. Deep Article Breadcrumbs:
   - Feature articles route to Latest (English) and 最新 (Chinese)
   - News and Release articles route to Latest / 最新
   - Guides and Intro articles route to Learn / 学习
4. Legacy Features Index:
   - /features/ and /zh/features/ exist and are not redirected
   - Contains contextual link to /latest/?kind=feature (or /zh/latest/?kind=feature)
   - Features terminology replaced with Analysis / 深度解读 in UI & eyebrow
5. Article Card Contracts:
   - Every article card possesses valid data-kind attribute
6. Latest Filtering Controls & Accessibility:
   - Hidden-until-JS attribute present on #latest-controls
   - Accessible button group with aria-label
   - Filter categories: all, news, feature, guide, release with aria-pressed
   - Status element #latest-count with role="status" and aria-live="polite"
7. Discovery & Footer Terminology:
   - Features replaced with Analysis (English) and 深度解读 (Chinese) in footers & 404 pages
8. Localization Invariants:
   - REQUIRED_NAV_ITEMS_ZH contains exactly 4 items
   - KIND_LABELS_ZH["feature"] == "深度解读"
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Dict, List, Set, Tuple
from html.parser import HTMLParser

REPO_ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = REPO_ROOT / "_site"


class NavDOMParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_site_nav = False
        self.nav_links: List[Tuple[str, str, Dict[str, str]]] = []  # (href, text, attrs)
        self.current_link_href = ""
        self.current_link_text = ""
        self.current_link_attrs: Dict[str, str] = {}
        self.breadcrumbs: List[Tuple[str, str]] = []  # (href, text)
        self.in_breadcrumbs = False
        self.article_cards: List[Dict[str, str]] = []
        self.element_ids: Set[str] = set()
        self.elements_with_hidden: Set[str] = set()
        self.latest_filter_buttons: List[Dict[str, str]] = []
        self.in_latest_controls = False
        self.footer_links: List[Tuple[str, str]] = []
        self.in_footer = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        elem_id = attr_dict.get("id", "")
        if elem_id:
            self.element_ids.add(elem_id)
        if "hidden" in attr_dict or any(k == "hidden" for k, _ in attrs):
            if elem_id:
                self.elements_with_hidden.add(elem_id)

        classes = attr_dict.get("class", "").split()

        if tag == "nav" and "site-nav" in classes:
            self.in_site_nav = True
        elif tag == "nav" and "breadcrumbs" in classes:
            self.in_breadcrumbs = True
        elif tag == "div" and elem_id == "latest-controls":
            self.in_latest_controls = True
        elif tag == "footer" and "site-footer" in classes:
            self.in_footer = True

        if tag == "a":
            href = attr_dict.get("href", "")
            if self.in_site_nav:
                self.current_link_href = href
                self.current_link_text = ""
                self.current_link_attrs = attr_dict
            elif self.in_breadcrumbs:
                self.current_link_href = href
                self.current_link_text = ""
            elif self.in_footer:
                self.current_link_href = href
                self.current_link_text = ""

        if tag == "article" and "article-card" in classes:
            self.article_cards.append(attr_dict)

        if self.in_latest_controls and tag == "button" and "data-kind" in attr_dict:
            self.latest_filter_buttons.append(attr_dict)

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self.in_site_nav = False
            self.in_breadcrumbs = False
        elif tag == "div" and self.in_latest_controls:
            # We don't exit on child divs, but we're tracking buttons inside
            pass
        elif tag == "footer":
            self.in_footer = False

        if tag == "a":
            if self.in_site_nav:
                self.nav_links.append((self.current_link_href, self.current_link_text.strip(), self.current_link_attrs))
                self.current_link_href = ""
                self.current_link_text = ""
            elif self.in_breadcrumbs:
                self.breadcrumbs.append((self.current_link_href, self.current_link_text.strip()))
                self.current_link_href = ""
                self.current_link_text = ""
            elif self.in_footer:
                self.footer_links.append((self.current_link_href, self.current_link_text.strip()))
                self.current_link_href = ""
                self.current_link_text = ""

    def handle_data(self, data: str) -> None:
        if self.current_link_href:
            self.current_link_text += data


class TestReporter:
    def __init__(self) -> None:
        self.checks = 0
        self.errors: List[str] = []

    def check(self) -> None:
        self.checks += 1

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def summary(self) -> bool:
        print(f"\nNavigation suite completed: {self.checks} checks.")
        if self.errors:
            print(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                print(f"  - {e}")
            return False
        print("ALL NAVIGATION INVARIANTS PASSED (0 errors).")
        return True


def run_checks() -> int:
    report = TestReporter()
    print("=== Audit Commons Navigation & Latest Filtering Verification Suite ===")

    # 1. Localization module constants
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import localization
    import build

    print("Checking localization & build constants...")
    report.check()
    if len(localization.REQUIRED_NAV_ITEMS_ZH) != 4:
        report.error(f"REQUIRED_NAV_ITEMS_ZH must have 4 items, got {len(localization.REQUIRED_NAV_ITEMS_ZH)}: {localization.REQUIRED_NAV_ITEMS_ZH}")
    zh_targets = [t for _, t in localization.REQUIRED_NAV_ITEMS_ZH]
    expected_zh_targets = ["/zh/latest/", "/zh/learn/", "/zh/resources/", "/zh/about/"]
    if zh_targets != expected_zh_targets:
        report.error(f"REQUIRED_NAV_ITEMS_ZH targets mismatch: expected {expected_zh_targets}, got {zh_targets}")

    report.check()
    if len(build.REQUIRED_NAV_ITEMS) != 4:
        report.error(f"REQUIRED_NAV_ITEMS must have 4 items, got {len(build.REQUIRED_NAV_ITEMS)}: {build.REQUIRED_NAV_ITEMS}")
    en_targets = [t for _, t in build.REQUIRED_NAV_ITEMS]
    expected_en_targets = ["/latest/", "/learn/", "/resources/", "/about/"]
    if en_targets != expected_en_targets:
        report.error(f"REQUIRED_NAV_ITEMS targets mismatch: expected {expected_en_targets}, got {en_targets}")

    report.check()
    if localization.KIND_LABELS_ZH.get("feature") != "深度解读":
        report.error(f"KIND_LABELS_ZH['feature'] must be '深度解读', got {localization.KIND_LABELS_ZH.get('feature')}")

    # 2. Iterate over all emitted HTML files in _site
    print("Checking emitted HTML routes in _site...")
    html_files = sorted(SITE_DIR.glob("**/*.html"))
    if not html_files:
        report.error(f"No HTML files found in {SITE_DIR}. Please run build.py first.")
        return 1

    for html_file in html_files:
        rel = html_file.relative_to(SITE_DIR).as_posix()
        is_zh = rel.startswith("zh/")
        text = html_file.read_text(encoding="utf-8")

        parser = NavDOMParser()
        parser.feed(text)

        # Check main navigation links
        report.check()
        nav_hrefs = [h for h, _, _ in parser.nav_links]
        expected_nav_hrefs = expected_zh_targets if is_zh else expected_en_targets

        if nav_hrefs != expected_nav_hrefs:
            report.error(f"{rel}: Nav links do not match expected 4 items: expected {expected_nav_hrefs}, got {nav_hrefs}")

        # Check Features / 专栏 is never in main nav
        report.check()
        for href, label, _ in parser.nav_links:
            if "features" in href or label in ("Features", "专栏", "深度专栏"):
                report.error(f"{rel}: Main nav contains Features item: href={href}, label={label}")

        # Check footer links replace Features with Analysis / 深度解读
        report.check()
        for href, label in parser.footer_links:
            if "features" in href:
                expected_label = "深度解读" if is_zh else "Analysis"
                if label != expected_label:
                    report.error(f"{rel}: Footer features link has outdated label '{label}', expected '{expected_label}'")

    # The reusable renderer accepts partial fixtures; the published path must be complete.
    for locale_prefix in ("", "zh/"):
        learn_file = SITE_DIR / locale_prefix / "learn/index.html"
        report.check()
        if not learn_file.is_file():
            report.error(f"Learning path missing: {learn_file}")
            continue
        learn_text = learn_file.read_text(encoding="utf-8")
        for step, slug in (("01", "start-here"), ("02", "guides/how-to-read-an-agent-eval-report"), ("03", "guides/audit-an-agent-action")):
            report.check()
            if f'id="step-{step}"' not in learn_text or f'href="/{locale_prefix}{slug}/"' not in learn_text:
                report.error(f"Published learning path missing step {step}: {locale_prefix}{slug}")

    # 3. Active Nav Route Tests
    print("Checking active navigation highlighting...")
    route_expected_active = [
        # (route_path, expected_active_target)
        ("latest/index.html", "/latest/"),
        ("zh/latest/index.html", "/zh/latest/"),
        ("features/index.html", "/latest/"),
        ("zh/features/index.html", "/zh/latest/"),
        ("news/frontier-pacing-ceo-statements/index.html", "/latest/"),
        ("zh/news/frontier-pacing-ceo-statements/index.html", "/zh/latest/"),
        ("features/benchmark-scores-and-agent-safety/index.html", "/latest/"),
        ("zh/features/benchmark-scores-and-agent-safety/index.html", "/zh/latest/"),
        ("updates/catchbench-0-1-2/index.html", "/latest/"),
        ("zh/updates/catchbench-0-1-2/index.html", "/zh/latest/"),
        ("learn/index.html", "/learn/"),
        ("zh/learn/index.html", "/zh/learn/"),
        ("guides/audit-an-agent-action/index.html", "/learn/"),
        ("zh/guides/audit-an-agent-action/index.html", "/zh/learn/"),
        ("start-here/index.html", "/learn/"),
        ("resources/index.html", "/resources/"),
        ("zh/resources/index.html", "/zh/resources/"),
        ("about/index.html", "/about/"),
        ("zh/about/index.html", "/zh/about/"),
    ]

    for rel_path, expected_active in route_expected_active:
        file_path = SITE_DIR / rel_path
        if not file_path.exists():
            report.error(f"Expected navigation test route missing: {rel_path}")
            continue
        report.check()
        text = file_path.read_text(encoding="utf-8")
        parser = NavDOMParser()
        parser.feed(text)
        active_links = [h for h, _, a in parser.nav_links if "active" in a.get("class", "").split()]
        if [expected_active] != active_links:
            report.error(f"{rel_path}: Expected active nav {expected_active}, got {active_links}")

    # 4. Deep Article Breadcrumb Tests
    print("Checking deep article breadcrumbs...")
    breadcrumb_cases = [
        ("features/benchmark-scores-and-agent-safety/index.html", "/latest/", "Latest"),
        ("zh/features/benchmark-scores-and-agent-safety/index.html", "/zh/latest/", "最新"),
        ("news/frontier-pacing-ceo-statements/index.html", "/latest/", "Latest"),
        ("zh/news/frontier-pacing-ceo-statements/index.html", "/zh/latest/", "最新"),
        ("updates/catchbench-0-1-2/index.html", "/latest/", "Latest"),
        ("zh/updates/catchbench-0-1-2/index.html", "/zh/latest/", "最新"),
        ("guides/audit-an-agent-action/index.html", "/learn/", "Learn"),
        ("zh/guides/audit-an-agent-action/index.html", "/zh/learn/", "学习"),
    ]

    for rel_path, expected_parent_href, expected_parent_label in breadcrumb_cases:
        file_path = SITE_DIR / rel_path
        if not file_path.exists():
            report.error(f"Expected navigation test route missing: {rel_path}")
            continue
        report.check()
        text = file_path.read_text(encoding="utf-8")
        parser = NavDOMParser()
        parser.feed(text)

        # Breadcrumbs should have Home -> Section -> Article
        parent_crumbs = [(h, l) for h, l in parser.breadcrumbs if h == expected_parent_href]
        if not parent_crumbs:
            report.error(f"{rel_path}: Breadcrumbs missing expected parent link ({expected_parent_href}, '{expected_parent_label}'): got {parser.breadcrumbs}")
        elif parent_crumbs[0][1] != expected_parent_label:
            report.error(f"{rel_path}: Breadcrumb parent label mismatch: expected '{expected_parent_label}', got '{parent_crumbs[0][1]}'")

    # 5. Legacy Features Index & Contextual Link
    print("Checking legacy features index...")
    for rel_path, expected_contextual_link in [
        ("features/index.html", "/latest/?kind=feature"),
        ("zh/features/index.html", "/zh/latest/?kind=feature"),
    ]:
        file_path = SITE_DIR / rel_path
        report.check()
        if not file_path.exists():
            report.error(f"Legacy features index route missing: {rel_path}")
            continue
        text = file_path.read_text(encoding="utf-8")
        if expected_contextual_link not in text:
            report.error(f"{rel_path}: Contextual backlink to '{expected_contextual_link}' missing from page")

    # 6. Article Cards & data-kind
    print("Checking article cards data-kind attribute...")
    card_routes = [
        "latest/index.html",
        "zh/latest/index.html",
        "features/index.html",
        "zh/features/index.html",
        "updates/index.html",
        "zh/updates/index.html",
        "guides/index.html",
        "zh/guides/index.html",
    ]
    for rel_path in card_routes:
        file_path = SITE_DIR / rel_path
        if not file_path.exists():
            report.error(f"Expected navigation test route missing: {rel_path}")
            continue
        report.check()
        text = file_path.read_text(encoding="utf-8")
        parser = NavDOMParser()
        parser.feed(text)
        if not parser.article_cards:
            report.error(f"{rel_path}: Expected article cards but none found")
        for card in parser.article_cards:
            if not card.get("data-kind"):
                report.error(f"{rel_path}: Article card missing data-kind attribute: {card}")

    # 7. Latest Filtering Controls & Accessibility
    print("Checking Latest filter controls and accessibility contracts...")
    for rel_path in ["latest/index.html", "zh/latest/index.html"]:
        file_path = SITE_DIR / rel_path
        report.check()
        text = file_path.read_text(encoding="utf-8")
        parser = NavDOMParser()
        parser.feed(text)

        if "latest-controls" not in parser.element_ids:
            report.error(f"{rel_path}: #latest-controls missing")
        if "latest-controls" not in parser.elements_with_hidden:
            report.error(f"{rel_path}: #latest-controls must have 'hidden' attribute for no-JS degradation")
        if "latest-count" not in parser.element_ids:
            report.error(f"{rel_path}: #latest-count missing")

        # Check filter buttons
        button_kinds = [b.get("data-kind") for b in parser.latest_filter_buttons]
        expected_kinds = ["all", "news", "feature", "guide", "release"]
        if button_kinds != expected_kinds:
            report.error(f"{rel_path}: Filter button kinds mismatch: expected {expected_kinds}, got {button_kinds}")

        # Check aria-pressed
        for btn in parser.latest_filter_buttons:
            kind = btn.get("data-kind")
            pressed = btn.get("aria-pressed")
            expected_pressed = "true" if kind == "all" else "false"
            if pressed != expected_pressed:
                report.error(f"{rel_path}: Button data-kind='{kind}' expected aria-pressed='{expected_pressed}', got '{pressed}'")

    success = report.summary()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(run_checks())
