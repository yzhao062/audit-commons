#!/usr/bin/env python3
"""
Audit Commons Output & Content Validation Suite
Rigorous, zero-dependency validation script verifying schema compliance,
output generation, internal links, fragment anchors, sitemap/feed invariants,
private file exclusion, safety guardrails, and accessibility contracts.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET
from resource_formats import formats_error
from editorial_media import social_image_eligible


class HtmlStructureExtractor(HTMLParser):
    """Parses an HTML document to extract IDs, links, assets, and semantic elements."""

    def __init__(self) -> None:
        super().__init__()
        self.element_ids: Set[str] = set()
        self.links: List[Tuple[str, int]] = []  # (href, line_number)
        self.asset_sources: List[Tuple[str, str, int]] = []  # (tag, src/href, line_number)
        self.images: List[Dict[str, str]] = []
        self.meta_tags: List[Dict[str, str]] = []
        self.has_skip_link: bool = False
        self.has_main: bool = False
        self.main_tabindex: Optional[str] = None
        self.has_site_header: bool = False
        self.has_site_nav: bool = False
        self.has_site_footer: bool = False
        self.brand_uses_mark_svg: bool = False
        self.json_ld_scripts: List[str] = []
        self.has_h1: bool = False
        self.h1_count: int = 0
        self.title: str = ""
        self.canonicals: List[str] = []
        self._in_title: bool = False

        # Resource page specific elements
        self.has_resource_controls: bool = False
        self.resource_controls_hidden: bool = False
        self.has_resource_search: bool = False
        self.filter_buttons: List[Dict[str, str]] = []
        self.has_tablist: bool = False
        self.tablist_aria_label: Optional[str] = None
        self.format_tabs: List[Dict[str, str]] = []
        self.tabpanels: List[Dict[str, str]] = []
        self.has_resource_count: bool = False
        self.resource_count_role_status: bool = False
        self.has_no_results: bool = False
        self.no_results_hidden: bool = False
        self.resource_cards: List[Dict[str, str]] = []

        self._in_script_json_ld: bool = False
        self._current_script_buffer: List[str] = []
        self._in_brand: bool = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        elem_id = attr_dict.get("id")
        elem_classes = attr_dict.get("class", "").split()
        if tag == "title":
            self._in_title = True
        if tag == "link" and attr_dict.get("rel") == "canonical":
            self.canonicals.append(attr_dict.get("href", ""))

        if elem_id:
            self.element_ids.add(elem_id)

        # Main landmark and tabindex
        if tag == "main" and elem_id == "main":
            self.has_main = True
            self.main_tabindex = attr_dict.get("tabindex")

        # Header / Nav / Footer
        if tag == "header" and "site-header" in elem_classes:
            self.has_site_header = True
        if tag == "nav" and "site-nav" in elem_classes:
            self.has_site_nav = True
        if tag == "footer" and "site-footer" in elem_classes:
            self.has_site_footer = True

        # Skip link
        if tag == "a" and "skip-link" in elem_classes:
            self.has_skip_link = True

        # Brand mark tracking
        if tag == "a" and "brand" in elem_classes:
            self._in_brand = True
        if self._in_brand and tag == "img":
            src = urlparse(attr_dict.get("src", "")).path
            if src.endswith("mark.svg") or src == "/assets/mark.svg":
                self.brand_uses_mark_svg = True

        # Headings
        if tag == "h1":
            self.has_h1 = True
            self.h1_count += 1

        # Links
        if tag == "a" and "href" in attr_dict:
            href = attr_dict["href"]
            self.links.append((href, self.getpos()[0]))

        # Assets & Dependencies
        if tag == "img":
            self.images.append(attr_dict)
        if tag in ("img", "script") and "src" in attr_dict:
            self.asset_sources.append((tag, attr_dict["src"], self.getpos()[0]))
        if tag == "link" and "href" in attr_dict:
            self.asset_sources.append((tag, attr_dict["href"], self.getpos()[0]))

        # Meta tags
        if tag == "meta":
            self.meta_tags.append(attr_dict)

        # JSON-LD scripts
        if tag == "script" and attr_dict.get("type") == "application/ld+json":
            self._in_script_json_ld = True
            self._current_script_buffer = []

        # Resource specific contract components
        if elem_id == "resource-controls":
            self.has_resource_controls = True
            self.resource_controls_hidden = "hidden" in attr_dict or attr_dict.get("hidden") == "hidden"

        if elem_id == "resource-search" and tag == "input" and attr_dict.get("type") == "search":
            self.has_resource_search = True

        if tag == "button" and "data-filter" in attr_dict:
            self.filter_buttons.append(attr_dict)

        if attr_dict.get("role") == "tablist":
            self.has_tablist = True
            self.tablist_aria_label = attr_dict.get("aria-label")

        if attr_dict.get("role") == "tab":
            self.format_tabs.append(attr_dict)

        if attr_dict.get("role") == "tabpanel":
            self.tabpanels.append(attr_dict)

        if elem_id == "resource-count":
            self.has_resource_count = True
            if attr_dict.get("role") == "status":
                self.resource_count_role_status = True

        if elem_id == "no-results":
            self.has_no_results = True
            self.no_results_hidden = "hidden" in attr_dict or attr_dict.get("hidden") == "hidden"

        if "resource-card" in elem_classes:
            self.resource_cards.append(attr_dict)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._in_brand:
            self._in_brand = False
        if tag == "script" and self._in_script_json_ld:
            self._in_script_json_ld = False
            self.json_ld_scripts.append("".join(self._current_script_buffer))
            self._current_script_buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._in_script_json_ld:
            self._current_script_buffer.append(data)


class ValidationReport:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checks_run: int = 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def check(self) -> None:
        self.checks_run += 1

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def validate_base_url_origin(base_url: str, report: ValidationReport) -> None:
    """Validates that base URL is an origin only (no userinfo, query, fragment, or subpaths)."""
    report.check()
    parsed = urlparse(base_url)
    if parsed.scheme not in ("https", "http"):
        report.error(f"Base URL scheme must be https or http, got '{parsed.scheme}' in '{base_url}'")
    if not parsed.netloc:
        report.error(f"Base URL missing host/origin: '{base_url}'")
    if parsed.username or parsed.password:
        report.error(f"Base URL contains user credentials: '{base_url}'")
    if parsed.query:
        report.error(f"Base URL contains query string: '{base_url}'")
    if parsed.fragment:
        report.error(f"Base URL contains fragment: '{base_url}'")
    if parsed.path and parsed.path != "/":
        report.error(f"Base URL must be origin-only; subpath '{parsed.path}' is not supported")


def validate_sources(content_dir: Path, report: ValidationReport) -> None:
    """Validates schema, dates, and invariants in content/ files."""
    # 1. site.json
    site_file = content_dir / "site.json"
    report.check()
    if not site_file.exists():
        report.error(f"Missing required metadata file: {site_file}")
        return
    try:
        with open(site_file, "r", encoding="utf-8") as f:
            site_data = json.load(f)
    except Exception as e:
        report.error(f"Failed to parse {site_file}: {e}")
        return

    for field in ("name", "tagline", "description", "maintainer", "base_url"):
        report.check()
        if field not in site_data:
            report.error(f"site.json missing required property '{field}'")

    if site_data.get("tagline") != "News, analysis, and learning about AI auditing.":
        report.error(f"site.json tagline must match exact contract: 'News, analysis, and learning about AI auditing.', got: '{site_data.get('tagline')}'")

    validate_base_url_origin(site_data.get("base_url", ""), report)

    # 2. pages.json
    pages_file = content_dir / "pages.json"
    report.check()
    if not pages_file.exists():
        report.error(f"Missing required file: {pages_file}")
        return
    try:
        with open(pages_file, "r", encoding="utf-8") as f:
            pages = json.load(f)
    except Exception as e:
        report.error(f"Failed to parse {pages_file}: {e}")
        return

    if not isinstance(pages, list):
        report.error("pages.json must be a list of page objects")
        return

    seen_slugs = set()
    valid_kinds = {"introduction", "guide", "release", "about", "news", "feature"}
    for idx, page in enumerate(pages):
        report.check()
        slug = page.get("slug")
        if not slug:
            report.error(f"Page #{idx} missing 'slug'")
            continue
        if slug in seen_slugs:
            report.error(f"Duplicate slug '{slug}' in pages.json")
        seen_slugs.add(slug)

        # Validate author
        if page.get("author") != "Audit Commons":
            report.error(f"Page '{slug}' author must be 'Audit Commons' (no personal bylines or invented teams), got: '{page.get('author')}'")

        # Validate kind
        kind = page.get("kind")
        if kind not in valid_kinds:
            report.error(f"Page '{slug}' kind must be one of {valid_kinds}, got '{kind}'")
        prefix = {"news": "news/", "feature": "features/", "guide": "guides/", "release": "updates/"}.get(kind)
        if prefix and not slug.startswith(prefix):
            report.error(f"Page '{slug}' of kind '{kind}' must live under '{prefix}'")

        # Validate dates
        if kind in {"news", "release"}:
            try:
                datetime.strptime(page.get("event_date", ""), "%Y-%m-%d")
            except (ValueError, TypeError):
                report.error(f"Page '{slug}' requires a valid event_date in YYYY-MM-DD format")
        pub = page.get("published")
        if not pub:
            report.error(f"Page '{slug}' missing 'published' date")
        else:
            try:
                datetime.strptime(pub, "%Y-%m-%d")
            except ValueError:
                report.error(f"Page '{slug}' published date '{pub}' is not valid YYYY-MM-DD")

        upd = page.get("updated")
        if upd:
            try:
                datetime.strptime(upd, "%Y-%m-%d")
            except ValueError:
                report.error(f"Page '{slug}' updated date '{upd}' is not valid YYYY-MM-DD")

        # Validate body_file
        bf = page.get("body_file")
        if not bf:
            report.error(f"Page '{slug}' missing 'body_file'")
        else:
            bf_path = content_dir / bf
            if not bf_path.exists():
                report.error(f"Page '{slug}' body file does not exist: {bf_path}")
            else:
                body_content = bf_path.read_text(encoding="utf-8")
                if "<article" in body_content.lower():
                    report.error(f"Page '{slug}' body HTML must not contain outer <article> tag")
                if "<h1" in body_content.lower():
                    report.error(f"Page '{slug}' body HTML must not contain <h1> tag (template provides <h1>)")

    # 3. resources.json
    res_file = content_dir / "resources.json"
    report.check()
    if not res_file.exists():
        report.error(f"Missing required file: {res_file}")
        return
    try:
        with open(res_file, "r", encoding="utf-8") as f:
            resources = json.load(f)
    except Exception as e:
        report.error(f"Failed to parse {res_file}: {e}")
        return

    if not isinstance(resources, list):
        report.error("resources.json must be a list of resource objects")
        return

    seen_ids = set()
    valid_categories = {"Evaluation", "Security", "Governance", "Reading", "Tools"}
    valid_relationships = {"External resource", "Maintainer project"}
    valid_formats = {"Paper", "Tool", "Benchmark", "Dataset", "Standard", "Collection"}
    for idx, r in enumerate(resources):
        report.check()
        r_id = r.get("id")
        if not r_id:
            report.error(f"Resource #{idx} missing 'id'")
            continue
        if r_id in seen_ids:
            report.error(f"Duplicate resource ID '{r_id}'")
        seen_ids.add(r_id)

        for req in ("name", "category", "summary", "url", "owner", "relationship", "checked"):
            report.check()
            if not r.get(req):
                report.error(f"Resource '{r_id}' missing required property '{req}'")

        if r.get("category") not in valid_categories:
            report.error(f"Resource '{r_id}' invalid category '{r.get('category')}'; expected {valid_categories}")

        if r.get("relationship") not in valid_relationships:
            report.error(f"Resource '{r_id}' invalid relationship '{r.get('relationship')}'; expected {valid_relationships}")

        chk = r.get("checked")
        if not chk:
            report.error(f"Resource '{r_id}' missing 'checked' date")
        else:
            try:
                datetime.strptime(chk, "%Y-%m-%d")
            except ValueError:
                report.error(f"Resource '{r_id}' checked date '{chk}' is not valid YYYY-MM-DD")

        # Validate new optional fields when present
        report.check()
        if error := formats_error(r):
            report.error(f"Resource '{r_id}': {error}")
        if "format" in r:
            fmt = r.get("format")
            if fmt not in valid_formats:
                report.error(f"Resource '{r_id}' invalid format '{fmt}'; expected {valid_formats}")

        if "source_section" in r:
            sec = r.get("source_section")
            if not isinstance(sec, str) or not sec.strip():
                report.error(f"Resource '{r_id}' source_section must be a non-empty string when present")

        if "venue" in r:
            ven = r.get("venue")
            if not isinstance(ven, str) or not ven.strip():
                report.error(f"Resource '{r_id}' venue must be a non-empty string when present")

        if "catalog_source" in r:
            cs = r.get("catalog_source")
            if not isinstance(cs, str) or not cs.startswith(("http://", "https://")):
                report.error(f"Resource '{r_id}' catalog_source must be a valid HTTP(S) URL when present")

        if "links" in r:
            links = r.get("links")
            if not isinstance(links, list):
                report.error(f"Resource '{r_id}' links must be a list of link objects when present")
            else:
                for l_idx, lk in enumerate(links):
                    if not isinstance(lk, dict) or not lk.get("label") or not lk.get("url"):
                        report.error(f"Resource '{r_id}' link #{l_idx} must contain 'label' and 'url'")

        if "source_urls" in r:
            s_urls = r.get("source_urls")
            if not isinstance(s_urls, list):
                report.error(f"Resource '{r_id}' source_urls must be a list of URLs when present")

    zh_dir = content_dir / "zh"
    if zh_dir.exists() and zh_dir.is_dir():
        from localization import validate_translation_overlays
        try:
            validate_translation_overlays(content_dir, pages, resources)
        except Exception as e:
            report.error(f"Chinese translation overlay validation failed: {e}")


def validate_output_directory(
    output_dir: Path,
    expected_base_url: str,
    report: ValidationReport,
    content_dir: Optional[Path] = None,
) -> None:
    """Validates generated site structure, links, fragments, assets, and contracts."""
    if not output_dir.exists() or not output_dir.is_dir():
        report.error(f"Output directory does not exist: {output_dir}")
        return

    validate_base_url_origin(expected_base_url, report)

    # Check required contract routes
    required_routes = [
        "index.html",
        "start-here/index.html",
        "resources/index.html",
        "guides/index.html",
        "guides/audit-an-agent-action/index.html",
        "updates/index.html",
        "updates/catchbench-0-1-2/index.html",
        "about/index.html",
        "latest/index.html",
        "features/index.html",
        "learn/index.html",
        "404.html",
    ]

    for route in required_routes:
        report.check()
        target = output_dir / route
        if not target.exists():
            report.error(f"Missing required route file: {route}")

    # Check required metadata files
    for meta_file in ("sitemap.xml", "robots.txt", "feed.xml", ".nojekyll"):
        report.check()
        target = output_dir / meta_file
        if not target.exists():
            report.error(f"Missing required metadata file: {meta_file}")

    # Private file exclusion check
    forbidden_patterns = [
        re.compile(r".*\.py$"),
        re.compile(r".*\.pyc$"),
        re.compile(r".*\.local\.md$"),
        re.compile(r".*README.*\.md$"),
        re.compile(r".*CONTRIBUTING.*\.md$"),
        re.compile(r".*\.git.*"),
    ]
    for root, _, files in os.walk(output_dir):
        for fname in files:
            report.check()
            rel_path = Path(root, fname).relative_to(output_dir).as_posix()
            for pat in forbidden_patterns:
                if pat.match(rel_path):
                    report.error(f"Private or repository file leaked into build output: {rel_path}")

    # Validate 404 Usability and Sitemap Exclusion
    page_404 = output_dir / "404.html"
    if page_404.exists():
        content_404 = page_404.read_text(encoding="utf-8")
        report.check()
        if "noindex" not in content_404:
            report.error("404.html must include <meta name='robots' content='noindex...'>")
        if len(content_404) < 300:
            report.error("404.html is too brief to be usable")

    # Validate Sitemap
    sitemap_file = output_dir / "sitemap.xml"
    sitemap_urls: Set[str] = set()
    if sitemap_file.exists():
        report.check()
        try:
            tree = ET.parse(sitemap_file)
            root = tree.getroot()
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall("sm:url/sm:loc", ns):
                if loc.text:
                    sitemap_urls.add(loc.text.strip())

            if not sitemap_urls:
                for loc in root.iter():
                    if loc.tag.endswith("loc") and loc.text:
                        sitemap_urls.add(loc.text.strip())

            for u in sitemap_urls:
                if "404" in u:
                    report.error(f"Sitemap must not contain 404 error page: {u}")
                if not u.startswith(expected_base_url.rstrip("/")):
                    report.error(f"Sitemap URL '{u}' does not match expected base URL '{expected_base_url}'")

        except Exception as e:
            report.error(f"Failed to parse sitemap.xml: {e}")

    # Validate Feed(s) - full-content bilingual regression checks
    def _validate_feed(feed_file: Path, feed_locale: str) -> None:
        if not feed_file.exists():
            return
        report.check()
        try:
            tree = ET.parse(feed_file)
            root = tree.getroot()
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns) or [e for e in root.iter() if e.tag.endswith("entry")]
            if not entries:
                report.error(f"{feed_file.name} must contain at least one <entry>")
                return

            expected_feed_url = f"{expected_base_url.rstrip('/')}/zh/feed.xml" if feed_locale == "zh" else f"{expected_base_url.rstrip('/')}/feed.xml"
            feed_id = root.findtext("atom:id", default="", namespaces=ns) or next((c.text for c in root if c.tag.endswith("id")), "")
            if feed_id != expected_feed_url:
                report.error(f"{feed_file.name} id mismatch: expected '{expected_feed_url}', got '{feed_id}'")

            def _find_elem(parent: ET.Element, tag_name: str) -> Optional[ET.Element]:
                elem = parent.find(f"atom:{tag_name}", ns)
                if elem is not None:
                    return elem
                for child in parent:
                    if child.tag.endswith(tag_name):
                        return child
                return None

            resolved_content_dir = content_dir or (output_dir.parent / "content")
            if not resolved_content_dir.exists():
                for entry in entries:
                    title_e = _find_elem(entry, "title")
                    link_e = _find_elem(entry, "link")
                    id_e = _find_elem(entry, "id")
                    content_e = _find_elem(entry, "content")
                    if title_e is None or not (title_e.text or "").strip():
                        report.error(f"{feed_file.name} entry missing title")
                    if link_e is None or not link_e.get("href"):
                        report.error(f"{feed_file.name} entry missing link href")
                    if id_e is None or not (id_e.text or "").strip():
                        report.error(f"{feed_file.name} entry missing id")
                    if content_e is None or not (content_e.text or "").strip():
                        report.error(f"{feed_file.name} entry missing content")
                return

            pages_file = resolved_content_dir / "pages.json"
            if not pages_file.exists():
                return
            source_pages = json.loads(pages_file.read_text(encoding="utf-8"))
            editorial_pages = [p for p in source_pages if p.get("kind") != "about"]

            zh_pages_map: Dict[str, Any] = {}
            zh_media_map: Dict[str, Any] = {}
            if feed_locale == "zh" and (resolved_content_dir / "zh" / "pages.json").exists():
                zh_pages_map = json.loads((resolved_content_dir / "zh" / "pages.json").read_text(encoding="utf-8"))
            if feed_locale == "zh" and (resolved_content_dir / "zh" / "media.json").exists():
                zh_media_map = json.loads((resolved_content_dir / "zh" / "media.json").read_text(encoding="utf-8"))

            manifest_data: Dict[str, Any] = {}
            if (resolved_content_dir / "media.json").exists():
                try:
                    manifest_data = json.loads((resolved_content_dir / "media.json").read_text(encoding="utf-8"))
                except Exception:
                    pass
            article_media_keys = manifest_data.get("articles", {})

            # Check coverage
            if len(entries) != len(editorial_pages):
                report.error(f"{feed_file.name} entries count mismatch: expected {len(editorial_pages)}, got {len(entries)}")

            # Check reverse-chronological order
            entry_pub_dates = []
            for entry in entries:
                pub_elem = _find_elem(entry, "published")
                if pub_elem is not None and pub_elem.text:
                    entry_pub_dates.append(pub_elem.text)
            if entry_pub_dates != sorted(entry_pub_dates, reverse=True):
                report.error(f"{feed_file.name} entries not in reverse-chronological order by published date")

            # Validate each entry
            for entry in entries:
                report.check()
                title_elem = _find_elem(entry, "title")
                link_elem = _find_elem(entry, "link")
                id_elem = _find_elem(entry, "id")
                pub_elem = _find_elem(entry, "published")
                upd_elem = _find_elem(entry, "updated")
                sum_elem = _find_elem(entry, "summary")
                content_elem = _find_elem(entry, "content")

                if title_elem is None or not (title_elem.text or "").strip():
                    report.error(f"{feed_file.name} entry missing title")
                if link_elem is None or not link_elem.get("href"):
                    report.error(f"{feed_file.name} entry missing link href")
                if id_elem is None or not (id_elem.text or "").strip():
                    report.error(f"{feed_file.name} entry missing id")
                if pub_elem is None or not (pub_elem.text or "").strip():
                    report.error(f"{feed_file.name} entry missing published")
                if upd_elem is None or not (upd_elem.text or "").strip():
                    report.error(f"{feed_file.name} entry missing updated")
                if content_elem is None or not (content_elem.text or "").strip():
                    report.error(f"{feed_file.name} entry missing content")
                    continue

                entry_url = link_elem.get("href", "")
                entry_id = id_elem.text.strip() if (id_elem is not None and id_elem.text) else ""

                # Identity preservation: ID must equal canonical article URL
                if entry_id != entry_url:
                    report.error(f"{feed_file.name} entry ID '{entry_id}' != link '{entry_url}'")

                path = urlparse(entry_url).path
                slug = path.removeprefix("/zh/").strip("/") if feed_locale == "zh" else path.strip("/")
                orig_p = next((p for p in editorial_pages if p["slug"] == slug), None)
                if not orig_p:
                    report.error(f"{feed_file.name} contains unexpected article slug: '{slug}'")
                    continue

                # Identity and dates match source exactly
                expected_pub = f"{orig_p['published']}T00:00:00Z"
                expected_upd = f"{(orig_p.get('updated') or orig_p['published'])}T00:00:00Z"
                if pub_elem.text != expected_pub:
                    report.error(f"{feed_file.name} entry '{slug}' published date mismatch: expected '{expected_pub}', got '{pub_elem.text}'")
                if upd_elem.text != expected_upd:
                    report.error(f"{feed_file.name} entry '{slug}' updated date mismatch: expected '{expected_upd}', got '{upd_elem.text}'")

                # Summary match
                expected_summary = zh_pages_map[slug]["summary"] if feed_locale == "zh" and slug in zh_pages_map else orig_p.get("summary", "")
                if sum_elem is not None and sum_elem.text != expected_summary:
                    report.error(f"{feed_file.name} entry '{slug}' summary does not match source summary")

                # Parse and inspect content HTML
                raw_html = content_elem.text or ""
                disclosure = orig_p.get("affiliation_disclosure", "")
                if feed_locale == "zh":
                    disclosure = zh_pages_map.get(slug, {}).get("affiliation_disclosure", disclosure)
                report.check()
                if disclosure and html.escape(disclosure) not in raw_html:
                    report.error(f"{feed_file.name} entry '{slug}' missing affiliation disclosure")
                class _FeedContentInspector(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.hrefs = []
                        self.srcs = []
                        self.has_site_nav = False
                        self.has_follow_widget = False

                    def handle_starttag(self, tag, attrs):
                        attr_dict = dict(attrs)
                        if "href" in attr_dict:
                            self.hrefs.append(attr_dict["href"])
                        if "src" in attr_dict:
                            self.srcs.append(attr_dict["src"])
                        classes = attr_dict.get("class", "").split()
                        if "site-nav" in classes:
                            self.has_site_nav = True
                        if "follow-section" in classes or "follow-box" in classes:
                            self.has_follow_widget = True

                inspector = _FeedContentInspector()
                try:
                    inspector.feed(raw_html)
                except Exception as ex:
                    report.error(f"{feed_file.name} entry '{slug}' content HTML parse error: {ex}")

                # Ensure no navbar or follow widget injection
                if inspector.has_site_nav:
                    report.error(f"{feed_file.name} entry '{slug}' injected site-nav into content")
                if inspector.has_follow_widget:
                    report.error(f"{feed_file.name} entry '{slug}' injected follow widget into content")

                # URL resolution check: all href and src must be absolute
                for h in inspector.hrefs:
                    if not h.startswith(("http://", "https://", "mailto:", "tel:")):
                        report.error(f"{feed_file.name} entry '{slug}' contains non-absolute href: '{h}'")

                for s in inspector.srcs:
                    if not s.startswith(("http://", "https://")):
                        report.error(f"{feed_file.name} entry '{slug}' contains non-absolute src: '{s}'")

                # Full-body content verification: substantive body text check
                bf_basename = Path(orig_p["body_file"]).name
                body_path = (resolved_content_dir / "zh" / "bodies" / bf_basename) if feed_locale == "zh" else (resolved_content_dir / orig_p["body_file"])
                if body_path.is_file():
                    headings = re.findall(r'<h[2-4][^>]*>(.*?)</h[2-4]>', body_path.read_text(encoding="utf-8"))
                    if headings:
                        first_h = re.sub(r'<[^>]+>', '', headings[0]).strip()
                        if first_h and first_h not in raw_html:
                            report.error(f"{feed_file.name} entry '{slug}' missing substantive body heading '{first_h}'")

                # Editorial media & credits check
                assigned_media = article_media_keys.get(slug)
                if assigned_media:
                    if "<figure" not in raw_html or "media-article" not in raw_html:
                        report.error(f"{feed_file.name} entry '{slug}' missing lead editorial figure")
                    if "media-credit" not in raw_html:
                        report.error(f"{feed_file.name} entry '{slug}' missing lead figure media credit")
                    if feed_locale == "zh" and assigned_media in zh_media_map:
                        zh_caption = zh_media_map[assigned_media].get("caption", "")
                        if zh_caption and zh_caption not in raw_html:
                            report.error(f"{feed_file.name} entry '{slug}' missing translated Chinese media caption")
                else:
                    if "<figure" in raw_html and "media-article" in raw_html:
                        report.error(f"{feed_file.name} entry '{slug}' unexpectedly has editorial figure")

                # Read more permalink check
                read_more = "在 Audit Commons 阅读全文" if feed_locale == "zh" else "Read complete article at Audit Commons"
                if read_more not in raw_html or entry_url not in raw_html:
                    report.error(f"{feed_file.name} entry '{slug}' missing read more permalink")

        except Exception as e:
            report.error(f"Failed to validate {feed_file.name}: {e}")

    _validate_feed(output_dir / "feed.xml", "en")
    if (output_dir / "zh" / "feed.xml").exists():
        _validate_feed(output_dir / "zh" / "feed.xml", "zh")

    # Parse and index all HTML files
    html_files = list(output_dir.rglob("*.html"))
    page_data: Dict[str, HtmlStructureExtractor] = {}

    for html_path in html_files:
        report.check()
        rel_path = html_path.relative_to(output_dir).as_posix()
        content = html_path.read_text(encoding="utf-8")

        # Invariant: No "Verified audit" string anywhere in generated HTML
        if "Verified audit" in content:
            report.error(f"{rel_path}: Found prohibited phrase 'Verified audit'")

        extractor = HtmlStructureExtractor()
        try:
            extractor.feed(content)
        except Exception as e:
            report.error(f"HTML parse error in {rel_path}: {e}")
        page_data[rel_path] = extractor

    # Validate semantic contract and DOM invariants on each HTML page
    expected_sitemap = {
        expected_base_url.rstrip('/') + ('/' if name == 'index.html' else '/' + name.removesuffix('index.html'))
        for name in page_data if not name.endswith('404.html')
    }
    report.check()
    if sitemap_urls != expected_sitemap:
        report.error(f"Sitemap does not match generated routes: missing={expected_sitemap - sitemap_urls}, extra={sitemap_urls - expected_sitemap}")
    for rel_path, ext in page_data.items():
        report.check()
        if ext.h1_count != 1:
            report.error(f"{rel_path}: Expected exactly one h1, found {ext.h1_count}")
        if not ext.has_site_header:
            report.error(f"{rel_path}: Missing <header class='site-header'>")
        if not ext.has_site_nav:
            report.error(f"{rel_path}: Missing <nav class='site-nav'>")
        if not ext.has_main:
            report.error(f"{rel_path}: Missing <main id='main'>")
        if ext.main_tabindex != "-1":
            report.error(f"{rel_path}: <main id='main'> must have tabindex='-1' for skip link accessibility focus")
        if not ext.has_site_footer:
            report.error(f"{rel_path}: Missing <footer class='site-footer'>")
        if not ext.has_skip_link:
            report.error(f"{rel_path}: Missing skip link <a class='skip-link' href='#main'>")
        if not ext.brand_uses_mark_svg:
            report.error(f"{rel_path}: .brand must use /assets/mark.svg")

        # Check required metadata
        meta_names = {m.get("name"): m.get("content") for m in ext.meta_tags if "name" in m}
        meta_props = {m.get("property"): m.get("content") for m in ext.meta_tags if "property" in m}

        if not meta_names.get("description"):
            report.error(f"{rel_path}: Missing <meta name='description'>")
        if not meta_props.get("og:title"):
            report.error(f"{rel_path}: Missing <meta property='og:title'>")
        if not meta_props.get("og:url"):
            report.error(f"{rel_path}: Missing <meta property='og:url'>")
        if not meta_names.get("twitter:card"):
            report.error(f"{rel_path}: Missing <meta name='twitter:card'>")

        # Check Structured Data JSON-LD
        for s in ext.json_ld_scripts:
            # Check script breakout safety: raw < or > inside JSON string should not appear unescaped
            if "<" in s or ">" in s:
                report.error(f"{rel_path}: JSON-LD structured data contains unescaped < or > characters")
            try:
                json.loads(s)
            except Exception as e:
                report.error(f"{rel_path}: Malformed JSON-LD structured data: {e}")

        if rel_path == "index.html":
            has_website = False
            for s in ext.json_ld_scripts:
                try:
                    data = json.loads(s)
                    if data.get("@type") == "WebSite":
                        has_website = True
                except Exception:
                    pass
            if not has_website:
                report.error("index.html must include JSON-LD WebSite structured data")

        if "guides/" in rel_path or "updates/" in rel_path or "news/" in rel_path or "features/" in rel_path:
            if rel_path not in (
                "guides/index.html", "updates/index.html", "features/index.html",
                "zh/guides/index.html", "zh/updates/index.html", "zh/features/index.html",
            ):
                has_article = False
                for s in ext.json_ld_scripts:
                    try:
                        data = json.loads(s)
                        if data.get("@type") in ("Article", "NewsArticle"):
                            has_article = True
                    except Exception:
                        pass
                if not has_article:
                    report.error(f"{rel_path}: Practical guides and releases must include JSON-LD Article structured data")

        # Check resource page DOM contract
        if rel_path in ("resources/index.html", "zh/resources/index.html"):
            if not ext.has_resource_controls or not ext.resource_controls_hidden:
                report.error(f"{rel_path}: #resource-controls must exist and have 'hidden' attribute initially")
            if not ext.has_resource_search:
                report.error(f"{rel_path}: input#resource-search[type='search'] must exist")
            if not ext.has_resource_count or not ext.resource_count_role_status:
                report.error(f"{rel_path}: #resource-count with role='status' must exist")
            if not ext.has_no_results or not ext.no_results_hidden:
                report.error(f"{rel_path}: #no-results empty state must exist and be hidden initially")
            if not ext.resource_cards:
                report.error(f"{rel_path}: must contain .resource-card elements")
            for card in ext.resource_cards:
                report.check()
                if not card.get("data-category"):
                    report.error("resources/index.html: .resource-card missing required data-category attribute")
                if not card.get("data-search"):
                    report.error("resources/index.html: .resource-card missing required data-search attribute")
                if not card.get("data-format"):
                    report.error("resources/index.html: .resource-card missing required data-format attribute")

            # Check format tabs and tabpanel ARIA contract
            report.check()
            if not ext.has_tablist:
                report.error("resources/index.html: missing [role='tablist'] container")
            if not ext.tablist_aria_label:
                report.error("resources/index.html: [role='tablist'] missing aria-label attribute")
            if not ext.format_tabs:
                report.error("resources/index.html: missing [role='tab'] buttons")

            has_tab_all = False
            for tab in ext.format_tabs:
                report.check()
                tab_id = tab.get("id")
                if not tab_id:
                    report.error("resources/index.html: [role='tab'] missing id attribute")
                if tab.get("aria-controls") != "resources-panel":
                    report.error(f"resources/index.html: tab '{tab_id}' aria-controls must be 'resources-panel'")
                if tab_id == "tab-all":
                    has_tab_all = True
                    if tab.get("aria-selected") != "true":
                        report.error("resources/index.html: tab-all must have aria-selected='true' initially")
                    if tab.get("tabindex") != "0":
                        report.error("resources/index.html: tab-all must have tabindex='0' initially")
                else:
                    if tab.get("aria-selected") != "false":
                        report.error(f"resources/index.html: tab '{tab_id}' must have aria-selected='false' initially")
                    if tab.get("tabindex") != "-1":
                        report.error(f"resources/index.html: tab '{tab_id}' must have tabindex='-1' initially")

            if not has_tab_all:
                report.error("resources/index.html: missing required 'tab-all' tab")

            report.check()
            if len(ext.tabpanels) != 1:
                report.error(f"resources/index.html: expected exactly 1 visible tabpanel, found {len(ext.tabpanels)}")
            else:
                panel = ext.tabpanels[0]
                if panel.get("id") != "resources-panel":
                    report.error("resources/index.html: tabpanel must have id='resources-panel'")
                if panel.get("aria-labelledby") != "tab-all":
                    report.error("resources/index.html: tabpanel aria-labelledby must initially reference 'tab-all'")
                if panel.get("tabindex") != "0":
                    report.error("resources/index.html: tabpanel must have tabindex='0' for keyboard navigation")

    # Validate all internal links, fragment targets, and referenced local assets
    for src_path, ext in page_data.items():
        for href, line_no in ext.links:
            report.check()
            if not href or href.startswith(("mailto:", "javascript:", "tel:")):
                continue

            parsed = urlparse(href)
            if parsed.scheme in ("http", "https"):
                continue

            if href.startswith("#"):
                fragment = href[1:]
                if fragment and fragment not in ext.element_ids:
                    report.error(f"{src_path}:{line_no}: In-page anchor '{href}' references missing id '{fragment}'")
                continue

            target_path_str = parsed.path
            fragment = parsed.fragment

            if target_path_str.startswith("/"):
                clean_target = target_path_str.lstrip("/")
            else:
                curr_dir = Path(src_path).parent
                clean_target = (curr_dir / target_path_str).as_posix()

            if not clean_target or clean_target == "":
                dest_file = "index.html"
            elif clean_target.endswith("/"):
                dest_file = f"{clean_target}index.html"
            elif "." not in Path(clean_target).name:
                dest_file = f"{clean_target}/index.html"
            else:
                dest_file = clean_target

            if dest_file not in page_data and not (output_dir / dest_file).exists():
                if not (output_dir / clean_target).exists():
                    report.error(f"{src_path}:{line_no}: Broken internal link '{href}' (resolved to {dest_file})")
                    continue

            if fragment and dest_file in page_data:
                target_ext = page_data[dest_file]
                if fragment not in target_ext.element_ids:
                    report.error(f"{src_path}:{line_no}: Fragment anchor '#{fragment}' not found in target '{dest_file}'")

        for tag, src, line_no in ext.asset_sources:
            report.check()
            if not src or src.startswith(("data:", "http://", "https://", "//")):
                continue
            clean_src = urlparse(src).path.lstrip("/")
            asset_target = output_dir / clean_src
            if clean_src == "assets/social-preview.png":
                if not asset_target.exists():
                    report.error(f"{src_path}:{line_no}: OG social preview PNG '{src}' not found")
                continue
            if not asset_target.exists():
                report.error(f"{src_path}:{line_no}: Asset source not found: '{src}' ({asset_target})")


def run_output_safety_tests(repo_root: Path, content_dir: Path, assets_dir: Path, report: ValidationReport) -> None:
    """
    Executes automated tests verifying that the static site generator's output directory
    clean and deny logic completely protects source dirs, git dirs, and unrelated files.
    """
    from build import build_site

    print("Running output directory safety and refuse tests...")

    # Test 1: Targeting protected content_dir must be rejected and content must survive intact
    report.check()
    site_json_pre = (content_dir / "site.json").read_bytes() if (content_dir / "site.json").exists() else b""
    try:
        build_site(repo_root=repo_root, content_dir=content_dir, output_dir=content_dir, assets_dir=assets_dir)
        report.error("Safety FAIL: build_site did not reject targeting protected content directory")
    except RuntimeError:
        pass
    except Exception as e:
        report.error(f"Safety FAIL: unexpected exception when targeting content directory: {e}")

    site_json_post = (content_dir / "site.json").read_bytes() if (content_dir / "site.json").exists() else b""
    if site_json_pre != site_json_post:
        report.error("Safety CRITICAL: content/site.json was modified or deleted during rejected build!")

    # Test 2: Targeting .git must be rejected and .git must survive intact
    report.check()
    git_dir = repo_root / ".git"
    if git_dir.exists():
        try:
            build_site(repo_root=repo_root, content_dir=content_dir, output_dir=git_dir, assets_dir=assets_dir)
            report.error("Safety FAIL: build_site did not reject targeting protected .git directory")
        except RuntimeError:
            pass
        except Exception as e:
            report.error(f"Safety FAIL: unexpected exception when targeting .git directory: {e}")

    # Test 3: Targeting repo root must be rejected
    report.check()
    try:
        build_site(repo_root=repo_root, content_dir=content_dir, output_dir=repo_root, assets_dir=assets_dir)
        report.error("Safety FAIL: build_site did not reject targeting repository root")
    except RuntimeError:
        pass
    except Exception as e:
        report.error(f"Safety FAIL: unexpected exception when targeting repository root: {e}")

    # Test 4: Unmarked non-empty directory with unrelated sentinel file must be rejected and survive
    report.check()
    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_path = Path(tmp_dir) / "unrelated_dir"
        temp_path.mkdir()
        sentinel = temp_path / "sentinel.txt"
        sentinel.write_text("Unrelated user file that must not be deleted", encoding="utf-8")

        try:
            build_site(repo_root=repo_root, content_dir=content_dir, output_dir=temp_path, assets_dir=assets_dir)
            report.error("Safety FAIL: build_site did not reject non-empty unmarked directory")
        except RuntimeError:
            pass
        except Exception as e:
            report.error(f"Safety FAIL: unexpected exception when targeting non-empty unmarked directory: {e}")

        if not sentinel.exists() or sentinel.read_text(encoding="utf-8") != "Unrelated user file that must not be deleted":
            report.error("Safety CRITICAL: Sentinel file was deleted or corrupted in rejected directory!")

    # Test 5 & 6: Fresh build writes marker, second build removes stale generated files
    report.check()
    with tempfile.TemporaryDirectory() as tmp_dir:
        qa_out = Path(tmp_dir) / "test_out"
        # 5a. Fresh build into non-existent directory succeeds
        build_site(repo_root=repo_root, content_dir=content_dir, output_dir=qa_out, assets_dir=assets_dir)
        if not (qa_out / ".generator-owned").exists():
            report.error("Safety FAIL: Fresh build did not write .generator-owned marker")
        if not (qa_out / "index.html").exists():
            report.error("Safety FAIL: Fresh build did not emit index.html")

        # 5b. Inject stale generated file
        stale_file = qa_out / "stale_leak_test.html"
        stale_file.write_text("Stale content from previous build", encoding="utf-8")

        # 6. Second valid build cleans stale content and succeeds
        build_site(repo_root=repo_root, content_dir=content_dir, output_dir=qa_out, assets_dir=assets_dir)
        if stale_file.exists():
            report.error("Safety FAIL: Second build did not remove stale generated file 'stale_leak_test.html'")
        if not (qa_out / "index.html").exists():
            report.error("Safety FAIL: Second build failed to regenerate valid index.html")


def run_resources_contract_tests(repo_root: Path, content_dir: Path, assets_dir: Path, report: ValidationReport) -> None:
    """
    Validates:
    1. Missing optional fields in legacy data fall back cleanly to sensible defaults (Collection, infer no claims).
    2. Uses a temporary fixture simulating all 6 formats with 100 rows, runs full build and validation,
       then removes fixture.
    """
    from build import build_site

    print("Running resources data contract & 100-row all-formats fixture tests...")

    from import_awesome import parse_awesome_markdown, clean_markdown_text
    artifact_fixture = (
        "## Tools and Platforms\n"
        r"**\[Tool\] Example** ([org/example](https://github.com/org/example)): "
        r"Example summary. [\[Paper\]](https://arxiv.org/abs/2310.10501) (EMNLP 2023 Demo)"
    )
    parsed_artifacts = parse_awesome_markdown(artifact_fixture)
    report.check()
    if (len(parsed_artifacts) != 1
            or parsed_artifacts[0]["summary"] != "Example summary."
            or parsed_artifacts[0]["venue"] != "EMNLP 2023 Demo"
            or parsed_artifacts[0]["links"] != [
                {"label": "Paper", "url": "https://arxiv.org/abs/2310.10501"}
            ]):
        report.error("Importer lost an escaped-bracket paper link or its venue")
    report.check()
    if clean_markdown_text(r"See [\[Paper\]](https://example.org/paper)") != "See Paper":
        report.error("Importer left nested-bracket Markdown in plain text")

    # Render legacy records without the optional catalog fields.
    report.check()
    res_file = content_dir / "resources.json"
    if res_file.exists():
        try:
            from build import build_resources_page
            legacy_data = json.loads(res_file.read_text(encoding="utf-8"))[:6]
            for item in legacy_data:
                for field in ("format", "formats", "source_section", "venue", "links", "catalog_source"):
                    item.pop(field, None)
            site_data = json.loads((content_dir / "site.json").read_text(encoding="utf-8"))
            extractor = HtmlStructureExtractor()
            extractor.feed(build_resources_page(site_data, legacy_data, "https://auditcommons.org"))
            if len(extractor.resource_cards) != len(legacy_data):
                report.error("Legacy resources did not all render")
            if any(card.get("data-format") != "Collection" for card in extractor.resource_cards):
                report.error("Legacy resources without a format must render as Collection")
        except Exception as e:
            report.error(f"Failed to verify legacy resources data: {e}")

    # 2. Temporary fixture: simulate all formats with 100 rows
    formats_cycle = ["Paper", "Tool", "Benchmark", "Dataset", "Standard", "Collection"]
    categories_cycle = ["Evaluation", "Security", "Governance", "Reading", "Tools"]

    fixture_resources = []
    for i in range(1, 101):
        fmt = formats_cycle[(i - 1) % len(formats_cycle)]
        cat = categories_cycle[(i - 1) % len(categories_cycle)]
        rel = "Maintainer project" if i % 10 == 0 else "External resource"
        sec = f"Topic Section {(i % 8) + 1}" if i % 2 == 0 else None
        venue = f"Conference 202{i % 6}" if fmt in ("Paper", "Benchmark") else None
        links = [{"label": "Code", "url": f"https://github.com/example/repo-{i}"}, {"label": "Data", "url": f"https://data.org/set-{i}"}] if i % 3 == 0 else []
        cat_src = f"https://github.com/yzhao062/awesome-auditable-ai/blob/main/README.md#sec-{i}" if i % 4 == 0 else None

        row: Dict[str, Any] = {
            "id": f"fixture-resource-{i:03d}",
            "name": f"Synthetic {fmt} Resource #{i}",
            "category": cat,
            "summary": f"A verified description of synthetic resource #{i} evaluating auditable behaviors.",
            "url": f"https://example.org/resources/{i}",
            "owner": f"Institution {(i % 5) + 1}",
            "relationship": rel,
            "source_urls": [f"https://example.org/resources/{i}/primary"],
            "checked": "2026-09-16",
            "format": fmt,
        }
        if sec:
            row["source_section"] = sec
        if venue:
            row["venue"] = venue
        if links:
            row["links"] = links
        if cat_src:
            row["catalog_source"] = cat_src

        fixture_resources.append(row)

    fixture_resources[0]["formats"] = ["Paper", "Dataset", "Benchmark"]
    for invalid in (["Unknown"], ["Paper", "Paper"], ["Dataset"], "Paper", []):
        report.check()
        if not formats_error({"format": "Paper", "formats": invalid}):
            report.error(f"Format validation accepted malformed memberships: {invalid!r}")

    from import_awesome import parse_awesome_markdown
    table_rows = parse_awesome_markdown(
        "## Datasets and Benchmarks\n"
        r"| [Example](https://arxiv.org/abs/2505.08638) | 2025 | Description. | "
        r"[\[Code\]](https://github.com/org/example) [\[Dataset\]](https://huggingface.co/datasets/org/example) |"
    )
    report.check()
    if len(table_rows) != 1 or table_rows[0]["links"] != [
        {"label": "Code", "url": "https://github.com/org/example"},
        {"label": "Dataset", "url": "https://huggingface.co/datasets/org/example"},
    ]:
        report.error("Importer dropped escaped artifact links in a table row")

    # Run fixture build in isolated temporary directory
    with tempfile.TemporaryDirectory() as fixture_tmp:
        fixture_content = Path(fixture_tmp) / "content"
        fixture_out = Path(fixture_tmp) / "_site"
        fixture_content.mkdir(parents=True)

        # Copy required metadata from original content dir
        shutil.copy2(content_dir / "site.json", fixture_content / "site.json")
        shutil.copy2(content_dir / "pages.json", fixture_content / "pages.json")
        shutil.copytree(content_dir / "bodies", fixture_content / "bodies")

        # Write the 100-row fixture
        (fixture_content / "resources.json").write_text(json.dumps(fixture_resources, indent=2), encoding="utf-8")

        # Validate source schema on fixture
        validate_sources(fixture_content, report)

        # Build site with fixture
        build_site(
            repo_root=repo_root,
            content_dir=fixture_content,
            output_dir=fixture_out,
            assets_dir=assets_dir,
            base_url_override="https://auditcommons.org",
        )

        # Validate output directory with fixture
        validate_output_directory(fixture_out, "https://auditcommons.org", report)

        # Inspect generated resources/index.html in fixture output
        res_html_path = fixture_out / "resources/index.html"
        report.check()
        if not res_html_path.exists():
            report.error("Fixture test: resources/index.html was not generated")
        else:
            text = res_html_path.read_text(encoding="utf-8")
            extractor = HtmlStructureExtractor()
            extractor.feed(text)

            # Check that all 100 cards exist
            report.check()
            if len(extractor.resource_cards) != 100:
                report.error(f"Fixture test: expected 100 .resource-card elements, found {len(extractor.resource_cards)}")

            report.check()
            if extractor.resource_cards[0].get("data-formats") != "Paper Dataset Benchmark":
                report.error("Multi-format fixture lost a secondary membership")
            fixture_html = (fixture_out / "resources/index.html").read_text(encoding="utf-8")
            report.check()
            if not re.search(r'id="tab-dataset"[^>]*>Datasets <span[^>]*>\(18\)', fixture_html):
                report.error("Dataset tab must count 17 primary datasets plus the cross-listed paper once")

            # Check that format tabs for all 6 formats were rendered
            report.check()
            tab_formats = {t.get("data-format") for t in extractor.format_tabs}
            expected_formats = {"all", "Paper", "Tool", "Benchmark", "Dataset", "Standard", "Collection"}
            if not expected_formats.issubset(tab_formats):
                report.error(f"Fixture test: missing format tabs in fixture output: {expected_formats - tab_formats}")

            # Check single visible tabpanel
            report.check()
            if len(extractor.tabpanels) != 1:
                report.error(f"Fixture test: expected 1 tabpanel, found {len(extractor.tabpanels)}")

    # Fixture is automatically removed upon exiting context manager
    print("100-row fixture test complete and temporary fixture cleaned up.")


def run_feed_contract_tests(
    repo_root: Path,
    content_dir: Path,
    assets_dir: Path,
    base_url: str,
    report: ValidationReport,
) -> None:
    """Rigorous regression tests for full-content bilingual Atom feeds."""
    print("Running full-content bilingual Atom feed regression tests...")
    from build import AbsolutizeHTMLParser, build_atom_feed

    # 1. URL resolution including query escaping, mailto, and fragment anchors
    test_base = "https://feed-test.auditcommons.org/news/sample-slug/"
    test_snippet = """
    <p>Introduction paragraph with &amp; entity.</p>
    <a href="/guides/sample?topic=eval&amp;mode=strict#step-1">Relative with query and fragment</a>
    <a href="#in-page-anchor">In-page anchor</a>
    <a href="mailto:editor@example.com?subject=Inquiry%20Regarding%20Audit">Email link</a>
    <img src="/assets/media/test.png" alt="Test &amp; Check">
    """
    parser = AbsolutizeHTMLParser(test_base)
    parser.feed(test_snippet)
    resolved = parser.get_html()
    report.check()
    if 'href="https://feed-test.auditcommons.org/guides/sample?topic=eval&amp;mode=strict#step-1"' not in resolved:
        report.error("Feed URL resolution failed for query and fragment on root-relative link")
    report.check()
    if 'href="https://feed-test.auditcommons.org/news/sample-slug/#in-page-anchor"' not in resolved:
        report.error("Feed URL resolution failed for in-page fragment anchor")
    report.check()
    if 'href="mailto:editor@example.com?subject=Inquiry%20Regarding%20Audit"' not in resolved:
        report.error("Feed URL resolution corrupted mailto link")
    report.check()
    if 'src="https://feed-test.auditcommons.org/assets/media/test.png"' not in resolved:
        report.error("Feed URL resolution failed for image src")

    # 2. XML safety round-trip
    wrapped_xml = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><content type="html">{html.escape(resolved)}</content></entry></feed>'
    try:
        xml_root = ET.fromstring(wrapped_xml)
        content_elem = xml_root.find("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}content")
        report.check()
        if content_elem is None or content_elem.text != resolved:
            report.error("Feed content failed XML round-trip equality")
    except Exception as ex:
        report.error(f"Feed XML safety test failed to parse XML: {ex}")

    # 3. Custom base URL & feed page generation
    synthetic_page = {
        "slug": "news/test-item",
        "title": "Test Title &amp; Analysis",
        "summary": "Summary of test item",
        "author": "Audit Commons",
        "published": "2026-09-17",
        "updated": "2026-09-17",
        "kind": "news",
        "source_urls": ["https://example.com/source?a=1&b=2"],
        "_body_html": '<section><h2>Test Heading</h2><p>Body with <a href="#details">fragment link</a>.</p></section>',
    }
    custom_feed_xml = build_atom_feed({"name": "Test Site"}, [synthetic_page], "https://custom.example.org", locale="en")
    report.check()
    try:
        custom_root = ET.fromstring(custom_feed_xml)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = custom_root.find("a:entry", ns)
        if entry is None:
            report.error("Synthetic feed failed to generate entry")
        else:
            if entry.findtext("a:id", namespaces=ns) != "https://custom.example.org/news/test-item/":
                report.error("Synthetic feed entry id mismatch")
            if entry.findtext("a:published", namespaces=ns) != "2026-09-17T00:00:00Z":
                report.error("Synthetic feed entry published date mismatch")
            content_text = entry.findtext("a:content", namespaces=ns) or ""
            if "https://custom.example.org/news/test-item/#details" not in content_text:
                report.error("Synthetic feed failed to absolutize fragment anchor against canonical URL")
            if "Test Heading" not in content_text:
                report.error("Synthetic feed failed to include substantive body HTML")
            if "https://custom.example.org/news/test-item/" not in content_text:
                report.error("Synthetic feed failed to include canonical permalink")
    except Exception as ex:
        report.error(f"Synthetic feed XML parse failed: {ex}")

    print("Atom feed regression tests completed successfully.")


def validate_search_metadata(output_dir: Path, content_dir: Path, base_url: str, report: ValidationReport) -> None:
    """Catch indexing regressions and disagreement between editorial and search metadata."""
    base_url = base_url.rstrip("/")
    robots = RobotFileParser()
    robots_path = output_dir / "robots.txt"
    if not robots_path.exists():
        report.error("Search checks require robots.txt")
        return
    robots.parse(robots_path.read_text(encoding="utf-8").splitlines())
    report.check()
    if base_url + "/sitemap.xml" not in (robots.site_maps() or []):
        report.error("robots.txt must advertise the canonical sitemap")

    titles: Dict[str, str] = {}
    descriptions: Dict[str, str] = {}
    for path in output_dir.rglob("*.html"):
        rel = path.relative_to(output_dir).as_posix()
        route = "/" if rel == "index.html" else "/" + rel.removesuffix("index.html")
        ext = HtmlStructureExtractor()
        ext.feed(path.read_text(encoding="utf-8"))
        meta = {m.get("name"): m.get("content", "") for m in ext.meta_tags}
        report.check()
        if ext.canonicals != [base_url + route]:
            report.error(f"{rel}: Expected one self-referencing canonical URL")
        for label, value, seen in (("title", ext.title.strip(), titles), ("description", meta.get("description", "").strip(), descriptions)):
            report.check()
            if not value or value in seen:
                report.error(f"{rel}: Missing or duplicate {label}; previous={seen.get(value)}")
            seen[value] = rel
        report.check()
        directives = {s.strip() for s in meta.get("robots", "").lower().split(",")}
        if rel.endswith("404.html"):
            if "noindex" not in directives:
                report.error(f"{rel}: Must remain noindex")
            continue
        if {"noindex", "nofollow", "none", "nosnippet"} & directives:
            report.error(f"{rel}: Search discovery or snippets are blocked")
        for bot in ("Googlebot", "Bingbot", "OAI-SearchBot"):
            report.check()
            if not robots.can_fetch(bot, base_url + route):
                report.error(f"{rel}: robots.txt blocks {bot}")

    registry = content_dir / "pages.json"
    if not registry.exists():
        return
    pages = json.loads(registry.read_text(encoding="utf-8"))
    for page in pages:
        if any(not page.get(key) for key in ("slug", "kind", "title", "summary", "published", "author")):
            report.error(f"Search metadata requires a complete article record: {page.get('slug', 'unknown')}")
            continue
        path = output_dir / page["slug"] / "index.html"
        if not path.exists():
            continue  # The output-route check reports missing files.
        text = path.read_text(encoding="utf-8")
        ext = HtmlStructureExtractor()
        ext.feed(text)
        try:
            data = [json.loads(s) for s in ext.json_ld_scripts]
        except ValueError:
            continue  # The JSON-LD parser check reports malformed scripts.
        url = base_url + "/" + page["slug"] + "/"
        breadcrumbs = [d for d in data if d.get("@type") == "BreadcrumbList"]
        report.check()
        if len(breadcrumbs) != 1:
            report.error(f"{page['slug']}: Expected one BreadcrumbList")
        else:
            trail = breadcrumbs[0].get("itemListElement", [])
            nav = re.search(r'<nav class="breadcrumbs"[^>]*>(.*?)</nav>', text, re.S)
            if len(trail) < 2 or trail[-1].get("item") != url or not nav:
                report.error(f"{page['slug']}: Breadcrumb trail must be visible and end at the canonical page")
            for i, item in enumerate(trail, 1):
                report.check()
                if item.get("position") != i or not item.get("name"):
                    report.error(f"{page['slug']}: Invalid breadcrumb position or label")
                if nav and html.escape(item.get("name", ""), quote=True) not in nav.group(1):
                    report.error(f"{page['slug']}: Breadcrumb schema label is absent from visible trail")
                if i < len(trail) and nav and f'href="{urlparse(item.get("item", "")).path}"' not in nav.group(1):
                    report.error(f"{page['slug']}: Breadcrumb must link locally to its parent")
        if page["kind"] == "about":
            continue
        articles = [d for d in data if d.get("@type") in {"Article", "NewsArticle"}]
        report.check()
        if len(articles) != 1:
            report.error(f"{page['slug']}: Expected one article schema")
            continue
        article = articles[0]
        expected = {
            "@type": "NewsArticle" if page["kind"] == "news" else "Article",
            "url": url, "mainEntityOfPage": url, "headline": page["title"],
            "description": page["summary"], "datePublished": page["published"],
            "dateModified": page.get("updated") or page["published"],
            "citation": page.get("source_urls", []),
        }
        for key, value in expected.items():
            report.check()
            if article.get(key) != value:
                report.error(f"{page['slug']}: Article {key} disagrees with editorial record")
        for role in ("author", "publisher"):
            report.check()
            identity = article.get(role, {})
            if identity.get("name") != page["author"] or identity.get("url") != base_url + "/about/":
                report.error(f"{page['slug']}: {role} must identify the visible editorial byline")
        for related in page.get("related_slugs", []):
            report.check()
            if f"/{related}/" not in {href for href, _ in ext.links}:
                report.error(f"{page['slug']}: Related reading link missing for {related}")


def validate_editorial_media(output_dir, content_dir, report):
    manifest_file = content_dir / 'media.json'
    if not manifest_file.exists():
        return
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    from hashlib import sha256
    for key, media in manifest['assets'].items():
        report.check()
        file = output_dir / media['src'].lstrip('/')
        if not file.is_file() or sha256(file.read_bytes()).hexdigest() != media['sha256']:
            report.error(f'Media {key}: published image missing or differs from source digest')
        if 'license_file' in media:
            report.check()
            if not (output_dir / media['license_file'].lstrip('/')).is_file():
                report.error(f'Media {key}: published license notice missing')
    for file in output_dir.rglob('*.html'):
        ext = HtmlStructureExtractor()
        ext.feed(file.read_text(encoding='utf-8'))
        for img in ext.images:
            if not img.get('src', '').startswith('/assets/media/'):
                continue
            report.check()
            if not img.get('alt') or not all(img.get(k, '').isdigit() and int(img[k]) > 0 for k in ('width', 'height')):
                report.error(f'{file}: editorial image needs descriptive alt and intrinsic dimensions')
    for slug, key in manifest['articles'].items():
        media = manifest['assets'][key]
        ext = HtmlStructureExtractor()
        ext.feed((output_dir / slug / 'index.html').read_text(encoding='utf-8'))
        links = {url for url, _ in ext.links}
        report.check()
        if media['source_url'] not in links or media['license_url'] not in links:
            report.error(f'{slug}: image attribution missing')
        report.check()
        if media['src'] not in {img.get('src') for img in ext.images}:
            report.error(f'{slug}: assigned editorial image missing')
        report.check()
        og = next((m for m in ext.meta_tags if m.get('property') == 'og:image'), {})
        expected_image = media['src'] if social_image_eligible(media) else '/assets/social-preview.png'
        if urlparse(og.get('content', '')).path != expected_image:
            report.error(f'{slug}: unexpected article social preview')


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Commons output & content verification suite")
    parser.add_argument("--content-dir", default="content", help="Path to source content directory")
    parser.add_argument("--output-dir", default="_site", help="Path to built static site directory")
    parser.add_argument("--assets-dir", default="assets", help="Path to assets directory")
    parser.add_argument("--base-url", default=None, help="Expected base URL (defaults to site.json or https://auditcommons.org)")
    parser.add_argument("--skip-source", action="store_true", help="Skip source content schema validation")
    parser.add_argument("--skip-safety", action="store_true", help="Skip generator output safety tests")

    args = parser.parse_args()
    repo_root = Path.cwd().resolve()
    content_dir = (repo_root / args.content_dir).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    assets_dir = (repo_root / args.assets_dir).resolve()

    report = ValidationReport()

    # Determine base URL to verify against
    base_url = args.base_url
    if not base_url and (content_dir / "site.json").exists():
        try:
            with open(content_dir / "site.json", "r", encoding="utf-8") as f:
                base_url = json.load(f).get("base_url")
        except Exception:
            pass
    if not base_url:
        base_url = "https://auditcommons.org"

    print("=== Audit Commons Verification Suite ===")
    print(f"Content directory: {content_dir}")
    print(f"Output directory:  {output_dir}")
    print(f"Base URL:          {base_url}")
    print()

    # 1. Output safety tests
    if not args.skip_safety and content_dir.exists() and assets_dir.exists():
        run_output_safety_tests(repo_root, content_dir, assets_dir, report)
        run_resources_contract_tests(repo_root, content_dir, assets_dir, report)
        run_feed_contract_tests(repo_root, content_dir, assets_dir, base_url, report)

    # 2. Source content checks
    if not args.skip_source:
        if content_dir.exists():
            print("Checking source content schemas, dates, and contracts...")
            validate_sources(content_dir, report)
        else:
            report.warn(f"Source directory '{content_dir}' does not exist; skipping source validation.")

    # 3. Output directory checks
    print("Checking output files, links, fragments, accessibility, and sitemap...")
    validate_output_directory(output_dir, base_url, report, content_dir=content_dir)
    validate_search_metadata(output_dir, content_dir, base_url, report)
    validate_editorial_media(output_dir, content_dir, report)

    # Print summary
    print()
    print(f"Checks completed: {report.checks_run}")
    if report.warnings:
        print(f"Warnings ({len(report.warnings)}):")
        for w in report.warnings:
            print(f"  [WARN] {w}")

    if report.errors:
        print(f"Errors ({len(report.errors)}):")
        for e in report.errors:
            print(f"  [FAIL] {e}")
        print("\nVerification FAILED.")
        return 1

    print("Verification PASSED with zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
