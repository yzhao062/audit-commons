#!/usr/bin/env python3
"""
scripts/check_localization.py - Dedicated Localization Verification Suite.

Validates:
1. Reciprocal SEO & Canonical Tags:
   - Self-referential canonical URLs for all English and Chinese routes
   - Reciprocal hreflang tags: en, zh-CN, x-default (x-default points to English root)
   - inLanguage properties in JSON-LD structured data and <html> lang attributes
   - OpenGraph og:locale tags (en_US vs zh_CN)
   - 404 pages: noindex, zero hreflang tags
2. Language Switcher Contract:
   - Header language switcher rendered across all pages
   - Active language identified with aria-current="true" and .is-active
   - Counterpart page target resolution for all routes (including 404.html <-> zh/404.html)
3. Simplified Chinese Resource Catalog:
   - All 201 resources accounted for in Chinese catalog
   - Localized category filter buttons and format tabs with correct counts
   - data-search attributes containing bilingual keywords
   - Status element #resource-count with role="status" and localized initial text
4. Chinese Body Link Localization:
   - Root-relative internal links transformed to /zh/...
   - External links, assets, and fragment anchors preserved
5. Translation Overlay Schema, Coverage, and Stale Hash Rejection:
   - Full coverage (all pages, all resources)
   - Prohibited fields absent
   - Pre-build rejection: stale source_sha256, missing keys, or path escape raise errors before output modification
6. Media Overlays:
   - Localized alt and caption metadata applied in rendered output
"""

from __future__ import annotations

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from localization import (
    validate_translation_overlays,
    compute_page_source_sha256,
    compute_resource_source_sha256,
    canonical_for,
    route_href,
    get_hreflang_tags,
    render_language_switcher,
    localize_body_html,
    FORMAT_DISPLAY_LABELS_ZH,
    CATEGORY_DISPLAY_LABELS_ZH,
)


class HtmlExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang = ""
        self.title = ""
        self.in_title = False
        self.canonicals: List[str] = []
        self.hreflangs: List[Tuple[str, str]] = []  # (hreflang, href)
        self.meta_tags: List[Dict[str, str]] = []
        self.json_ld_scripts: List[str] = []
        self.in_json_ld = False
        self.json_ld_buf = ""
        self.lang_switch_links: List[Dict[str, str]] = []
        self.in_lang_switch = False
        self.resource_cards: List[Dict[str, str]] = []
        self.element_ids: Set[str] = set()
        self.all_links: List[str] = []
        self.images: List[Dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        if "id" in attr_dict:
            self.element_ids.add(attr_dict["id"])

        if tag == "html":
            self.html_lang = attr_dict.get("lang", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "link":
            rel = attr_dict.get("rel", "")
            if rel == "canonical":
                self.canonicals.append(attr_dict.get("href", ""))
            elif rel == "alternate" and "hreflang" in attr_dict:
                self.hreflangs.append((attr_dict.get("hreflang", ""), attr_dict.get("href", "")))
        elif tag == "meta":
            self.meta_tags.append(attr_dict)
        elif tag == "script" and attr_dict.get("type") == "application/ld+json":
            self.in_json_ld = True
            self.json_ld_buf = ""
        elif tag == "nav" and "lang-switch" in attr_dict.get("class", "").split():
            self.in_lang_switch = True
        elif self.in_lang_switch and tag == "a":
            self.lang_switch_links.append(attr_dict)
        elif tag == "article" and "resource-card" in attr_dict.get("class", "").split():
            self.resource_cards.append(attr_dict)
        elif tag == "a" and "href" in attr_dict:
            self.all_links.append(attr_dict["href"])
        elif tag == "img":
            self.images.append(attr_dict)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_json_ld:
            self.in_json_ld = False
            self.json_ld_scripts.append(self.json_ld_buf)
            self.json_ld_buf = ""
        elif tag == "nav" and self.in_lang_switch:
            self.in_lang_switch = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif self.in_json_ld:
            self.json_ld_buf += data


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
        print(f"\nLocalization checks completed: {self.checks}")
        if self.errors:
            print(f"Errors found ({len(self.errors)}):")
            for e in self.errors:
                print(f"  - {e}")
            return False
        print("ALL LOCALIZATION INVARIANTS PASSED (0 errors).")
        return True


def test_reciprocal_seo(repo_root: Path, report: TestReporter) -> None:
    """Test self-canonicals, reciprocal hreflangs, inLanguage, and og:locale."""
    print("Checking reciprocal SEO, canonicals, hreflang, and inLanguage...")
    site_dir = repo_root / "_site"
    base_url = "https://auditcommons.org"

    pages = json.loads((repo_root / "content/pages.json").read_text(encoding="utf-8"))
    canonical_routes = [
        "",
        "latest",
        "features",
        "learn",
        "resources",
        "guides",
        "updates",
        "about",
    ] + [p["slug"] for p in pages]

    for route in canonical_routes:
        clean = route.strip("/")
        en_rel = f"{clean}/index.html" if clean else "index.html"
        zh_rel = f"zh/{clean}/index.html" if clean else "zh/index.html"

        en_path = site_dir / en_rel
        zh_path = site_dir / zh_rel

        report.check()
        if not en_path.exists():
            report.error(f"Missing English route: {en_rel}")
            continue
        report.check()
        if not zh_path.exists():
            report.error(f"Missing Chinese route: {zh_rel}")
            continue

        en_ext = HtmlExtractor()
        en_ext.feed(en_path.read_text(encoding="utf-8"))

        zh_ext = HtmlExtractor()
        zh_ext.feed(zh_path.read_text(encoding="utf-8"))

        # 1. <html> lang attribute
        report.check()
        if en_ext.html_lang != "en":
            report.error(f"{en_rel}: Expected lang='en', got '{en_ext.html_lang}'")
        report.check()
        if zh_ext.html_lang != "zh-CN":
            report.error(f"{zh_rel}: Expected lang='zh-CN', got '{zh_ext.html_lang}'")

        # 2. Canonical URL (self-referential)
        expected_en_canonical = f"{base_url}/{clean}/" if clean else f"{base_url}/"
        expected_zh_canonical = f"{base_url}/zh/{clean}/" if clean else f"{base_url}/zh/"

        report.check()
        if en_ext.canonicals != [expected_en_canonical]:
            report.error(f"{en_rel}: Canonical mismatch: expected {expected_en_canonical}, got {en_ext.canonicals}")
        report.check()
        if zh_ext.canonicals != [expected_zh_canonical]:
            report.error(f"{zh_rel}: Canonical mismatch: expected {expected_zh_canonical}, got {zh_ext.canonicals}")

        # 3. Reciprocal hreflang tags
        en_hmap = dict(en_ext.hreflangs)
        zh_hmap = dict(zh_ext.hreflangs)

        report.check()
        if en_hmap.get("en") != expected_en_canonical:
            report.error(f"{en_rel}: hreflang='en' expected {expected_en_canonical}, got {en_hmap.get('en')}")
        report.check()
        if en_hmap.get("zh-CN") != expected_zh_canonical:
            report.error(f"{en_rel}: hreflang='zh-CN' expected {expected_zh_canonical}, got {en_hmap.get('zh-CN')}")
        report.check()
        if en_hmap.get("x-default") != expected_en_canonical:
            report.error(f"{en_rel}: hreflang='x-default' expected {expected_en_canonical}, got {en_hmap.get('x-default')}")

        report.check()
        if zh_hmap.get("en") != expected_en_canonical:
            report.error(f"{zh_rel}: hreflang='en' expected {expected_en_canonical}, got {zh_hmap.get('en')}")
        report.check()
        if zh_hmap.get("zh-CN") != expected_zh_canonical:
            report.error(f"{zh_rel}: hreflang='zh-CN' expected {expected_zh_canonical}, got {zh_hmap.get('zh-CN')}")
        report.check()
        if zh_hmap.get("x-default") != expected_en_canonical:
            report.error(f"{zh_rel}: hreflang='x-default' expected {expected_en_canonical}, got {zh_hmap.get('x-default')}")

        # 4. OpenGraph locale
        en_og_locale = next((m.get("content") for m in en_ext.meta_tags if m.get("property") == "og:locale"), None)
        zh_og_locale = next((m.get("content") for m in zh_ext.meta_tags if m.get("property") == "og:locale"), None)
        report.check()
        if en_og_locale != "en_US":
            report.error(f"{en_rel}: Expected og:locale='en_US', got '{en_og_locale}'")
        report.check()
        if zh_og_locale != "zh_CN":
            report.error(f"{zh_rel}: Expected og:locale='zh_CN', got '{zh_og_locale}'")

        # 5. JSON-LD inLanguage
        for s in zh_ext.json_ld_scripts:
            report.check()
            try:
                data = json.loads(s)
                if "@type" in data and data.get("@type") != "BreadcrumbList":
                    in_lang = data.get("inLanguage")
                    if in_lang != "zh-CN":
                        report.error(f"{zh_rel}: JSON-LD inLanguage expected 'zh-CN', got '{in_lang}'")
            except Exception as e:
                report.error(f"{zh_rel}: JSON-LD decode error: {e}")

    # Check 404 pages: no hreflangs, noindex
    for p404_rel in ("404.html", "zh/404.html"):
        p404 = site_dir / p404_rel
        report.check()
        if not p404.exists():
            report.error(f"Missing {p404_rel}")
            continue
        p404_ext = HtmlExtractor()
        p404_ext.feed(p404.read_text(encoding="utf-8"))
        report.check()
        if p404_ext.hreflangs:
            report.error(f"{p404_rel}: 404 pages must NOT have hreflang tags")
        robots = next((m.get("content", "") for m in p404_ext.meta_tags if m.get("name") == "robots"), "")
        report.check()
        if "noindex" not in robots:
            report.error(f"{p404_rel}: 404 page must be noindex")


def test_language_switcher(repo_root: Path, report: TestReporter) -> None:
    """Test header language switcher across routes."""
    print("Checking header language switcher contract...")
    site_dir = repo_root / "_site"

    test_routes = [
        ("index.html", "/", "/zh/"),
        ("resources/index.html", "/resources/", "/zh/resources/"),
        ("guides/audit-an-agent-action/index.html", "/guides/audit-an-agent-action/", "/zh/guides/audit-an-agent-action/"),
        ("about/index.html", "/about/", "/zh/about/"),
        ("404.html", "/404.html", "/zh/404.html"),
        ("zh/index.html", "/", "/zh/"),
        ("zh/resources/index.html", "/resources/", "/zh/resources/"),
        ("zh/guides/audit-an-agent-action/index.html", "/guides/audit-an-agent-action/", "/zh/guides/audit-an-agent-action/"),
        ("zh/about/index.html", "/about/", "/zh/about/"),
        ("zh/404.html", "/404.html", "/zh/404.html"),
    ]

    for rel_path, expected_en_href, expected_zh_href in test_routes:
        p = site_dir / rel_path
        report.check()
        if not p.exists():
            report.error(f"Missing page: {rel_path}")
            continue

        ext = HtmlExtractor()
        ext.feed(p.read_text(encoding="utf-8"))

        is_zh_page = rel_path.startswith("zh/")

        report.check()
        if len(ext.lang_switch_links) != 2:
            report.error(f"{rel_path}: Expected 2 language switch links, found {len(ext.lang_switch_links)}")
            continue

        en_link, zh_link = ext.lang_switch_links[0], ext.lang_switch_links[1]

        report.check()
        if en_link.get("href") != expected_en_href:
            report.error(f"{rel_path}: Language switch EN href expected '{expected_en_href}', got '{en_link.get('href')}'")

        report.check()
        if zh_link.get("href") != expected_zh_href:
            report.error(f"{rel_path}: Language switch 中文 href expected '{expected_zh_href}', got '{zh_link.get('href')}'")

        if is_zh_page:
            report.check()
            if zh_link.get("aria-current") != "true" or "is-active" not in zh_link.get("class", ""):
                report.error(f"{rel_path}: 中文 link should have aria-current='true' and is-active")
            report.check()
            if en_link.get("aria-current") == "true" or "is-active" in en_link.get("class", ""):
                report.error(f"{rel_path}: EN link should not be active on Chinese page")
        else:
            report.check()
            if en_link.get("aria-current") != "true" or "is-active" not in en_link.get("class", ""):
                report.error(f"{rel_path}: EN link should have aria-current='true' and is-active")
            report.check()
            if zh_link.get("aria-current") == "true" or "is-active" in zh_link.get("class", ""):
                report.error(f"{rel_path}: 中文 link should not be active on English page")


def test_resource_catalog_chinese(repo_root: Path, report: TestReporter) -> None:
    """Test Chinese resource catalog structure and data contract."""
    print("Checking Chinese resource catalog against the current source...")
    site_dir = repo_root / "_site"
    resources = json.loads((repo_root / "content/resources.json").read_text(encoding="utf-8"))
    expected_count = len(resources)
    zh_res_html = (site_dir / "zh/resources/index.html").read_text(encoding="utf-8")

    ext = HtmlExtractor()
    ext.feed(zh_res_html)

    report.check()
    if len(ext.resource_cards) != expected_count:
        report.error(f"zh/resources: Expected {expected_count} resource cards, found {len(ext.resource_cards)}")

    # Check for Chinese labels in filter buttons and format tabs
    for cat_en, cat_zh in CATEGORY_DISPLAY_LABELS_ZH.items():
        report.check()
        if f'data-filter="{cat_en}"' not in zh_res_html:
            report.error(f"zh/resources: Missing category filter button data-filter='{cat_en}'")
        report.check()
        if cat_zh not in zh_res_html:
            report.error(f"zh/resources: Missing Chinese category label '{cat_zh}'")

    for fmt_en, fmt_zh in FORMAT_DISPLAY_LABELS_ZH.items():
        report.check()
        if fmt_zh not in zh_res_html:
            report.error(f"zh/resources: Missing Chinese format label '{fmt_zh}'")

    # Check status announcement
    report.check()
    if f'id="resource-count" role="status" aria-live="polite">显示全部 {expected_count} 项资源</div>' not in zh_res_html:
        report.error("zh/resources: #resource-count missing localized initial text with current catalog count")

    # Check that search terms on cards contain Chinese text
    cards_with_zh_search = 0
    for card in ext.resource_cards:
        search_val = card.get("data-search", "")
        # Checks if contains CJK Unified Ideographs
        if re.search(r"[\u4e00-\u9fff]", search_val):
            cards_with_zh_search += 1

    report.check()
    if cards_with_zh_search != expected_count:
        report.error(f"zh/resources: Expected all {expected_count} cards to have Chinese search terms, found {cards_with_zh_search}")


def test_chinese_body_links(repo_root: Path, report: TestReporter) -> None:
    """Test localized body content links in articles."""
    print("Checking internal link localization in Chinese article bodies...")
    site_dir = repo_root / "_site"
    pages = json.loads((repo_root / "content/pages.json").read_text(encoding="utf-8"))

    for p in pages:
        slug = p["slug"]
        zh_path = site_dir / "zh" / slug / "index.html"
        report.check()
        if not zh_path.exists():
            report.error(f"Missing Chinese article: zh/{slug}/index.html")
            continue

        html_text = zh_path.read_text(encoding="utf-8")
        # Match <article class="article-body">...</article>
        m = re.search(r'<article class="article-body">(.*?)</article>', html_text, re.S)
        report.check()
        if not m:
            report.error(f"zh/{slug}: Could not locate article-body element")
            continue

        body_html = m.group(1)
        # Find all hrefs
        hrefs = re.findall(r'href="([^"]+)"', body_html)
        for href in hrefs:
            report.check()
            if href.startswith(("#", "http://", "https://", "mailto:", "javascript:", "tel:")):
                continue
            if href.startswith(("/assets/", "/favicon", "/social-preview")):
                continue
            # Internal navigation links should be prefixed with /zh/
            if href.startswith("/"):
                if not href.startswith("/zh/"):
                    report.error(f"zh/{slug}: Unlocalized root-relative link in article body: '{href}'")


def test_overlay_invariants_and_fail_early(repo_root: Path, report: TestReporter) -> None:
    """Test overlay validation, hash rejection, and fail-early invariants."""
    print("Checking translation overlay contracts and fail-early behaviors...")
    content_dir = repo_root / "content"

    pages = json.loads((content_dir / "pages.json").read_text(encoding="utf-8"))
    resources = json.loads((content_dir / "resources.json").read_text(encoding="utf-8"))

    # 1. Valid overlays should pass validation without error
    report.check()
    try:
        overlays = validate_translation_overlays(content_dir, pages, resources)
        if overlays is None:
            report.error("Expected overlays to be loaded and validated successfully")
    except Exception as e:
        report.error(f"Unexpected overlay validation failure: {e}")

    # 2. Stale sha256 rejection test
    report.check()
    tampered_pages = copy.deepcopy(pages)
    tampered_pages[0]["title"] = "Tampered English Title"
    try:
        validate_translation_overlays(content_dir, tampered_pages, resources)
        report.error("Stale page sha256 was NOT rejected as expected")
    except ValueError as ve:
        if "stale" not in str(ve) and "source_sha256" not in str(ve):
            report.error(f"Expected stale hash error, got: {ve}")

    # 3. Missing page translation test
    report.check()
    pages_missing = copy.deepcopy(pages)
    pages_missing.append({
        "slug": "guides/new-untranslated-guide",
        "title": "New",
        "summary": "New",
        "author": "Audit Commons",
        "published": "2026-09-16",
        "kind": "guide",
        "body_file": pages[0]["body_file"],
    })
    try:
        validate_translation_overlays(content_dir, pages_missing, resources)
        report.error("Missing page translation overlay was NOT rejected as expected")
    except ValueError as ve:
        if "Missing Chinese translation" not in str(ve):
            report.error(f"Expected missing translation error, got: {ve}")

    # 4. Prohibited field rejection test
    allowed_page_keys = {"title", "summary", "topics", "body_file", "affiliation_disclosure", "source_sha256"}
    zh_pages_file = content_dir / "zh/pages.json"
    zh_pages = json.loads(zh_pages_file.read_text(encoding="utf-8"))
    for slug, p_entry in zh_pages.items():
        report.check()
        diff = set(p_entry.keys()) - allowed_page_keys
        if diff:
            report.error(f"content/zh/pages.json entry '{slug}' has prohibited keys: {diff}")

    allowed_res_keys = {"summary", "source_sha256"}
    zh_res_file = content_dir / "zh/resources.json"
    zh_res = json.loads(zh_res_file.read_text(encoding="utf-8"))
    for res_id, r_entry in zh_res.items():
        report.check()
        diff = set(r_entry.keys()) - allowed_res_keys
        if diff:
            report.error(f"content/zh/resources.json entry '{res_id}' has prohibited keys: {diff}")


def test_media_overlays(repo_root: Path, report: TestReporter) -> None:
    """Test media translations in Chinese edition."""
    print("Checking media translations...")
    site_dir = repo_root / "_site"
    content_dir = repo_root / "content"

    media_overlay_file = content_dir / "zh/media.json"
    if not media_overlay_file.exists():
        return

    zh_media = json.loads(media_overlay_file.read_text(encoding="utf-8"))
    # Verify translated captions or alts appear in the Chinese HTML output
    sample_caption = None
    for k, v in zh_media.items():
        if v.get("caption"):
            sample_caption = v.get("caption")
            break

    if sample_caption:
        report.check()
        found = False
        for p in (site_dir / "zh").rglob("*.html"):
            if sample_caption in p.read_text(encoding="utf-8"):
                found = True
                break
        if not found:
            report.error(f"Translated media caption not found in Chinese site: '{sample_caption}'")


def test_media_and_path_rejection(repo_root: Path, report: TestReporter) -> None:
    import shutil
    import tempfile
    from build import build_site

    with tempfile.TemporaryDirectory() as scratch:
        content = Path(scratch) / "content"
        output = Path(scratch) / "output"
        shutil.copytree(repo_root / "content", content)
        output.mkdir()
        sentinel = output / "preserve.txt"
        sentinel.write_text("existing output", encoding="utf-8")
        media_file = content / "zh/media.json"
        pages_file = content / "zh/pages.json"
        original_media = media_file.read_text(encoding="utf-8")
        original_pages = pages_file.read_text(encoding="utf-8")
        for case, expected_error in (("missing", "coverage mismatch"), ("unknown", "coverage mismatch"), ("stale", "source_sha256 mismatch"), ("path", "path traversal")):
            media = json.loads(original_media)
            pages = json.loads(original_pages)
            first = next(iter(media))
            if case == "missing":
                media.pop(first)
            elif case == "unknown":
                media["unknown-test-asset"] = media[first]
            elif case == "stale":
                media[first]["source_sha256"] = "0" * 64
            else:
                pages[next(iter(pages))]["body_file"] = "zh/bodies/../../bodies/about.html"
            media_file.write_text(json.dumps(media), encoding="utf-8")
            pages_file.write_text(json.dumps(pages), encoding="utf-8")
            report.check()
            try:
                build_site(repo_root, content, output, repo_root / "assets")
            except ValueError as error:
                if expected_error not in str(error):
                    report.error(f"{case}: wrong rejection: {error}")
            else:
                report.error(f"{case}: invalid translation allowed")
            if not sentinel.exists() or sentinel.read_text(encoding="utf-8") != "existing output":
                report.error(f"{case}: existing output was modified before rejection")


def test_chinese_feed(repo_root: Path, report: TestReporter) -> None:
    import xml.etree.ElementTree as ET
    from html.parser import HTMLParser
    import re

    ns = {"a": "http://www.w3.org/2005/Atom"}
    zh_feed_file = repo_root / "_site/zh/feed.xml"
    if not zh_feed_file.exists():
        report.error("Chinese Atom feed _site/zh/feed.xml is missing")
        return

    tree = ET.parse(zh_feed_file)
    sources = json.loads((repo_root / "content/pages.json").read_text(encoding="utf-8"))
    overlays = json.loads((repo_root / "content/zh/pages.json").read_text(encoding="utf-8"))
    zh_media = json.loads((repo_root / "content/zh/media.json").read_text(encoding="utf-8"))
    manifest = json.loads((repo_root / "content/media.json").read_text(encoding="utf-8"))
    art_media_keys = manifest.get("articles", {})
    expected = {p["slug"]: overlays[p["slug"]] for p in sources if p["kind"] != "about"}
    entries = tree.findall("a:entry", ns)
    report.check()
    if len(entries) != len(expected):
        report.error("Chinese Atom feed does not cover all published articles")
    found = set()
    for entry in entries:
        link = entry.find("a:link", ns)
        path = urlparse(link.get("href", "") if link is not None else "").path
        slug = path.removeprefix("/zh/").strip("/")
        report.check()
        if not path.startswith("/zh/") or slug not in expected or entry.findtext("a:title", namespaces=ns) != expected[slug]["title"]:
            report.error(f"Chinese Atom entry has wrong URL or translated title: {path}")
        found.add(slug)

        orig_p = next(p for p in sources if p["slug"] == slug)
        expected_url = f"https://auditcommons.org/zh/{slug}/"
        pub_date = orig_p["published"]
        upd_date = orig_p.get("updated") or pub_date

        report.check()
        if entry.findtext("a:id", namespaces=ns) != expected_url:
            report.error(f"Chinese Atom entry ID mismatch for {slug}")
        if entry.findtext("a:published", namespaces=ns) != f"{pub_date}T00:00:00Z":
            report.error(f"Chinese Atom entry published date mismatch for {slug}")
        if entry.findtext("a:updated", namespaces=ns) != f"{upd_date}T00:00:00Z":
            report.error(f"Chinese Atom entry updated date mismatch for {slug}")
        if entry.findtext("a:summary", namespaces=ns) != expected[slug]["summary"]:
            report.error(f"Chinese Atom entry summary mismatch for {slug}")

        # Content inspections
        content = entry.findtext("a:content", namespaces=ns) or ""
        report.check()
        if not content:
            report.error(f"Chinese Atom entry content empty for {slug}")
            continue

        class _ZHContentInspector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.hrefs = []
                self.srcs = []
                self.has_nav = False
                self.has_follow = False

            def handle_starttag(self, tag, attrs):
                d = dict(attrs)
                if "href" in d:
                    self.hrefs.append(d["href"])
                if "src" in d:
                    self.srcs.append(d["src"])
                cl = d.get("class", "").split()
                if "site-nav" in cl:
                    self.has_nav = True
                if "follow-section" in cl or "follow-box" in cl:
                    self.has_follow = True

        insp = _ZHContentInspector()
        try:
            insp.feed(content)
        except Exception as ex:
            report.error(f"Chinese Atom entry HTML parse failure for {slug}: {ex}")

        report.check()
        if insp.has_nav:
            report.error(f"Chinese Atom entry {slug} injected site navbar")
        if insp.has_follow:
            report.error(f"Chinese Atom entry {slug} injected follow widget")

        for h in insp.hrefs:
            if not h.startswith(("http://", "https://", "mailto:", "tel:")):
                report.error(f"Chinese Atom entry {slug} contains non-absolute href: {h}")
            elif h.startswith("#"):
                report.error(f"Chinese Atom entry {slug} contains unresolved fragment: {h}")

        for s in insp.srcs:
            if not s.startswith(("http://", "https://")):
                report.error(f"Chinese Atom entry {slug} contains non-absolute src: {s}")

        # Substantive body check
        zh_body_file = repo_root / "content" / expected[slug]["body_file"]
        if zh_body_file.is_file():
            headings = re.findall(r"<h[2-4][^>]*>(.*?)</h[2-4]>", zh_body_file.read_text(encoding="utf-8"))
            if headings:
                first_h = re.sub(r"<[^>]+>", "", headings[0]).strip()
                report.check()
                if first_h and first_h not in content:
                    report.error(f"Chinese Atom entry {slug} missing body heading: '{first_h}'")

        # Editorial media check
        mkey = art_media_keys.get(slug)
        report.check()
        if mkey:
            if "<figure" not in content or "media-article" not in content:
                report.error(f"Chinese Atom entry {slug} missing lead figure")
            if mkey in zh_media and zh_media[mkey]["caption"] not in content:
                report.error(f"Chinese Atom entry {slug} missing Chinese media caption")
        else:
            if "<figure" in content and "media-article" in content:
                report.error(f"Chinese Atom entry {slug} unexpectedly has lead figure")

        # Permalink check
        report.check()
        if "在 Audit Commons 阅读全文" not in content or expected_url not in content:
            report.error(f"Chinese Atom entry {slug} missing Chinese permalink")

    if found != set(expected):
        report.error("Chinese Atom feed has missing or duplicate entries")


def main() -> int:
    repo_root = Path.cwd().resolve()
    report = TestReporter()

    print("=== Audit Commons Localization Invariant Suite ===")
    test_reciprocal_seo(repo_root, report)
    test_language_switcher(repo_root, report)
    test_resource_catalog_chinese(repo_root, report)
    test_chinese_body_links(repo_root, report)
    test_overlay_invariants_and_fail_early(repo_root, report)
    test_media_overlays(repo_root, report)
    test_media_and_path_rejection(repo_root, report)
    test_chinese_feed(repo_root, report)

    passed = report.summary()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
