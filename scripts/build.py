#!/usr/bin/env python3
"""
Audit Commons Static Site Generator
Builds the complete Audit Commons field portal using standard Python 3.12 library only.
Generates the field portal from its editorial content and static assets.
Supports both English and Simplified Chinese (/zh/) editions via translation overlays.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

from resource_formats import resource_formats
from editorial_media import bind_media, media_credit, render_media, social_image_eligible
from reading_lists import (
    load_reading_lists,
    render_reading_lists_html,
    render_learn_selections_bridge,
)
from localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    LOCALE_LANG,
    LOCALE_OG,
    REQUIRED_NAV_ITEMS_ZH,
    FORMAT_DISPLAY_LABELS_ZH,
    CATEGORY_DISPLAY_LABELS_ZH,
    SECTION_DISPLAY_LABELS_ZH,
    KIND_LABELS_ZH,
    canonical_for,
    route_href,
    get_hreflang_tags,
    render_language_switcher,
    localize_body_html,
    display_date,
    normalize_slug,
    validate_translation_overlays,
    apply_page_overlay,
    apply_resource_overlay,
    apply_media_overlay,
)


DEFAULT_BASE_URL = "https://auditcommons.org"
MARKER_FILENAME = ".generator-owned"
MARKER_SIGNATURE = "Audit Commons Static Site Generator Ownership Marker\nversion=1\n"

REQUIRED_NAV_ITEMS = [
    ("Latest", "/latest/"),
    ("Learn", "/learn/"),
    ("Resources", "/resources/"),
    ("About", "/about/"),
]

NAV_SLUG_PREFIXES: dict[str, list[str]] = {
    "latest":    ["latest", "news/", "news", "updates/", "updates", "features/", "features"],
    "learn":     ["learn", "guides/", "start-here"],
    "resources": ["resources"],
    "about":     ["about"],
}

CURATED_HOME_RESOURCE_IDS = [
    "nist-ai-rmf",
    "inspect-aisi",
    "agentdojo",
    "awesome-auditable-ai",
    "catchbench",
    "auditable-agents",
]

VALID_RESOURCE_FORMATS = [
    "Paper",
    "Tool",
    "Benchmark",
    "Dataset",
    "Standard",
    "Collection",
]

FORMAT_DISPLAY_LABELS = {
    "Paper": "Papers",
    "Tool": "Tools",
    "Benchmark": "Benchmarks",
    "Dataset": "Datasets",
    "Standard": "Standards",
    "Collection": "Collections",
}


def escape(val: Any) -> str:
    """Safely escape text for HTML attributes or body content."""
    if val is None:
        return ""
    return html.escape(str(val), quote=True)


def parse_date(date_str: str) -> datetime:
    """Validate and parse a YYYY-MM-DD date."""
    if not isinstance(date_str, str):
        raise ValueError(f"Date must be a string, got {type(date_str).__name__}")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError(f"Invalid date format '{date_str}'; expected YYYY-MM-DD")
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid calendar date '{date_str}': {e}") from e


def publication_identity(site_data: Dict[str, Any], base_url: str, locale: str = "en") -> Dict[str, Any]:
    return {
        "@type": "Organization",
        "@id": canonical_for(base_url, "about", locale) + "#publication",
        "name": site_data.get("name", "Audit Commons"),
        "url": canonical_for(base_url, "about", locale),
    }


def validate_base_url(url_str: Optional[str]) -> str:
    """
    Validates that base_url is an origin only (https or local http).
    Rejects user credentials, query strings, fragments, and subpaths (other than '/').
    """
    if not url_str:
        return DEFAULT_BASE_URL
    parsed = urlparse(url_str.strip())
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"Base URL scheme must be 'https' or 'http', got '{parsed.scheme}' in '{url_str}'")
    if not parsed.netloc:
        raise ValueError(f"Base URL missing valid host/origin: '{url_str}'")
    if parsed.username or parsed.password:
        raise ValueError(f"Base URL must not include user credentials/userinfo: '{url_str}'")
    if parsed.query:
        raise ValueError(f"Base URL must not include query string: '{url_str}'")
    if parsed.fragment:
        raise ValueError(f"Base URL must not include fragment: '{url_str}'")
    if parsed.path and parsed.path != "/":
        raise ValueError(
            f"Base URL supports origin only (e.g. 'https://auditcommons.org' or 'http://localhost:8000'). "
            f"Subpath '{parsed.path}' is rejected because root-relative route links require an origin root."
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def serialize_json_ld(data: Dict[str, Any]) -> str:
    """
    Serializes structured data to JSON, escaping <, >, & to prevent HTML/script tag breakouts.
    """
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def clean_directory_contents_safely(target_dir: Path) -> None:
    """
    Recursively removes contents of a directory without traversing or deleting symlink targets.
    """
    for child in target_dir.iterdir():
        if child.is_symlink() or child.is_junction():
            raise RuntimeError(f"Refusing linked build entry: {child}")
        elif child.is_dir():
            clean_directory_contents_safely(child)
            child.rmdir()
        else:
            child.unlink()


def prepare_output_directory(
    output_dir: Path,
    repo_root: Path,
    content_dir: Path,
    assets_dir: Path,
) -> None:
    """
    Safely validates and prepares the output directory.
    - Rejects symlink/junction output directories.
    - Denies filesystem root, repository root, and repository root ancestors.
    - Denies protected source directories (content, assets, scripts, .git, .github) and their contents.
    - Allows fresh non-existent directories or empty directories.
    - Only cleans existing non-empty directories if they contain the exact valid .generator-owned marker.
    - Unlinks symlinks without deleting targets.
    """
    for component in (output_dir, *output_dir.parents):
        if component.is_symlink() or component.is_junction():
            raise RuntimeError(f"Output path contains a link or junction: {component}")

    resolved_out = output_dir.resolve()
    resolved_repo = repo_root.resolve()
    resolved_content = content_dir.resolve()
    resolved_assets = assets_dir.resolve()
    git_dir = (repo_root / ".git").resolve()
    github_dir = (repo_root / ".github").resolve()
    scripts_dir = (repo_root / "scripts").resolve()

    # 1. Deny filesystem root / drive root
    if resolved_out == Path(resolved_out.anchor):
        raise RuntimeError(f"Refusing to target filesystem root as output directory: {resolved_out}")

    # 2. Deny repo root and repo root ancestors
    if resolved_out == resolved_repo:
        raise RuntimeError(f"Refusing to target repository root as output directory: {resolved_out}")
    if resolved_out in resolved_repo.parents:
        raise RuntimeError(f"Refusing to target repository ancestor as output directory: {resolved_out}")

    # 3. Deny protected source and internal directories
    protected_dirs = [
        ("content", resolved_content),
        ("assets", resolved_assets),
        ("scripts", scripts_dir),
        (".git", git_dir),
        (".github", github_dir),
    ]
    for name, pdir in protected_dirs:
        if resolved_out == pdir or pdir in resolved_out.parents:
            raise RuntimeError(f"Refusing to target protected {name} directory or its contents: {output_dir}")
        if resolved_out in pdir.parents and resolved_out != resolved_repo:
            raise RuntimeError(f"Refusing to target ancestor of protected {name} directory: {output_dir}")

    # 4. Handle non-existent (fresh) directory
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=False)
        marker_path = output_dir / MARKER_FILENAME
        marker_path.write_text(MARKER_SIGNATURE, encoding="utf-8")
        return

    # 5. Handle existing path
    if not output_dir.is_dir():
        raise RuntimeError(f"Output path exists and is not a directory: {output_dir}")

    children = list(output_dir.iterdir())
    if len(children) == 0:
        # Fresh empty directory: safe to use
        marker_path = output_dir / MARKER_FILENAME
        marker_path.write_text(MARKER_SIGNATURE, encoding="utf-8")
        return

    # 6. Existing non-empty directory: MUST contain valid marker
    marker_path = output_dir / MARKER_FILENAME
    if not marker_path.exists() or not marker_path.is_file():
        raise RuntimeError(
            f"Refusing to clean non-empty unmarked directory: '{output_dir}'. "
            f"Output directory must be empty or contain a valid {MARKER_FILENAME} marker."
        )

    try:
        marker_content = marker_path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to read {MARKER_FILENAME} in '{output_dir}': {e}")

    if marker_content.strip() != MARKER_SIGNATURE.strip():
        raise RuntimeError(
            f"Invalid {MARKER_FILENAME} signature in '{output_dir}'. Refusing to clean directory."
        )

    # Check the whole tree before removing any previous output.
    for root, directories, files in os.walk(output_dir, followlinks=False):
        for name in directories + files:
            entry = Path(root) / name
            if entry.is_symlink() or entry.is_junction():
                raise RuntimeError(f"Refusing linked build entry: {entry}")
    clean_directory_contents_safely(output_dir)

    # Re-write fresh marker
    marker_path.write_text(MARKER_SIGNATURE, encoding="utf-8")


def render_html_page(
    *,
    title: str,
    description: str,
    canonical_url: str,
    base_url: str,
    site_data: Dict[str, Any],
    body_content: str,
    current_slug: str = "",
    og_type: str = "website",
    is_404: bool = False,
    extra_meta: str = "",
    json_ld: Optional[Dict[str, Any]] = None,
    social_image: Optional[Dict[str, Any]] = None,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    """Renders a complete HTML page matching the DOM, accessibility, and localization contracts."""
    site_name = escape(site_data.get("name", "Audit Commons"))
    if locale == "zh":
        site_tagline = escape("关于 AI 审计的新闻、深度分析与实践学习。")
    else:
        site_tagline = escape(site_data.get("tagline", "Research, tools, and community for AI auditing."))

    maintainer = site_data.get("maintainer", {})
    maintainer_name = escape(maintainer.get("name", "Yue Zhao"))
    maintainer_url = escape(maintainer.get("url", "https://viterbi-web.usc.edu/~yzhao010/"))

    escaped_title = escape(title)
    full_title = f"{escaped_title} | {site_name}" if title != site_name else site_name
    escaped_desc = escape(description)
    escaped_canonical = escape(canonical_url)
    social_png_url = f"{base_url.rstrip('/')}/assets/social-preview.png"
    social_width, social_height = 1200, 630
    social_alt = f"{site_name}: {site_tagline}"
    if social_image_eligible(social_image):
        social_png_url = base_url.rstrip('/') + social_image['src']
        social_width, social_height = social_image['width'], social_image['height']
        social_alt = escape(social_image['alt'])

    # Robots tag: 404 must not be indexed
    robots_tag = '<meta name="robots" content="noindex, follow">' if is_404 else '<meta name="robots" content="index, follow, max-image-preview:large">'

    html_lang = LOCALE_LANG.get(locale, "en")
    og_locale = LOCALE_OG.get(locale, "en_US")
    hreflang_tags = get_hreflang_tags(base_url, current_slug, has_zh=has_zh) if not is_404 else ""
    lang_switch_html = render_language_switcher(current_slug, locale, has_zh=has_zh)

    # Navigation links - use exact match + explicit prefix map
    nav_items = REQUIRED_NAV_ITEMS_ZH if locale == "zh" else REQUIRED_NAV_ITEMS
    clean_current = normalize_slug(current_slug)
    nav_links_html = []
    for label, target in nav_items:
        target_slug = target.strip("/").removeprefix("zh/").strip("/")
        # Exact match
        is_active = (clean_current == target_slug)
        if not is_active:
            # Check via prefix map
            prefixes = NAV_SLUG_PREFIXES.get(target_slug, [])
            for pfx in prefixes:
                if pfx.endswith("/"):
                    is_active = clean_current.startswith(pfx) or clean_current + "/" == pfx
                else:
                    is_active = (clean_current == pfx) or clean_current.startswith(pfx + "/")
                if is_active:
                    break
        current_value = "page" if clean_current == target_slug else "true"
        active_attr = f' class="active" aria-current="{current_value}"' if is_active else ""
        nav_links_html.append(f'<a href="{target}"{active_attr}>{escape(label)}</a>')
    nav_html = "\n        ".join(nav_links_html)

    # Brand and Header labels
    brand_href = route_href("", locale)
    brand_aria = "Audit Commons 首页" if locale == "zh" else "Audit Commons Homepage"
    brand_subtitle = "AI 审计" if locale == "zh" else "AI Auditing"
    skip_text = "跳转至主要内容" if locale == "zh" else "Skip to main content"
    nav_aria = "主导航" if locale == "zh" else "Main Navigation"

    # Feed Link
    feed_url = f"{base_url.rstrip('/')}/zh/feed.xml" if locale == "zh" else f"{base_url.rstrip('/')}/feed.xml"
    feed_title = f"{site_name} (中文) 订阅" if locale == "zh" else f"{site_name} Feed"

    # JSON-LD Structured Data with script breakout protection
    json_ld_html = ""
    if json_ld:
        safe_json_str = serialize_json_ld(json_ld)
        json_ld_html = f'<script type="application/ld+json">\n{safe_json_str}\n</script>'

    # Footer
    if locale == "zh":
        footer_html = f"""  <footer class="site-footer">
    <div class="container footer-grid">
      <div class="footer-col footer-about">
        <h2>Audit Commons</h2>
        <p class="footer-tagline">{site_tagline}</p>
        <p class="footer-maintainer">维护者：<a href="{maintainer_url}">{maintainer_name}</a>。</p>
      </div>

      <div class="footer-col footer-links">
        <h2>内容栏目</h2>
        <ul>
          <li><a href="/zh/latest/">最新内容</a></li>
          <li><a href="/zh/latest/?kind=feature">深度解读</a></li>
          <li><a href="/zh/learn/">学习指南</a></li>
          <li><a href="/zh/resources/">资源目录</a></li>
          <li><a href="/zh/about/">关于本站</a></li>
        </ul>
      </div>

      <div class="footer-col footer-editorial">
        <h2>关注与参与</h2>
        <ul>
          <li><a href="/zh/about/#contact">联系编辑</a></li>
          <li><a href="/zh/about/#contribute">贡献指南</a></li>
          <li><a href="/zh/about/#corrections">提交勘误</a></li>
          <li><a href="/zh/feed.xml">通过 RSS / Atom 订阅</a></li>
          <li><a href="https://github.com/yzhao062/audit-commons">网站源码</a></li>
          <li><a href="https://github.com/yzhao062/awesome-auditable-ai">Awesome Auditable AI</a></li>
        </ul>
      </div>
    </div>
    <div class="container footer-bottom">
      <p class="footer-copy">&copy; 2026 Audit Commons. {site_tagline}</p>
    </div>
  </footer>"""
    else:
        footer_html = f"""  <footer class="site-footer">
    <div class="container footer-grid">
      <div class="footer-col footer-about">
        <h2>Audit Commons</h2>
        <p class="footer-tagline">{site_tagline}</p>
        <p class="footer-maintainer">Maintained by <a href="{maintainer_url}">{maintainer_name}</a>.</p>
      </div>

      <div class="footer-col footer-links">
        <h2>Editorial Sections</h2>
        <ul>
          <li><a href="/latest/">Latest additions</a></li>
          <li><a href="/latest/?kind=feature">Analysis</a></li>
          <li><a href="/learn/">Learn</a></li>
          <li><a href="/resources/">Resources</a></li>
          <li><a href="/about/">About</a></li>
        </ul>
      </div>

      <div class="footer-col footer-editorial">
        <h2>Connect</h2>
        <ul>
          <li><a href="/about/#contact">Contact the editor</a></li>
          <li><a href="/about/#contribute">Contribution Guide</a></li>
          <li><a href="/about/#corrections">Submit Corrections</a></li>
          <li><a href="/feed.xml">Follow via RSS / Atom</a></li>
          <li><a href="https://github.com/yzhao062/audit-commons">Website source</a></li>
          <li><a href="https://github.com/yzhao062/awesome-auditable-ai">Awesome Auditable AI</a></li>
        </ul>
      </div>
    </div>
    <div class="container footer-bottom">
      <p class="footer-copy">&copy; 2026 Audit Commons. {site_tagline}</p>
    </div>
  </footer>"""

    hreflang_block = f"\n{hreflang_tags}" if hreflang_tags else ""

    return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{full_title}</title>
  <meta name="description" content="{escaped_desc}">
  <link rel="canonical" href="{escaped_canonical}">{hreflang_block}
  {robots_tag}

  <!-- Open Graph / Facebook -->
  <meta property="og:site_name" content="{site_name}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:title" content="{full_title}">
  <meta property="og:description" content="{escaped_desc}">
  <meta property="og:url" content="{escaped_canonical}">
  <meta property="og:locale" content="{og_locale}">
  <meta property="og:image" content="{social_png_url}">
  <meta property="og:image:width" content="{social_width}">
  <meta property="og:image:height" content="{social_height}">
  <meta property="og:image:alt" content="{social_alt}">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{full_title}">
  <meta name="twitter:description" content="{escaped_desc}">
  <meta name="twitter:image" content="{social_png_url}">

  <!-- Feed and Favicon -->
  <link rel="alternate" type="application/atom+xml" title="{feed_title}" href="{feed_url}">
  <link rel="icon" href="/favicon.svg?v=graphite" type="image/svg+xml">
  <link rel="stylesheet" href="{escape(site_data.get('_style_href', '/assets/style.css'))}">
  <script src="/assets/site.js" defer></script>
  {extra_meta}
  {json_ld_html}
</head>
<body>
  <a class="skip-link" href="#main">{skip_text}</a>

  <header class="site-header">
    <div class="container header-container">
      <a href="{brand_href}" class="brand" aria-label="{brand_aria}">
        <img src="/assets/mark.svg?v=graphite" alt="" width="38" height="38" class="brand-icon">
        <span class="brand-text">
          <span class="brand-title">Audit Commons</span>
          <span class="brand-subtitle">{brand_subtitle}</span>
        </span>
      </a>
      <nav class="site-nav" aria-label="{nav_aria}">
        {nav_html}
      </nav>
{lang_switch_html}
    </div>
  </header>

  <main id="main" tabindex="-1">
{body_content}
  </main>

{footer_html}
</body>
</html>"""


def _kind_label(kind: str, locale: str = "en") -> str:
    """Human-readable label for an article kind."""
    if locale == "zh":
        return KIND_LABELS_ZH.get(kind, "文章")
    return {
        "introduction": "Orientation",
        "guide": "Guide",
        "release": "Release",
        "news": "News",
        "feature": "Analysis",
        "about": "About",
    }.get(kind, "Article")


def build_follow_section(locale: str = "en") -> str:
    if locale == "zh":
        return """
    <section class="follow-section" aria-labelledby="follow-heading">
      <h2 id="follow-heading">关注 Audit Commons</h2>
      <p>在您的阅读器中及时获取最新报道、实践指南与精选资源。</p>
      <div class="follow-links">
        <a href="/zh/feed.xml">通过 RSS / Atom 订阅 &rarr;</a>
        <a href="/zh/about/#contribute">推荐报道或资源 &rarr;</a>
      </div>
    </section>"""
    return """
    <section class="follow-section" aria-labelledby="follow-heading">
      <h2 id="follow-heading">Follow Audit Commons</h2>
      <p>Keep up with new reporting, practical guides, and resources in your feed reader.</p>
      <div class="follow-links">
        <a href="/feed.xml">Follow via RSS / Atom &rarr;</a>
        <a href="/about/#contribute">Suggest a story or resource &rarr;</a>
      </div>
    </section>"""


def build_homepage(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    resources: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    """Build editorial publication front page."""
    if locale == "zh":
        title = "AI 审计新闻、指南与资源"
        description = "关于 AI 审计实践与研究的专题报道。"
        announced_label = "公布于"
        published_label = "发布于"
        byline_prefix = "文 / "
        read_article_text = "阅读全文 &rarr;"
        news_section_title = "新闻与动态"
        see_all_text = "查看全部 &rarr;"
        learn_section_title = "学习"
        all_guides_text = "所有指南 &rarr;"
        selected_res_title = "精选资源"
        full_catalog_text = "完整目录 &rarr;"
        maintainer_tag = " · 维护者项目"
        masthead_sub = "新闻、分析与学习"
        masthead_site = "AI 审计"
    else:
        title = "AI Auditing News, Guides & Resources"
        description = site_data.get("description", "Editorial coverage of AI auditing practice and research.")
        announced_label = "Announced"
        published_label = "Published"
        byline_prefix = "By "
        read_article_text = "Read article &rarr;"
        news_section_title = "News &amp; Releases"
        see_all_text = "See all &rarr;"
        learn_section_title = "Learn"
        all_guides_text = "All guides &rarr;"
        selected_res_title = "Selected Resources"
        full_catalog_text = "Full catalog &rarr;"
        maintainer_tag = " · Maintainer project"
        masthead_sub = "News, analysis &amp; learning"
        masthead_site = "AI auditing"

    editorial_kinds_priority = ["feature", "news", "guide", "introduction", "release"]
    editorial_pages = [p for p in pages if p.get("kind") not in ("about",)]
    lead_page = None
    for kind in editorial_kinds_priority:
        candidates = sorted(
            [p for p in editorial_pages if p.get("kind") == kind],
            key=lambda p: p.get("published", ""),
            reverse=True,
        )
        if candidates:
            lead_page = candidates[0]
            break

    lead_html = ""
    if lead_page:
        lp = lead_page
        lp_kind = lp.get("kind", "article")
        lp_label = _kind_label(lp_kind, locale)
        lp_event_date = lp.get("event_date", "")
        lp_pub = lp.get("published", "")
        event_date_html = ""
        if lp_event_date and lp_event_date != lp_pub:
            event_date_html = f'<span class="pub-lead-event-date">{announced_label} <time datetime="{escape(lp_event_date)}">{display_date(lp_event_date, locale)}</time></span>'
        lead_html = f"""
    <section class="pub-lead-section" aria-labelledby="pub-lead-heading">
      <div class="pub-lead-meta">
        <span class="pub-lead-label">{escape(lp_label)}</span>
        {event_date_html}
        <span class="pub-lead-date">{published_label} <time datetime="{escape(lp_pub)}">{display_date(lp_pub, locale)}</time></span>
      </div>
      <h1 class="pub-lead-headline" id="pub-lead-heading">
        <a href="{route_href(lp['slug'], locale)}">{escape(lp['title'])}</a>
      </h1>
      <p class="pub-lead-summary">{escape(lp.get('summary', ''))}</p>
      {render_media(lp, 'lead', route_href(lp['slug'], locale), priority=True)}
      <p class="pub-lead-byline">{byline_prefix}{escape(lp.get('author', 'Audit Commons'))}</p>
      <a class="pub-section-more" href="{route_href(lp['slug'], locale)}">{read_article_text}</a>
    </section>"""

    # Compact news list (news + release, sorted by published desc, exclude lead)
    news_kinds = {"news", "release"}
    news_items = sorted(
        [p for p in pages if p.get("kind") in news_kinds and p is not lead_page],
        key=lambda p: p.get("published", ""),
        reverse=True,
    )[:5]
    news_rows = ""
    for item in news_items:
        item_label = _kind_label(item.get("kind", ""), locale)
        item_event = item.get("event_date", "")
        item_pub = item.get("published", "")
        event_bit = ""
        if item_event and item_event != item_pub:
            event_bit = f'<span class="news-list-event">{announced_label} <time datetime="{escape(item_event)}">{display_date(item_event, locale)}</time></span> '
        disclosure_bit = f'<p class="news-list-disclosure">{escape(item.get("affiliation_disclosure", ""))}</p>' if item.get("kind") == "release" else ""
        news_rows += f"""
        <li class="news-list-item">
          {render_media(item, 'compact', route_href(item['slug'], locale))}
          <div class="news-list-copy">
          <div class="news-list-meta"><span class="news-list-label">{escape(item_label)}</span>
          <span class="news-list-date">{published_label} <time datetime="{escape(item_pub)}">{display_date(item_pub, locale)}</time></span></div>
          <a class="news-list-title" href="{route_href(item['slug'], locale)}">{escape(item['title'])}</a>
          {event_bit}{disclosure_bit}
          </div>
        </li>"""

    news_section_html = ""
    if news_rows:
        news_section_html = f"""
    <section class="pub-news-section" aria-labelledby="news-list-heading">
      <div class="pub-section-bar">
        <h2 id="news-list-heading" class="pub-section-title">{news_section_title}</h2>
        <a class="pub-section-more" href="{route_href('latest', locale)}">{see_all_text}</a>
      </div>
      <ul class="news-list">{news_rows}
      </ul>
    </section>"""

    # Learning articles (introduction + guide, not the lead)
    learn_items = [p for p in pages if p.get("kind") in ("introduction", "guide") and p is not lead_page]
    learn_entries = ""
    for p in learn_items:
        plabel = _kind_label(p.get("kind", ""), locale)
        learn_entries += f"""
        <article class="reading-entry">
          {render_media(p, 'compact', route_href(p['slug'], locale))}
          <span class="eyebrow">{escape(plabel)}</span>
          <h3><a href="{route_href(p['slug'], locale)}">{escape(p['title'])}</a></h3>
          <p>{escape(p.get('summary', ''))}</p>
        </article>"""

    learn_html = ""
    if learn_entries:
        learn_html = f"""
    <section class="pub-learn-section" aria-labelledby="learn-heading">
      <div class="pub-section-bar">
        <h2 id="learn-heading" class="pub-section-title">{learn_section_title}</h2>
        <a class="pub-section-more" href="{route_href('learn', locale)}">{all_guides_text}</a>
      </div>
      <div class="pub-learning-grid">{learn_entries}</div>
    </section>"""

    # Selected resources
    res_by_id = {r.get("id"): r for r in resources if r.get("id")}
    curated_selected = [res_by_id[rid] for rid in CURATED_HOME_RESOURCE_IDS if rid in res_by_id]
    if len(curated_selected) < 6:
        for r in resources:
            if r not in curated_selected:
                curated_selected.append(r)
                if len(curated_selected) == 6:
                    break

    res_rows = ""
    for res in curated_selected:
        rel_label = maintainer_tag if res.get('relationship') == 'Maintainer project' else ''
        res_rows += f"""
        <li class="home-res-item">
          {render_media(res, 'resource', res['url'])}
          <a href="{escape(res['url'])}" class="home-res-link">{escape(res['name'])} <span aria-hidden="true">&nearr;</span></a>
          <span class="home-res-cat">{escape(CATEGORY_DISPLAY_LABELS_ZH.get(res.get('category', ''), res.get('category', '')) if locale == 'zh' else res.get('category', ''))}{rel_label}</span>
        </li>"""

    res_section_html = f"""
    <section class="pub-resources-section" aria-labelledby="res-heading">
      <div class="pub-section-bar">
        <h2 id="res-heading" class="pub-section-title">{selected_res_title}</h2>
        <a class="pub-section-more" href="{route_href('resources', locale)}">{full_catalog_text}</a>
      </div>
      <ul class="home-res-list">{res_rows}
      </ul>
    </section>"""

    body_content = f"""
    <div class="container pub-home">
      <header class="pub-masthead">
        {'<p class="pub-site-name">' + masthead_site + '</p>' if lead_page else '<h1 class="pub-site-name">Audit Commons</h1>'}
        <p class="pub-scope">{masthead_sub}</p>
      </header>

      <div class="pub-front-grid">
        <div class="pub-front-main">
          {lead_html}
        </div>
        <div class="pub-front-sidebar">
          {news_section_html}
        </div>
      </div>
      {build_follow_section(locale)}
      {learn_html}
      {res_section_html}
    </div>
"""
    json_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": canonical_for(base_url, "", locale) + "#website",
        "inLanguage": LOCALE_LANG.get(locale, "en"),
        "name": site_data.get("name", "Audit Commons"),
        "url": canonical_for(base_url, "", locale),
        "description": description,
        "publisher": publication_identity(site_data, base_url, locale),
    }
    return render_html_page(
        title=title,
        description=description,
        canonical_url=canonical_for(base_url, "", locale),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="" if locale == "en" else "zh",
        og_type="website",
        json_ld=json_ld,
        locale=locale,
        has_zh=has_zh,
    )


def build_resources_page(
    site_data: Dict[str, Any],
    resources: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
    reading_lists: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Generates the searchable, filterable resource catalog with accessible format tabs."""
    categories = ["All", "Evaluation", "Security", "Governance", "Reading", "Tools"]

    filter_buttons_html = []
    for cat in categories:
        is_all = (cat == "All")
        pressed = "true" if is_all else "false"
        active_cls = " is-active" if is_all else ""
        btn_label = CATEGORY_DISPLAY_LABELS_ZH[cat] if locale == "zh" else cat
        btn = f'<button type="button" class="filter-button{active_cls}" data-filter="{cat}" aria-pressed="{pressed}">{btn_label}</button>'
        filter_buttons_html.append(btn)
    buttons_markup = "\n          ".join(filter_buttons_html)

    # Compute counts per format
    format_counts: dict[str, int] = {}
    for r in resources:
        for fmt in resource_formats(r):
            format_counts[fmt] = format_counts.get(fmt, 0) + 1

    total_count = len(resources)

    # Build format tabs with true ARIA tab semantics
    all_tab_label = "全部" if locale == "zh" else "All"
    format_tabs_html = [
        f'<button type="button" role="tab" id="tab-all" class="format-tab is-active" aria-selected="true" aria-controls="resources-panel" tabindex="0" data-format="all">{all_tab_label} <span class="format-count">({total_count})</span></button>'
    ]
    for fmt in VALID_RESOURCE_FORMATS:
        cnt = format_counts.get(fmt, 0)
        if cnt > 0:
            fmt_id = fmt.lower()
            fmt_label = FORMAT_DISPLAY_LABELS_ZH.get(fmt, fmt) if locale == "zh" else FORMAT_DISPLAY_LABELS.get(fmt, f"{fmt}s")
            format_tabs_html.append(
                f'<button type="button" role="tab" id="tab-{fmt_id}" class="format-tab" aria-selected="false" aria-controls="resources-panel" tabindex="-1" data-format="{fmt}">{fmt_label} <span class="format-count">({cnt})</span></button>'
            )
    format_tabs_markup = "\n            ".join(format_tabs_html)

    cards_html = []
    for r in resources:
        r_name = escape(r.get("name", ""))
        r_url = escape(r.get("url", "#"))
        r_cat = escape(r.get("category", ""))
        r_rel = escape(r.get("relationship", ""))
        r_sum = escape(r.get("summary", ""))
        owner = r.get("owner", "")
        r_owner = escape("见论文作者名单" if locale == "zh" and owner == "Authors listed in the paper" else owner)
        r_checked = escape(r.get("checked", ""))
        format_val = r.get("format") or "Collection"
        formats = resource_formats(r)
        r_section = r.get("source_section", "")
        r_venue = r.get("venue", "")
        links = r.get("links", [])
        catalog_source = r.get("catalog_source", "")
        source_urls = r.get("source_urls", [])

        topic_display = r_section if r_section else r_cat
        topic_display_localized = (SECTION_DISPLAY_LABELS_ZH.get(r_section, r_section) if r_section else CATEGORY_DISPLAY_LABELS_ZH.get(r_cat, r_cat)) if locale == "zh" else topic_display

        # Comprehensive search fields ensuring both English and Chinese queries match
        search_fields = [
            r.get("name", ""),
            r.get("summary", ""),
            r.get("_search_summary", ""),
            r.get("owner", ""),
            r.get("category", ""),
            CATEGORY_DISPLAY_LABELS_ZH.get(r.get("category", ""), ""),
            r.get("relationship", ""),
            "维护者项目" if r.get("relationship") == "Maintainer project" else "外部资源",
            " ".join(formats),
            " ".join(FORMAT_DISPLAY_LABELS_ZH.get(f, f) for f in formats),
            r_section,
            r_venue,
        ]
        if isinstance(links, list):
            for lk in links:
                if isinstance(lk, dict):
                    search_fields.append(lk.get("label", ""))
                    search_fields.append(lk.get("url", ""))
        if isinstance(source_urls, list):
            for u in source_urls:
                search_fields.append(u)
        search_terms = " ".join(str(f) for f in search_fields if f).lower()

        # Tags
        tags_html = [
            f'<span class="tag tag-format tag-format-{escape(fmt.lower())}">{escape(FORMAT_DISPLAY_LABELS_ZH.get(fmt, fmt) if locale == "zh" else fmt)}</span>'
            for fmt in formats
        ]
        tags_html.append(f'<span class="tag tag-topic" data-category="{r_cat}">{escape(topic_display_localized)}</span>')
        if r_venue:
            tags_html.append(f'<span class="tag tag-venue">{escape(r_venue)}</span>')
        if r_rel == "Maintainer project":
            tags_html.append(f'<span class="tag tag-maintainer">{"维护者项目" if locale == "zh" else "Maintainer project"}</span>')
        else:
            tags_html.append(f'<span class="tag tag-relationship">{"外部资源" if locale == "zh" else r_rel}</span>')
        tags_markup = "\n              ".join(tags_html)

        # Artifact / secondary links
        links_markup = ""
        if isinstance(links, list) and links:
            pills = []
            for lk in links:
                if isinstance(lk, dict) and lk.get("url"):
                    label = lk.get("label") or "Link"
                    if locale == "zh":
                        label = {"Paper": "论文", "Code": "代码", "Data": "数据", "Dataset": "数据集", "Docs": "文档", "Documentation": "文档", "Project": "项目", "Website": "网站", "Link": "链接"}.get(label, label)
                    lbl = escape(label)
                    pills.append(f'<a href="{escape(lk["url"])}" class="resource-pill" rel="noopener noreferrer">{lbl} <span class="external-arrow" aria-hidden="true">&nearr;</span></a>')
            if pills:
                links_markup = f'\n          <div class="resource-links" aria-label="{"相关资料链接" if locale == "zh" else "Artifact links"}">{" ".join(pills)}</div>'

        # Provenance details
        if locale == "zh":
            prov_items = [
                f'<p class="provenance-item"><strong>归属：</strong> {r_owner}</p>',
                f'<p class="provenance-item"><strong>审核状态：</strong> 于 <time datetime="{r_checked}">{r_checked}</time> 对照目录快照完成核对（外部链接未进行运行时验证）。</p>',
            ]
            if r_rel == "Maintainer project":
                prov_items.append('<p class="provenance-item provenance-disclosure"><strong>维护者披露：</strong> 由 Audit Commons 维护者（Yue Zhao）编写或维护。仅因相关性收录，不包含机构背书。</p>')
            if catalog_source:
                prov_items.append(f'<p class="provenance-item"><strong>目录来源：</strong> <a href="{escape(catalog_source)}" rel="noopener noreferrer">Awesome Auditable AI 条目</a></p>')
            if source_urls:
                url_list = "".join(f'<li><a href="{escape(u)}" rel="noopener noreferrer">{escape(u)}</a></li>' for u in source_urls)
                prov_items.append(f'<div class="provenance-sources"><strong>原始来源：</strong><ul class="source-list">{url_list}</ul></div>')
            if res_media := r.get('_media'):
                prov_items.append(f'<p class="provenance-item"><strong>图片：</strong> {media_credit(res_media)}。{escape(res_media["changes"])}</p>')
            prov_toggle = "来源与溯源信息"
        else:
            prov_items = [
                f'<p class="provenance-item"><strong>Attribution:</strong> {r_owner}</p>',
                f'<p class="provenance-item"><strong>Review status:</strong> Catalog reviewed <time datetime="{r_checked}">{r_checked}</time> against catalog snapshot (external links are not runtime verified).</p>',
            ]
            if r_rel == "Maintainer project":
                prov_items.append('<p class="provenance-item provenance-disclosure"><strong>Maintainer disclosure:</strong> Authored or maintained by Audit Commons maintainers (Yue Zhao). Listed for relevance without institutional endorsement.</p>')
            if catalog_source:
                prov_items.append(f'<p class="provenance-item"><strong>Catalog source:</strong> <a href="{escape(catalog_source)}" rel="noopener noreferrer">Awesome Auditable AI record</a></p>')
            if source_urls:
                url_list = "".join(f'<li><a href="{escape(u)}" rel="noopener noreferrer">{escape(u)}</a></li>' for u in source_urls)
                prov_items.append(f'<div class="provenance-sources"><strong>Primary sources:</strong><ul class="source-list">{url_list}</ul></div>')
            if res_media := r.get('_media'):
                prov_items.append(f'<p class="provenance-item"><strong>Image:</strong> {media_credit(res_media)}. {escape(res_media["changes"])}</p>')
            prov_toggle = "Provenance &amp; sources"

        card = f"""
        <article class="resource-card" data-category="{r_cat}" data-format="{escape(format_val)}" data-formats="{escape(' '.join(formats))}" data-search="{escape(search_terms)}">
          {render_media(r, 'resource', r['url'])}
          <div class="resource-card-header">
            <div class="resource-tags">
              {tags_markup}
            </div>
            <h2 class="resource-title"><a href="{r_url}">{r_name} <span class="external-arrow" aria-hidden="true">&nearr;</span></a></h2>
          </div>
          <p class="resource-summary">{r_sum}</p>{links_markup}
          <details class="resource-provenance">
            <summary class="provenance-toggle">{prov_toggle}</summary>
            <div class="provenance-body">
              {"".join(prov_items)}
            </div>
          </details>
        </article>"""
        cards_html.append(card)

    grid_html = "\n".join(cards_html)

    if locale == "zh":
        page_title = "AI 审计资源库：论文、工具与基准评测"
        page_desc = "浏览关于 AI 审计的研究论文、工具、基准、数据集、标准与精选合集，支持主题筛选并提供原始来源链接。"
        eyebrow = "目录"
        heading = "AI 审计资源库"
        page_lead = "用于研究和审计 AI 系统的学术论文、实用工具、基准评测、数据集与规范标准。"
        notice_html = '<p>改编自 <a href="https://github.com/yzhao062/awesome-auditable-ai">Awesome Auditable AI</a>。收录条目描述沿用对应目录；收录并不代表对相关成果进行独立评测。各条目均记录了其来源与审核日期。<a href="/zh/about/#contribute">推荐资源或提交修正</a>。</p>'
        format_region_label = "格式筛选"
        format_tablist_label = "按格式筛选资源"
        search_label = "搜索资源"
        search_placeholder = "按名称、摘要、主题、所有者、发表会议搜索..."
        category_group_label = "按分类筛选"
        category_prefix = "分类："
        count_text = f"显示全部 {total_count} 项资源"
        format_note = "部分资源属于多个格式分类。全部标签下每项资源仅计算一次。"
        empty_text = "没有符合您搜索或筛选条件的资源。"
        reset_text = "重置搜索"
    else:
        page_title = "AI Auditing Resources: Papers, Tools & Benchmarks"
        page_desc = "Browse research papers, tools, benchmarks, datasets, standards, and collections about AI auditing, with topic filters and links to original sources."
        eyebrow = "Catalog"
        heading = "AI auditing library"
        page_lead = "Papers, tools, benchmarks, datasets, and standards for studying and auditing AI systems."
        notice_html = '<p>Adapted from <a href="https://github.com/yzhao062/awesome-auditable-ai">Awesome Auditable AI</a>. Descriptions follow the linked catalog; inclusion is not an independent evaluation of the work. Each entry records its source and review date. <a href="/about/#contribute">Suggest a resource or correction</a>.</p>'
        format_region_label = "Format filter"
        format_tablist_label = "Filter resources by format"
        search_label = "Search resources"
        search_placeholder = "Search by name, summary, topic, owner, venue..."
        category_group_label = "Filter by category"
        category_prefix = "Category:"
        count_text = f"Showing all {total_count} resources"
        format_note = "Resources can appear in more than one format. All counts each resource once."
        empty_text = "No resources match your search or filter criteria."
        reset_text = "Reset search"

    selections_html = ""
    if reading_lists:
        res_lookup = {r.get("id"): r for r in resources if isinstance(r, dict) and "id" in r}
        selections_html = "\n" + render_reading_lists_html(reading_lists, res_lookup, locale=locale)

    body_content = f"""
    <div class="container">
      <header class="page-header resource-page-header">
        <span class="eyebrow">{eyebrow}</span>
        <h1>{heading}</h1>
        <p class="page-lead">{page_lead}</p>
        <div class="catalog-upstream-notice">
          {notice_html}
        </div>
      </header>{selections_html}

      <div id="resource-controls" hidden>
        <div class="format-tabs-bar" role="region" aria-label="{format_region_label}">
          <div role="tablist" aria-label="{format_tablist_label}" class="format-tabs">
            {format_tabs_markup}
          </div>
        </div>

        <div class="resource-filters-row">
          <div class="resource-search-wrapper">
            <label for="resource-search" class="search-label">{search_label}</label>
            <input type="search" id="resource-search" placeholder="{search_placeholder}" autocomplete="off">
          </div>
          <div class="category-filters" role="group" aria-label="{category_group_label}">
            <span class="filter-group-label">{category_prefix}</span>
            {buttons_markup}
          </div>
        </div>

        <div id="resource-count" role="status" aria-live="polite">{count_text}</div>
        <p class="resource-format-note">{format_note}</p>
      </div>

      <div id="no-results" class="empty-state" hidden>
        <p>{empty_text}</p>
        <button type="button" data-action="reset" class="button button-secondary">{reset_text}</button>
      </div>

      <section id="resources-panel" role="tabpanel" aria-labelledby="tab-all" tabindex="0" class="resources-panel">
        <div class="resource-grid">
          {grid_html}
        </div>
      </section>
    </div>
"""

    return render_html_page(
        title=page_title,
        description=page_desc,
        canonical_url=canonical_for(base_url, "resources", locale),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="resources" if locale == "en" else "zh/resources",
        og_type="website",
        locale=locale,
        has_zh=has_zh,
    )


def build_guides_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    title = "实践指南" if locale == "zh" else "Guides"
    eyebrow = "学习" if locale == "zh" else "Learn"
    description = "解读评测证据与审计 AI 系统的实用指南。" if locale == "zh" else "Practical guides to reading evidence and auditing AI systems."
    empty_msg = "暂无已发布的实践指南。" if locale == "zh" else "No guides published yet."
    return _render_article_list_index(
        site_data=site_data, pages=[p for p in pages if p.get("kind") == "guide"],
        base_url=base_url, title=title, slug="guides", eyebrow=eyebrow,
        description=description, empty_msg=empty_msg, locale=locale, has_zh=has_zh,
    )


def build_updates_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    title = "版本发布" if locale == "zh" else "Releases"
    eyebrow = "最新" if locale == "zh" else "Latest"
    description = "版本更新说明、原始来源与维护者信息披露。" if locale == "zh" else "Release notes, sources, and maintainer disclosures."
    empty_msg = "暂无已发布的版本更新。" if locale == "zh" else "No release notes published yet."
    return _render_article_list_index(
        site_data=site_data, pages=[p for p in pages if p.get("kind") == "release"],
        base_url=base_url, title=title, slug="updates", eyebrow=eyebrow,
        description=description, empty_msg=empty_msg, locale=locale, has_zh=has_zh,
    )


def build_latest_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    """Generates /latest/ (or /zh/latest/) — all editorial additions sorted most-recent-first."""
    editorial = [p for p in pages if p.get("kind") not in ("about",)]
    title = "最新内容" if locale == "zh" else "Latest Additions"
    eyebrow = "全站目录" if locale == "zh" else "Publication index"
    description = "Audit Commons 刊发的全部内容，按最新发布时间排序。" if locale == "zh" else "All editorial content added to Audit Commons, most recently published first."
    empty_msg = "暂无已发布的内容。" if locale == "zh" else "No articles published yet."
    return _render_article_list_index(
        site_data=site_data, pages=editorial, base_url=base_url,
        title=title, description=description, eyebrow=eyebrow,
        slug="latest", empty_msg=empty_msg, locale=locale, has_zh=has_zh,
        is_latest=True,
    )


def build_features_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    """Generates /features/ (or /zh/features/) — feature-kind articles."""
    features = [p for p in pages if p.get("kind") == "feature"]
    title = "深度解读" if locale == "zh" else "Analysis"
    eyebrow = "深度解读" if locale == "zh" else "Analysis"
    description = "深入探讨 AI 审计研究、实践与政策的专题解读与分析。" if locale == "zh" else "In-depth editorial analysis on AI auditing research, practice, and policy."
    empty_msg = "暂无已发布的深度解读文章。" if locale == "zh" else "No analysis articles published yet."
    contextual_note = (
        f'<p class="topic-legacy-note"><a href="{route_href("latest", locale)}?kind=feature">&larr; 在最新发布中按深度解读筛选</a></p>'
        if locale == "zh"
        else f'<p class="topic-legacy-note"><a href="{route_href("latest", locale)}?kind=feature">&larr; View all Analysis articles in Latest</a></p>'
    )
    return _render_article_list_index(
        site_data=site_data, pages=features, base_url=base_url,
        title=title, description=description, eyebrow=eyebrow,
        slug="features", empty_msg=empty_msg, locale=locale, has_zh=has_zh,
        contextual_note=contextual_note,
    )


def build_learn_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    has_zh: bool = True,
    has_selections: bool = False,
) -> str:
    """Generates /learn/ (or /zh/learn/) — structured 3-step editorial learning path."""
    page_map = {p.get("slug"): p for p in pages}
    is_zh = (locale == "zh")

    # Curated 3-step learning path sequence
    steps_data = [
        {
            "step_num": "01",
            "slug": "start-here",
            "kicker": "第一步 · 核心概念" if is_zh else "Step 1 · Core Concepts",
            "nav_label": "理解可审计 AI" if is_zh else "Understand auditable AI",
            "time_display": "阅读用时：约 2 分钟" if is_zh else "Reading: ~2 min",
            "outcome": (
                "区分评估、监控与审计的边界，并理解为何模型内部文本不能证明外部行动确实发生。"
                if is_zh else
                "Distinguish evaluation, monitoring, and auditing, and recognize why internal model text cannot prove an external action occurred."
            ),
            "read_text": "阅读导读" if is_zh else "Read introduction",
            "resources": [
                {
                    "title": "NIST AI 风险管理框架 (AI RMF 1.0)" if is_zh else "NIST AI Risk Management Framework (AI RMF 1.0)",
                    "href": f"{route_href('resources', locale)}?q=NIST%20AI",
                    "desc": "用于梳理 AI 风险与审计问题的自愿性框架。" if is_zh else "Voluntary framework for organizing risk taxonomy and audit questions.",
                },
                {
                    "title": "Inspect 评估框架" if is_zh else "Inspect Framework",
                    "href": f"{route_href('resources', locale)}?q=Inspect",
                    "desc": "英国 AISI 推出的开源评测工具，用于设计可复现的基准测试。" if is_zh else "AISI open-source framework for reproducible model and agent evaluations.",
                },
            ],
        },
        {
            "step_num": "02",
            "slug": "guides/how-to-read-an-agent-eval-report",
            "kicker": "第二步 · 报告评估" if is_zh else "Step 2 · Report Evaluation",
            "nav_label": "阅读评估报告" if is_zh else "Read an evaluation report",
            "time_display": "阅读用时：约 4 分钟 | 案例演练：约 10 分钟（共计约 14 分钟）" if is_zh else "Reading: ~4 min | Worked critique: ~10 min (Total ~14 min)",
            "outcome": (
                "围绕任务、算力、样本量、失败模式与结论边界提出五个关键问题，判断评估证据是否支撑其结论。"
                if is_zh else
                "Ask five questions about tasks, compute, sample size, failure modes, and evidence bounds to judge whether an evaluation supports its claims."
            ),
            "read_text": "阅读指南" if is_zh else "Read guide",
            "resources": [
                {
                    "title": "Inspect 评估工具" if is_zh else "Inspect",
                    "href": f"{route_href('resources', locale)}?q=Inspect",
                    "desc": "包含可复用任务、评分器与审查日志的评测工具。" if is_zh else "Evaluation framework with reusable tasks, tools, scorers, and inspection logs.",
                },
                {
                    "title": "资源库：基准评测" if is_zh else "Catalog: Benchmarks",
                    "href": f"{route_href('resources', locale)}?format=Benchmark",
                    "desc": "在资源目录中查阅精选评测基准。" if is_zh else "Explore curated evaluation benchmarks in the resource catalog.",
                },
            ],
        },
        {
            "step_num": "03",
            "slug": "guides/audit-an-agent-action",
            "kicker": "第三步 · 实操审计" if is_zh else "Step 3 · Practical Auditing",
            "nav_label": "审计智能体行动" if is_zh else "Audit an agent action",
            "time_display": "阅读用时：约 4 分钟 | 工作表演练：约 15 分钟（共计约 19 分钟）" if is_zh else "Reading: ~4 min | Worksheet practice: ~15 min (Total ~19 min)",
            "outcome": (
                "对照五项可观察证据要素审查外部工具调用，并在纯文本工作表中记录限定性结论。"
                if is_zh else
                "Verify external tool calls across five observable evidence elements and document bounded findings in a plaintext worksheet."
            ),
            "read_text": "阅读指南" if is_zh else "Read guide",
            "resources": [
                {
                    "title": "AgentDojo 安全基准" if is_zh else "AgentDojo",
                    "href": f"{route_href('resources', locale)}?q=AgentDojo",
                    "desc": "针对具备工具调用能力智能体的提示注入攻防测试环境。" if is_zh else "Benchmark environment for testing prompt injection and tool execution security boundaries.",
                },
                {
                    "title": "资源库：安全工具" if is_zh else "Catalog: Security Tools",
                    "href": f"{route_href('resources', locale)}?category=security&format=Tool",
                    "desc": "用于智能体工作流安全审计与防护的实用工具。" if is_zh else "Practical security auditing tools and scanners for agent workflows.",
                },
            ],
        },
    ]

    title = "学习" if is_zh else "Learn"
    eyebrow = "学习路径" if is_zh else "Learning Path"
    description = (
        "从核心概念起步，学会阅读评估报告，再动手练习审计工作表。"
        if is_zh else
        "Start with the concepts, learn to read an evaluation report, then try an audit worksheet."
    )
    time_label = "预估用时" if is_zh else "Estimated Time"
    outcome_label = "学习目标" if is_zh else "Learning Outcome"
    resources_label = "相关实践资源" if is_zh else "Practical Related Resources"

    # Render curated steps
    steps_html = []
    outline_items = []
    curated_slugs = set()
    for s in steps_data:
        slug = s["slug"]
        curated_slugs.add(slug)
        page = page_map.get(slug)
        if not page:
            continue

        step_id = f"step-{s['step_num']}"
        p_href = route_href(slug, locale)
        p_title = escape(page.get("title", s["nav_label"]))
        p_media = render_media(page, "index", p_href, priority=False)

        outline_items.append(
            f'<li><a href="#{step_id}"><span class="outline-num">{int(s["step_num"])}</span> {escape(s["nav_label"])}</a></li>'
        )

        res_items = []
        for r in s["resources"]:
            r_title = escape(r["title"])
            r_href = escape(r["href"])
            r_desc = escape(r["desc"])
            res_items.append(
                f'<li><a href="{r_href}">{r_title}</a>: <span class="step-res-desc">{r_desc}</span></li>'
            )
        res_list_html = "\n              ".join(res_items)

        step_card = f"""
        <li class="learning-step" id="{step_id}">
          <div class="step-num-col">
            <span class="step-num" aria-hidden="true">{s['step_num']}</span>
          </div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-kicker">{escape(s['kicker'])}</span>
              <h2 class="step-heading"><a href="{p_href}">{p_title}</a></h2>
            </div>
            <div class="step-time-box">
              <span class="step-time-label">{time_label}:</span>
              <span class="step-time-val">{escape(s['time_display'])}</span>
            </div>
            <div class="step-outcome">
              <strong class="step-outcome-label">{outcome_label}</strong>
              <p class="step-outcome-text">{escape(s['outcome'])}</p>
            </div>
            {p_media}
            <div class="step-link-wrap">
              <a href="{p_href}" class="step-read-link">{escape(s['read_text'])} &rarr;</a>
            </div>
            <div class="step-resources">
              <span class="step-resources-label">{resources_label}</span>
              <ul class="step-resources-list">
                {res_list_html}
              </ul>
            </div>
          </div>
        </li>"""
        steps_html.append(step_card)

    steps_markup = "\n".join(steps_html)

    # Additional reading section for any guides not in curated steps
    additional_guides = [
        p for p in pages
        if p.get("kind") in ("introduction", "guide") and p.get("slug") not in curated_slugs
    ]
    additional_section = ""
    if additional_guides:
        add_title = "延伸阅读与参考指南" if is_zh else "Additional Guides & Reference"
        add_desc = "未包含在核心三步路径中的其他实践指南与入门参考资料。" if is_zh else "Further practical guides and orienting materials beyond the core three-step path."
        published_prefix = "发布于 " if is_zh else "Published "
        read_more_text = "阅读全文 &rarr;" if is_zh else "Read article &rarr;"

        add_cards = []
        for p in sorted(additional_guides, key=lambda x: x.get("published", ""), reverse=True):
            p_slug = p["slug"]
            p_title = escape(p["title"])
            p_summary = escape(p.get("summary", ""))
            p_pub = escape(p.get("published", ""))
            p_kind = _kind_label(p.get("kind", ""), locale)
            p_topics = "".join(f'<span class="tag">{escape(t)}</span>' for t in p.get("topics", []))
            p_href = route_href(p_slug, locale)
            p_media = render_media(p, "index", p_href, priority=False)
            add_card = f"""
          <article class="article-card{' has-media' if p.get('_media') else ''}" data-kind="{escape(p.get('kind', ''))}">
            {p_media}
            <div class="article-card-copy">
              <div class="article-card-header">
                <span class="eyebrow">{escape(p_kind)}</span>
                <h2><a href="{p_href}">{p_title}</a></h2>
              </div>
              <p class="article-summary">{p_summary}</p>
              <div class="article-card-meta">
                <span class="date">{published_prefix}<time datetime="{p_pub}">{display_date(p_pub, locale)}</time></span>
                <div class="tags">{p_topics}</div>
              </div>
              <a href="{p_href}" class="article-read-link">{read_more_text}</a>
            </div>
          </article>"""
            add_cards.append(add_card)

        additional_section = f"""
      <section class="learning-additional" aria-labelledby="additional-guides-heading">
        <div class="learning-additional-header">
          <h2 id="additional-guides-heading">{escape(add_title)}</h2>
          <p>{escape(add_desc)}</p>
        </div>
        <div class="article-list">
          {"\n".join(add_cards)}
        </div>
      </section>"""

    # Outline and main content composition
    outline_html = ""
    path_html = ""
    empty_html = ""
    if steps_html:
        outline_label = "学习路径阶段" if is_zh else "Learning path stages"
        outline_html = f"""
      <nav class="learning-outline" aria-label="{outline_label}">
        <ol class="outline-list">
          {"\n          ".join(outline_items)}
        </ol>
      </nav>"""
        path_html = f"""
      <ol class="learning-path" aria-label="{escape(title)}">
        {steps_markup}
      </ol>"""
    elif not additional_guides:
        empty_html = f'<p class="empty-state">{"暂无已发布的学习指南。" if is_zh else "No guides published yet."}</p>'

    selections_bridge = ("\n" + render_learn_selections_bridge(locale=locale)) if has_selections else ""

    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">{escape(eyebrow)}</span>
        <h1>{escape(title)}</h1>
        <p class="page-lead">{escape(description)}</p>
      </header>{selections_bridge}{outline_html}{path_html}{additional_section}{empty_html}
    </div>
"""

    return render_html_page(
        title=title,
        description=description,
        canonical_url=canonical_for(base_url, "learn", locale),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="learn" if locale == "en" else "zh/learn",
        og_type="website",
        locale=locale,
        has_zh=has_zh,
    )


def _render_article_list_index(
    *,
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
    title: str,
    description: str,
    eyebrow: str,
    slug: str,
    empty_msg: str,
    locale: str = "en",
    has_zh: bool = True,
    contextual_note: str = "",
    is_latest: bool = False,
) -> str:
    """Generic list-style index page for editorial article sections."""
    published_prefix = "发布于 " if locale == "zh" else "Published "
    announced_prefix = "公布于 " if locale == "zh" else "Announced "
    read_more_text = "阅读全文 &rarr;" if locale == "zh" else "Read article &rarr;"

    cards_html = []
    for p in sorted(pages, key=lambda x: x.get("published", ""), reverse=True):
        p_slug = p["slug"]
        p_title = escape(p["title"])
        p_summary = escape(p.get("summary", ""))
        p_pub = escape(p.get("published", ""))
        p_event = p.get("event_date", "")
        p_kind = _kind_label(p.get("kind", ""), locale)
        p_topics = "".join(f'<span class="tag">{escape(t)}</span>' for t in p.get("topics", []))
        event_bit = ""
        if p_event and p_event != p.get("published", ""):
            event_bit = f'<span class="date">{announced_prefix}<time datetime="{escape(p_event)}">{display_date(p_event, locale)}</time></span> '
        disclosure_bit = f'<p class="catalog-attribution">{escape(p["affiliation_disclosure"])}</p>' if p.get("kind") == "release" and p.get("affiliation_disclosure") else ""
        card = f"""
        <article class="article-card{' has-media' if p.get('_media') else ''}" data-kind="{escape(p.get('kind', ''))}">
          {render_media(p, 'index', route_href(p_slug, locale), priority=not cards_html)}
          <div class="article-card-copy">
          <div class="article-card-header">
            <span class="eyebrow">{escape(p_kind)}</span>
            <h2><a href="{route_href(p_slug, locale)}">{p_title}</a></h2>
          </div>
          <p class="article-summary">{p_summary}</p>
          <div class="article-card-meta">
            <span class="date">{published_prefix}<time datetime="{p_pub}">{display_date(p_pub, locale)}</time></span>{event_bit}
            <div class="tags">{p_topics}</div>
          </div>
          {disclosure_bit}
          <a href="{route_href(p_slug, locale)}" class="article-read-link">{read_more_text}</a>
          </div>
        </article>"""
        cards_html.append(card)
    cards_markup = "\n".join(cards_html) if cards_html else f'<p class="empty-state">{empty_msg}</p>'

    filter_controls_html = ""
    if is_latest:
        filter_label = "分类：" if locale == "zh" else "Category:"
        filter_aria = "按类别筛选内容" if locale == "zh" else "Filter articles by category"
        count_text = f"显示全部 {len(pages)} 篇内容" if locale == "zh" else f"Showing all {len(pages)} items"
        no_res_text = "未找到符合该分类的内容。" if locale == "zh" else "No articles found matching this category."
        reset_text = "显示全部内容" if locale == "zh" else "Show all articles"

        all_label = "全部" if locale == "zh" else "All"
        news_label = "新闻简讯" if locale == "zh" else "News"
        analysis_label = "深度解读" if locale == "zh" else "Analysis"
        guides_label = "实践指南" if locale == "zh" else "Guides"
        releases_label = "动态发布" if locale == "zh" else "Releases"

        filter_controls_html = f"""
      <div id="latest-controls" class="latest-filters-bar" hidden>
        <div class="category-filters" role="group" aria-label="{filter_aria}">
          <span class="filter-group-label">{filter_label}</span>
          <button type="button" class="filter-button is-active" data-kind="all" data-filter="all" aria-pressed="true">{all_label}</button>
          <button type="button" class="filter-button" data-kind="news" data-filter="news" aria-pressed="false">{news_label}</button>
          <button type="button" class="filter-button" data-kind="feature" data-filter="feature" aria-pressed="false">{analysis_label}</button>
          <button type="button" class="filter-button" data-kind="guide" data-filter="guide" aria-pressed="false">{guides_label}</button>
          <button type="button" class="filter-button" data-kind="release" data-filter="release" aria-pressed="false">{releases_label}</button>
        </div>
        <div id="latest-count" role="status" aria-live="polite" class="latest-count">{count_text}</div>
        <div id="latest-no-results" class="empty-state" hidden>
          <p>{no_res_text}</p>
          <button type="button" class="filter-button is-active" data-action="reset-latest">{reset_text}</button>
        </div>
      </div>"""

    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">{escape(eyebrow)}</span>
        <h1>{escape(title)}</h1>
        <p class="page-lead">{escape(description)}</p>
        {contextual_note}
      </header>
      {filter_controls_html}
      <div class="article-list">
        {cards_markup}
      </div>
    </div>
"""
    return render_html_page(
        title=title,
        description=description,
        canonical_url=canonical_for(base_url, slug, locale),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug=slug if locale == "en" else f"zh/{slug}",
        og_type="website",
        locale=locale,
        has_zh=has_zh,
    )


def build_article_page(
    page: Dict[str, Any],
    site_data: Dict[str, Any],
    body_html: str,
    base_url: str,
    related_pages: Optional[List[Dict[str, Any]]] = None,
    locale: str = "en",
    has_zh: bool = True,
) -> str:
    """Generates an individual article / content page."""
    slug = page["slug"]
    title = page["title"]
    summary = page.get("summary", "")
    author = page.get("author", "Audit Commons")
    published = page.get("published", "")
    updated = page.get("updated", "")
    kind = page.get("kind", "article")
    event_date = page.get("event_date", "")
    topics = page.get("topics", [])
    source_urls = page.get("source_urls", [])
    disclosure = page.get("affiliation_disclosure", "")

    canonical_url = canonical_for(base_url, slug, locale)

    if locale == "zh":
        section_name, section_slug = {
            "news": ("最新", "latest"), "release": ("最新", "latest"),
            "feature": ("最新", "latest"), "guide": ("学习", "learn"),
            "introduction": ("学习", "learn"), "about": ("关于", "about"),
        }[kind]
        home_label = "首页"
        nav_label = "路径导航"
    else:
        section_name, section_slug = {
            "news": ("Latest", "latest"), "release": ("Latest", "latest"),
            "feature": ("Latest", "latest"), "guide": ("Learn", "learn"),
            "introduction": ("Learn", "learn"), "about": ("About", "about"),
        }[kind]
        home_label = "Home"
        nav_label = "Breadcrumb"

    trail = [(home_label, canonical_for(base_url, "", locale))]
    if section_slug != slug:
        trail.append((section_name, canonical_for(base_url, section_slug, locale)))
    trail.append((title, canonical_url))
    crumbs = "".join(
        f'<li><a href="{escape(urlparse(url).path)}">{escape(label)}</a></li>'
        if i < len(trail) - 1 else f'<li aria-current="page">{escape(label)}</li>'
        for i, (label, url) in enumerate(trail)
    )
    breadcrumbs = f'<nav class="breadcrumbs" aria-label="{nav_label}"><ol>{crumbs}</ol></nav>'
    breadcrumb_data = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": label, "item": url}
            for i, (label, url) in enumerate(trail, 1)
        ],
    }
    extra_meta = f'<script type="application/ld+json">{serialize_json_ld(breadcrumb_data)}</script>'

    related_html = ""
    if related_pages:
        heading = "延伸阅读" if locale == "zh" else "Continue reading"
        related_links = "".join(
            f'<li><a href="{route_href(p["slug"], locale)}">{escape(p["title"])}</a></li>'
            for p in related_pages
        )
        related_html = f'<section class="related-reading" aria-labelledby="related-reading"><h2 id="related-reading">{heading}</h2><ul>{related_links}</ul></section>'

    eyebrow_text = _kind_label(kind, locale)
    if locale == "en":
        eyebrow_text = {"guide": "Practical Guide", "release": "Field Update"}.get(kind, eyebrow_text)
    topics_markup = "".join(f'<span class="tag">{escape(t)}</span>' for t in topics)

    sources_section = ""
    if locale == "zh":
        source_heading = "原始来源" if kind in ("release", "news") else "相关资源"
    else:
        source_heading = "Primary sources" if kind in ("release", "news") else "Related resources"

    if source_urls:
        items = "".join(f'<li><a href="{escape(u)}">{escape(u)}</a></li>' for u in source_urls)
        sources_section = f"""
        <div class="meta-section">
          <h4>{source_heading}</h4>
          <ul class="source-list">{items}</ul>
        </div>"""

    disclosure_section = ""
    if disclosure:
        disc_heading = "关联与披露说明" if locale == "zh" else "Affiliation &amp; Disclosure"
        disclosure_section = f"""
        <div class="callout meta-disclosure">
          <h4>{disc_heading}</h4>
          <p>{escape(disclosure)}</p>
        </div>"""

    updated_markup = ""
    if updated and updated != published:
        upd_label = "更新日期" if locale == "zh" else "Updated"
        updated_markup = f"""
        <dt>{upd_label}</dt>
        <dd><time datetime="{escape(updated)}">{display_date(updated, locale)}</time></dd>"""

    event_date_markup = ""
    if event_date and event_date != published:
        ann_label = "公布日期" if locale == "zh" else "Announced"
        event_date_markup = f"""
        <dt>{ann_label}</dt>
        <dd><time datetime="{escape(event_date)}">{display_date(event_date, locale)}</time></dd>"""

    header_meta = ""
    if kind != "about":
        if locale == "zh":
            event_text = f' &middot; 公布于 <time datetime="{escape(event_date)}">{display_date(event_date, locale)}</time>' if event_date else ""
            header_meta = f'<p class="article-header-meta">文 / <a href="{route_href("about", locale)}">{escape(author)}</a> &middot; 发布于 <time datetime="{escape(published)}">{display_date(published, locale)}</time>{event_text}</p>'
        else:
            event_text = f' &middot; Announced <time datetime="{escape(event_date)}">{display_date(event_date, locale)}</time>' if event_date else ""
            header_meta = f'<p class="article-header-meta">By <a href="{route_href("about", locale)}">{escape(author)}</a> &middot; Published <time datetime="{escape(published)}">{display_date(published, locale)}</time>{event_text}</p>'

    aside_heading = "文档信息" if locale == "zh" else "Document Details"
    aside_type = "类型" if locale == "zh" else "Type"
    aside_author = "编辑署名" if locale == "zh" else "Editorial Identity"
    aside_pub = "发布日期" if locale == "zh" else "Published"
    aside_topics = "主题" if locale == "zh" else "Topics"

    # Run HTML-aware navigation link localizer
    localized_body_content = localize_body_html(body_html, locale)

    body_content = f"""
    <div class="container">
      <header class="page-header">
        {breadcrumbs}
        <span class="eyebrow">{escape(eyebrow_text)}</span>
        <h1>{escape(title)}</h1>
        {header_meta}
        <p class="page-lead">{escape(summary)}</p>
      </header>

      <div class="article-layout">
        <article class="article-body">
          {render_media(page, 'article', priority=True)}
          {localized_body_content}
          {related_html}
          {build_follow_section(locale) if kind != 'about' else ''}
        </article>

        <aside class="article-aside">
          <div class="article-meta">
            <h3>{aside_heading}</h3>
            <dl class="meta-list">
              <dt>{aside_type}</dt>
              <dd>{escape(eyebrow_text)}</dd>
              <dt>{aside_author}</dt>
              <dd>{escape(author)}</dd>
              <dt>{aside_pub}</dt>
              <dd><time datetime="{escape(published)}">{display_date(published, locale)}</time></dd>
              {event_date_markup}
              {updated_markup}
            </dl>

            {f'<div class="meta-section"><h4>{aside_topics}</h4><div class="tags">{topics_markup}</div></div>' if topics_markup else ''}
            {disclosure_section}
            {sources_section}
          </div>
        </aside>
      </div>
    </div>
"""

    og_type = "article" if kind != "about" else "website"
    json_ld: Dict[str, Any]
    if kind != "about":
        json_ld = {
            "@context": "https://schema.org",
            "@type": "NewsArticle" if kind == "news" else "Article",
            "@id": canonical_url + "#article",
            "url": canonical_url,
            "inLanguage": LOCALE_LANG.get(locale, "en"),
            "isPartOf": {"@id": canonical_for(base_url, "", locale) + "#website"},
            "articleSection": section_name,
            "keywords": topics,
            "citation": source_urls,
            "isAccessibleForFree": True,
            "headline": title,
            "description": summary,
            "author": publication_identity(site_data, base_url, locale),
            "publisher": publication_identity(site_data, base_url, locale),
            "datePublished": published,
            "dateModified": updated or published,
            "mainEntityOfPage": canonical_url,
        }
    else:
        json_ld = {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "inLanguage": LOCALE_LANG.get(locale, "en"),
            "mainEntity": publication_identity(site_data, base_url, locale),
            "name": title,
            "description": summary,
            "url": canonical_url,
        }

    if media := page.get('_media'):
        json_ld['image'] = {
            '@type': 'ImageObject', 'url': base_url.rstrip('/') + media['src'],
            'width': media['width'], 'height': media['height'],
            'caption': media['caption'], 'creditText': media['credit'],
            'license': media['license_url'],
        }

    return render_html_page(
        title=title,
        description=summary,
        canonical_url=canonical_url,
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug=slug if locale == "en" else f"zh/{slug}",
        og_type=og_type,
        extra_meta=extra_meta,
        json_ld=json_ld,
        social_image=page.get('_media'),
        locale=locale,
        has_zh=has_zh,
    )


def build_404_page(site_data: Dict[str, Any], base_url: str, locale: str = "en", has_zh: bool = True) -> str:
    """Generates the usable 404 error page (never indexed in sitemap)."""
    if locale == "zh":
        title = "页面未找到"
        description = "在 Audit Commons 上未找到您所请求的页面。"
        eyebrow = "404 错误"
        heading = "页面未找到"
        lead = "在 Audit Commons 上未找到您所请求的页面。"
        body_content = f"""
    <div class="container">
      <header class="page-header error-header">
        <span class="eyebrow">{eyebrow}</span>
        <h1>{heading}</h1>
        <p class="page-lead">{lead}</p>
      </header>

      <div class="empty-state error-content">
        <p>该页面可能已被移动，或您输入的网址有误。您可以直接访问以下主要栏目：</p>
        <ul class="error-nav-list">
          <li><a href="/zh/">首页</a>：网站发布主页</li>
          <li><a href="/zh/latest/">最新</a>：最新文章与新闻简讯</li>
          <li><a href="/zh/latest/?kind=feature">深度解读</a>：研究深度解读与分析</li>
          <li><a href="/zh/learn/">学习</a>：入门导读、实践指南与实操示例</li>
          <li><a href="/zh/resources/">资源</a>：基准评测、测试沙盒与规范标准目录</li>
          <li><a href="/zh/about/">关于</a>：刊发范围、维护者披露与贡献说明</li>
        </ul>
      </div>
    </div>
"""
    else:
        title = "Page Not Found"
        description = "The requested page could not be found on Audit Commons."
        eyebrow = "Error 404"
        heading = "Page Not Found"
        lead = "We could not find this page on Audit Commons."
        body_content = f"""
    <div class="container">
      <header class="page-header error-header">
        <span class="eyebrow">{eyebrow}</span>
        <h1>{heading}</h1>
        <p class="page-lead">{lead}</p>
      </header>

      <div class="empty-state error-content">
        <p>The page may have moved or the URL may contain a typographical error. You can navigate directly to one of the primary sections below:</p>
        <ul class="error-nav-list">
          <li><a href="/">Home</a>: The publication front page</li>
          <li><a href="/latest/">Latest</a>: Recent articles and news briefs</li>
          <li><a href="/latest/?kind=feature">Analysis</a>: Research explainers and analysis</li>
          <li><a href="/learn/">Learn</a>: Introductions, guides, and worked examples</li>
          <li><a href="/resources/">Resources</a>: Searchable directory of benchmarks, sandboxes, and specifications</li>
          <li><a href="/about/">About</a>: Scope, maintainer disclosures, and contributions</li>
        </ul>
      </div>
    </div>
"""

    return render_html_page(
        title=title,
        description=description,
        canonical_url=canonical_for(base_url, "404.html", locale),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="404" if locale == "en" else "zh/404",
        og_type="website",
        is_404=True,
        locale=locale,
        has_zh=has_zh,
    )


def build_sitemap(routes: Dict[str, str], base_url: str) -> str:
    """
    Generates sitemap.xml for public routes.
    Explicitly excludes 404.html and any localized 404 pages.
    """
    clean_base = base_url.rstrip("/")
    url_elements = []

    for route, modified in routes.items():
        if route.endswith("404.html"):
            continue
        clean_route = route.strip("/")
        loc = f"{clean_base}/" if not clean_route else f"{clean_base}/{clean_route}/"
        priority = "1.0" if clean_route in ("", "zh") else "0.8"
        entry = f"""  <url>
    <loc>{escape(loc)}</loc>
    <lastmod>{escape(modified)}</lastmod>
    <priority>{priority}</priority>
  </url>"""
        url_elements.append(entry)

    urls_markup = "\n".join(url_elements)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_markup}
</urlset>
"""


class AbsolutizeHTMLParser(HTMLParser):
    """
    Resolves relative, root-relative, and fragment URLs in HTML markup to absolute URLs.
    URL-bearing attributes href, src, and poster are resolved against base_url.
    srcset candidate URLs are split and individually resolved against base_url.
    All attributes are safely re-escaped with proper quote and entity handling.
    Void tags (img, hr, br, etc.) are emitted without closing tags per HTML5.
    Other attributes (such as action, formaction, cite, data-*) are passed through unchanged;
    Audit Commons article HTML bodies do not contain forms, embeds, or video/audio constructs.
    """
    URL_ATTRS = {"href", "src", "poster"}
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=False)
        self.base_url = base_url
        self.pieces: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_strs = []
        for name, val in attrs:
            if val is not None:
                lower_name = name.lower()
                if lower_name in self.URL_ATTRS:
                    val_clean = val.strip()
                    if val_clean.lower().startswith(("mailto:", "tel:", "javascript:")):
                        resolved = val
                    else:
                        resolved = urljoin(self.base_url, val)
                    attr_strs.append(f'{name}="{html.escape(resolved, quote=True)}"')
                elif lower_name == "srcset":
                    candidates = []
                    for cand in val.split(","):
                        parts = cand.strip().split(None, 1)
                        if parts:
                            u = parts[0]
                            if not u.lower().startswith(("mailto:", "tel:", "javascript:", "data:")):
                                u = urljoin(self.base_url, u)
                            cand_res = u if len(parts) == 1 else f"{u} {parts[1]}"
                            candidates.append(cand_res)
                    resolved = ", ".join(candidates)
                    attr_strs.append(f'{name}="{html.escape(resolved, quote=True)}"')
                else:
                    attr_strs.append(f'{name}="{html.escape(val, quote=True)}"')
            else:
                attr_strs.append(name)
        attr_str = (" " + " ".join(attr_strs)) if attr_strs else ""
        self.pieces.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() not in self.VOID_TAGS:
            self.pieces.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.pieces.append(data)

    def handle_entityref(self, name: str) -> None:
        self.pieces.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.pieces.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.pieces.append(f"<!--{data}-->")

    def get_html(self) -> str:
        return "".join(self.pieces)


def absolutize_html_urls(html_content: str, base_url: str) -> str:
    """Safely absolutize all URL-bearing attributes in an HTML snippet using HTMLParser."""
    parser = AbsolutizeHTMLParser(base_url)
    parser.feed(html_content)
    return parser.get_html()


def build_atom_feed(
    site_data: Dict[str, Any],
    feed_pages: List[Dict[str, Any]],
    base_url: str,
    locale: str = "en",
    content_dir: Optional[Path] = None,
) -> str:
    """
    Generates an Atom 1.0 feed (/feed.xml or /zh/feed.xml).
    Entries link canonical update URLs and deliver complete article HTML bodies,
    lead editorial figures with caption/credit, primary sources, and article permalinks.
    All relative/fragment URLs are resolved to absolute URLs against canonical item URLs.
    """
    clean_base = base_url.rstrip("/")
    if locale == "zh":
        site_name = escape(f"{site_data.get('name', 'Audit Commons')} (中文)")
        site_tagline = escape("关于 AI 审计的新闻、深度分析与实践学习。")
        feed_url = f"{clean_base}/zh/feed.xml"
        site_url = f"{clean_base}/zh/"
        read_more_text = "在 Audit Commons 阅读全文"
    else:
        site_name = escape(site_data.get("name", "Audit Commons"))
        site_tagline = escape(site_data.get("tagline", "Research, tools, and community for AI auditing."))
        feed_url = f"{clean_base}/feed.xml"
        site_url = f"{clean_base}/"
        read_more_text = "Read complete article at Audit Commons"

    dates = [p.get("updated") or p.get("published") for p in feed_pages if p.get("published")]
    feed_updated = max(dates) if dates else "2026-09-15"

    entries_xml = []
    for p in feed_pages:
        slug = p["slug"]
        title = escape(p["title"])
        summary = escape(p.get("summary", ""))
        author = escape(p.get("author", "Audit Commons"))
        published = p.get("published", "2026-09-15")
        updated = p.get("updated") or published
        item_canonical = canonical_for(base_url, slug, locale)
        source_urls = p.get("source_urls", [])

        sources_html = ""
        if source_urls:
            s_list = "".join(f'<li><a href="{escape(u)}">{escape(u)}</a></li>' for u in source_urls)
            source_label = "原始来源" if locale == "zh" and p.get("kind") in ("release", "news") else (
                "相关资源" if locale == "zh" else (
                    "Primary sources" if p.get("kind") in ("release", "news") else "Related resources"
                )
            )
            sources_html = f"<p><strong>{source_label}:</strong></p><ul>{s_list}</ul>"

        # Resolve body HTML
        body_html = p.get("_body_html")
        if body_html is None and content_dir is not None:
            bf = p.get("body_file")
            if bf:
                bf_path = content_dir / bf
                if bf_path.is_file():
                    body_html = bf_path.read_text(encoding="utf-8")
        if body_html is None:
            body_html = ""

        # Localize internal links if Chinese locale
        body_content = localize_body_html(body_html, locale)

        # Assigned editorial lead figure with caption and credit
        media_html = render_media(p, "article")

        entry_parts = [f"<p>{summary}</p>"]
        if media_html:
            entry_parts.append(media_html)
        if body_content:
            entry_parts.append(body_content)
        if sources_html:
            entry_parts.append(sources_html)
        disclosure = p.get("affiliation_disclosure")
        if disclosure:
            disclosure_label = "关联与披露说明" if locale == "zh" else "Affiliation &amp; Disclosure"
            entry_parts.append(f'<h2>{disclosure_label}</h2><p>{escape(disclosure)}</p>')
        entry_parts.append(f'<p><a href="{item_canonical}">{read_more_text}</a></p>')

        raw_combined_html = "\n".join(entry_parts)
        absolutized_html = absolutize_html_urls(raw_combined_html, item_canonical)
        entry_content = html.escape(absolutized_html)

        entry = f"""  <entry>
    <title>{title}</title>
    <link href="{escape(item_canonical)}" rel="alternate" type="text/html"/>
    <id>{escape(item_canonical)}</id>
    <published>{published}T00:00:00Z</published>
    <updated>{updated}T00:00:00Z</updated>
    <author>
      <name>{author}</name>
    </author>
    <summary type="text">{summary}</summary>
    <content type="html">{entry_content}</content>
  </entry>"""
        entries_xml.append(entry)

    entries_markup = "\n".join(entries_xml)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{site_name}</title>
  <subtitle>{site_tagline}</subtitle>
  <link href="{feed_url}" rel="self" type="application/atom+xml"/>
  <link href="{site_url}" rel="alternate" type="text/html"/>
  <id>{feed_url}</id>
  <updated>{feed_updated}T00:00:00Z</updated>
  <author>
    <name>{site_name}</name>
  </author>
{entries_markup}
</feed>
"""


def build_robots_txt(base_url: str) -> str:
    """Generates robots.txt referencing canonical sitemap."""
    clean_base = base_url.rstrip("/")
    return f"""User-agent: *
Allow: /

Sitemap: {clean_base}/sitemap.xml
"""


def copy_assets_safely(assets_dir: Path, output_dir: Path) -> None:
    """
    Safely copies only allowed static assets into _site/assets/ and key root assets.
    Never copies arbitrary repo files or scripts.
    """
    out_assets = output_dir / "assets"
    out_assets.mkdir(parents=True, exist_ok=True)

    if assets_dir.exists() and assets_dir.is_dir():
        for item in assets_dir.iterdir():
            if item.is_file():
                dest = out_assets / item.name
                shutil.copy2(item, dest)

        fav = assets_dir / "favicon.svg"
        if fav.exists():
            shutil.copy2(fav, output_dir / "favicon.svg")

        soc_svg = assets_dir / "social-preview.svg"
        if soc_svg.exists():
            shutil.copy2(soc_svg, output_dir / "social-preview.svg")

    # Always generate .nojekyll in output directory
    (output_dir / ".nojekyll").touch()


def build_site(
    repo_root: Path,
    content_dir: Path,
    output_dir: Path,
    assets_dir: Path,
    base_url_override: Optional[str] = None,
) -> None:
    """Orchestrates complete validation, rendering, and writing of the site."""
    # 2. Validate and load site.json
    site_file = content_dir / "site.json"
    if not site_file.exists():
        raise FileNotFoundError(f"Missing required site metadata: {site_file}")
    with open(site_file, "r", encoding="utf-8") as f:
        try:
            site_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {site_file}: {e}") from e

    # Determine and validate effective base URL (origin only)
    effective_base_url = validate_base_url(base_url_override or site_data.get("base_url"))
    style_file = assets_dir / "style.css"
    if style_file.is_file():
        style_version = hashlib.sha256(style_file.read_bytes()).hexdigest()[:12]
        site_data["_style_href"] = f"/assets/style.css?v={style_version}"

    # 3. Validate and load pages.json
    pages_file = content_dir / "pages.json"
    if not pages_file.exists():
        raise FileNotFoundError(f"Missing required pages registry: {pages_file}")
    with open(pages_file, "r", encoding="utf-8") as f:
        try:
            pages = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {pages_file}: {e}") from e

    if not isinstance(pages, list):
        raise ValueError("content/pages.json must be a JSON list of page records")

    # Keep a deep copy of raw pages for overlay verification before media binding
    raw_pages_for_hash = copy.deepcopy(pages)

    # Validate page schemas & dates
    seen_slugs = set()
    for idx, page in enumerate(pages):
        slug = page.get("slug")
        if not slug:
            raise ValueError(f"Page record #{idx} missing required 'slug'")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*", slug):
            raise ValueError(f"Invalid page slug: {slug!r}")
        if slug.split('/')[0] in {'assets', 'resources', 'index', '404', 'zh'} or slug in {'guides', 'updates', 'latest', 'features', 'learn'}:
            raise ValueError(f"Page slug collides with a generated route: {slug}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate slug detected in pages.json: '{slug}'")
        seen_slugs.add(slug)

        for req_field in ("title", "summary", "author", "published", "kind", "body_file"):
            if req_field not in page:
                raise ValueError(f"Page '{slug}' missing required field '{req_field}'")

        if page["kind"] not in {"introduction", "guide", "release", "about", "news", "feature"}:
            raise ValueError(f"Page '{slug}' has unsupported kind: {page['kind']}")
        prefix = {"news": "news/", "feature": "features/", "guide": "guides/", "release": "updates/"}.get(page["kind"])
        if prefix and not slug.startswith(prefix):
            raise ValueError(f"Page '{slug}' of kind '{page['kind']}' must live under '{prefix}'")

        parse_date(page["published"])
        if page["kind"] in {"news", "release"} and not page.get("event_date"):
            raise ValueError(f"News or release '{slug}' must identify its event_date")
        if page.get("updated"):
            parse_date(page["updated"])
        if page.get("event_date"):
            parse_date(page["event_date"])

        body_file = (content_dir / page["body_file"]).resolve()
        if not body_file.is_relative_to(content_dir.resolve()) or body_file.suffix != '.html':
            raise ValueError(f"Body path must be HTML inside content: {page['body_file']}")
        if not body_file.is_file():
            raise FileNotFoundError(f"Body file not found for page '{slug}': {body_file}")

    page_lookup = {p["slug"]: p for p in pages}
    for page in pages:
        related = page.get("related_slugs", [])
        if not isinstance(related, list) or any(not isinstance(slug, str) for slug in related):
            raise ValueError(f"related_slugs must be a list of slugs: {page['slug']}")
        if len(related) != len(set(related)) or any(slug not in page_lookup or slug == page["slug"] for slug in related):
            raise ValueError(f"Unknown, duplicate or self-related article: {page['slug']}")

    # 4. Validate and load resources.json
    resources_file = content_dir / "resources.json"
    if not resources_file.exists():
        raise FileNotFoundError(f"Missing required resources registry: {resources_file}")
    with open(resources_file, "r", encoding="utf-8") as f:
        try:
            resources = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {resources_file}: {e}") from e

    if not isinstance(resources, list):
        raise ValueError("content/resources.json must be a JSON list of resource records")

    raw_resources_for_hash = copy.deepcopy(resources)

    # Validate resource records
    seen_res_ids = set()
    valid_categories = {"Evaluation", "Security", "Governance", "Reading", "Tools"}
    valid_relationships = {"External resource", "Maintainer project"}
    for idx, res in enumerate(resources):
        res_id = res.get("id")
        if not res_id:
            raise ValueError(f"Resource record #{idx} missing required 'id'")
        if res_id in seen_res_ids:
            raise ValueError(f"Duplicate resource ID detected: '{res_id}'")
        seen_res_ids.add(res_id)

        for req_field in ("name", "category", "summary", "url", "owner", "relationship", "checked"):
            if req_field not in res:
                raise ValueError(f"Resource '{res_id}' missing required field '{req_field}'")

        if res["category"] not in valid_categories:
            raise ValueError(f"Resource '{res_id}' has invalid category '{res['category']}'. Expected one of {valid_categories}")

        if res["relationship"] not in valid_relationships:
            raise ValueError(f"Resource '{res_id}' has invalid relationship '{res['relationship']}'")

        parse_date(res["checked"])

    # 4b. Validate Chinese translation overlays if content/zh directory exists
    # Validates overlay keys/types, paths, coverage, and source_sha256 BEFORE touching output
    zh_overlays = validate_translation_overlays(content_dir, raw_pages_for_hash, raw_resources_for_hash)
    if zh_overlays is not None:
        for resource in resources:
            resource["_search_summary"] = zh_overlays["resources"][resource["id"]]["summary"]

    # 4c. Validate and load reading-lists.json if present in content_dir
    reading_lists_file = content_dir / "reading-lists.json"
    reading_lists: Optional[List[Dict[str, Any]]] = None
    if reading_lists_file.exists():
        reading_lists = load_reading_lists(content_dir, resources)

    media_files = bind_media(content_dir, assets_dir, pages, resources)
    prepare_output_directory(output_dir, repo_root, content_dir, assets_dir)

    # 5. Copy static assets
    copy_assets_safely(assets_dir, output_dir)
    for source in media_files:
        destination = output_dir / 'assets' / source.relative_to(assets_dir.resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    has_zh = (zh_overlays is not None)

    # 6. Render English Home Page (/)
    home_html = build_homepage(site_data, pages, resources, effective_base_url, locale="en", has_zh=has_zh)
    (output_dir / "index.html").write_text(home_html, encoding="utf-8")

    # 7. Render English Resources Page (/resources/)
    res_html = build_resources_page(site_data, resources, effective_base_url, locale="en", has_zh=has_zh, reading_lists=reading_lists)
    res_dir = output_dir / "resources"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "index.html").write_text(res_html, encoding="utf-8")

    # 8. Render English Guides Index (/guides/)
    guides_html = build_guides_index(site_data, pages, effective_base_url, locale="en", has_zh=has_zh)
    guides_dir = output_dir / "guides"
    guides_dir.mkdir(parents=True, exist_ok=True)
    (guides_dir / "index.html").write_text(guides_html, encoding="utf-8")

    # 9. Render English Updates Index (/updates/)
    updates_html = build_updates_index(site_data, pages, effective_base_url, locale="en", has_zh=has_zh)
    updates_dir = output_dir / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    (updates_dir / "index.html").write_text(updates_html, encoding="utf-8")

    # 9b. English editorial section indices
    latest_html = build_latest_index(site_data, pages, effective_base_url, locale="en", has_zh=has_zh)
    latest_dir = output_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "index.html").write_text(latest_html, encoding="utf-8")

    features_html = build_features_index(site_data, pages, effective_base_url, locale="en", has_zh=has_zh)
    features_dir = output_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "index.html").write_text(features_html, encoding="utf-8")

    learn_html_page = build_learn_index(site_data, pages, effective_base_url, locale="en", has_zh=has_zh, has_selections=(reading_lists is not None))
    learn_dir = output_dir / "learn"
    learn_dir.mkdir(parents=True, exist_ok=True)
    (learn_dir / "index.html").write_text(learn_html_page, encoding="utf-8")

    # 10. Render English Individual Content Pages
    all_sitemap_routes = ["", "resources", "guides", "updates", "latest", "features", "learn"]
    for page in pages:
        slug = page["slug"].strip("/")
        body_file = content_dir / page["body_file"]
        body_html = body_file.read_text(encoding="utf-8")
        page["_body_html"] = body_html

        article_html = build_article_page(
            page, site_data, body_html, effective_base_url,
            [page_lookup[slug] for slug in page.get("related_slugs", [])],
            locale="en",
            has_zh=has_zh,
        )
        target_dir = output_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "index.html").write_text(article_html, encoding="utf-8")

        all_sitemap_routes.append(slug)

    # 11. Render English Usable 404 Page (/404.html)
    page_404_html = build_404_page(site_data, effective_base_url, locale="en", has_zh=has_zh)
    (output_dir / "404.html").write_text(page_404_html, encoding="utf-8")

    # 12. Render Chinese Edition (/zh/...) if translation overlays present
    if zh_overlays is not None:
        zh_dir = output_dir / "zh"
        zh_dir.mkdir(parents=True, exist_ok=True)

        manifest_data: Dict[str, Any] = {}
        if (content_dir / "media.json").exists():
            try:
                manifest_data = json.loads((content_dir / "media.json").read_text(encoding="utf-8"))
            except Exception:
                pass

        article_media_keys = manifest_data.get("articles", {})
        res_media_keys = manifest_data.get("resources", {})
        media_overlay = zh_overlays.get("media", {})

        # Localize page objects with overlay data
        zh_pages = []
        for p in pages:
            p_over = zh_overlays["pages"][p["slug"]]
            zh_p = apply_page_overlay(p, p_over)
            if "_media" in p:
                m_key = article_media_keys.get(p["slug"])
                zh_p["_media"] = apply_media_overlay(p["_media"], media_overlay.get(m_key, {}))
            zh_p["_body_html"] = zh_overlays["bodies"][p["slug"]]
            zh_pages.append(zh_p)

        zh_page_lookup = {p["slug"]: p for p in zh_pages}

        # Localize resource objects with overlay data
        zh_resources = []
        for r in resources:
            r_over = zh_overlays["resources"][r["id"]]
            zh_r = apply_resource_overlay(r, r_over)
            zh_r["_search_summary"] = r["summary"]
            if "_media" in r:
                m_key = res_media_keys.get(r["id"])
                zh_r["_media"] = apply_media_overlay(r["_media"], media_overlay.get(m_key, {}))
            zh_resources.append(zh_r)

        # 12a. Render Chinese Home Page (/zh/)
        zh_home_html = build_homepage(site_data, zh_pages, zh_resources, effective_base_url, locale="zh")
        (zh_dir / "index.html").write_text(zh_home_html, encoding="utf-8")
        all_sitemap_routes.append("zh")

        # 12b. Render Chinese Resources Page (/zh/resources/)
        zh_res_html = build_resources_page(site_data, zh_resources, effective_base_url, locale="zh", reading_lists=reading_lists)
        zh_res_dir = zh_dir / "resources"
        zh_res_dir.mkdir(parents=True, exist_ok=True)
        (zh_res_dir / "index.html").write_text(zh_res_html, encoding="utf-8")
        all_sitemap_routes.append("zh/resources")

        # 12c. Render Chinese Section Indices
        zh_guides_html = build_guides_index(site_data, zh_pages, effective_base_url, locale="zh")
        zh_guides_dir = zh_dir / "guides"
        zh_guides_dir.mkdir(parents=True, exist_ok=True)
        (zh_guides_dir / "index.html").write_text(zh_guides_html, encoding="utf-8")
        all_sitemap_routes.append("zh/guides")

        zh_updates_html = build_updates_index(site_data, zh_pages, effective_base_url, locale="zh")
        zh_updates_dir = zh_dir / "updates"
        zh_updates_dir.mkdir(parents=True, exist_ok=True)
        (zh_updates_dir / "index.html").write_text(zh_updates_html, encoding="utf-8")
        all_sitemap_routes.append("zh/updates")

        zh_latest_html = build_latest_index(site_data, zh_pages, effective_base_url, locale="zh")
        zh_latest_dir = zh_dir / "latest"
        zh_latest_dir.mkdir(parents=True, exist_ok=True)
        (zh_latest_dir / "index.html").write_text(zh_latest_html, encoding="utf-8")
        all_sitemap_routes.append("zh/latest")

        zh_features_html = build_features_index(site_data, zh_pages, effective_base_url, locale="zh")
        zh_features_dir = zh_dir / "features"
        zh_features_dir.mkdir(parents=True, exist_ok=True)
        (zh_features_dir / "index.html").write_text(zh_features_html, encoding="utf-8")
        all_sitemap_routes.append("zh/features")

        zh_learn_html = build_learn_index(site_data, zh_pages, effective_base_url, locale="zh", has_selections=(reading_lists is not None))
        zh_learn_dir = zh_dir / "learn"
        zh_learn_dir.mkdir(parents=True, exist_ok=True)
        (zh_learn_dir / "index.html").write_text(zh_learn_html, encoding="utf-8")
        all_sitemap_routes.append("zh/learn")

        # 12d. Render Chinese Individual Content Pages
        for zh_p in zh_pages:
            slug = zh_p["slug"].strip("/")
            body_html = zh_overlays["bodies"][slug]
            zh_article_html = build_article_page(
                zh_p, site_data, body_html, effective_base_url,
                [zh_page_lookup[s] for s in zh_p.get("related_slugs", [])],
                locale="zh",
            )
            zh_target_dir = zh_dir / slug
            zh_target_dir.mkdir(parents=True, exist_ok=True)
            (zh_target_dir / "index.html").write_text(zh_article_html, encoding="utf-8")
            all_sitemap_routes.append(f"zh/{slug}")

        # 12e. Render Chinese 404 (/zh/404.html)
        zh_404_html = build_404_page(site_data, effective_base_url, locale="zh")
        (zh_dir / "404.html").write_text(zh_404_html, encoding="utf-8")

        # 12f. Render Chinese Feed (/zh/feed.xml)
        zh_feed_pages = sorted([p for p in zh_pages if p.get("kind") != "about"], key=lambda p: p["published"], reverse=True)
        zh_feed_xml = build_atom_feed(site_data, zh_feed_pages, effective_base_url, locale="zh", content_dir=content_dir)
        (zh_dir / "feed.xml").write_text(zh_feed_xml, encoding="utf-8")

    # 13. Render Sitemap (/sitemap.xml) - Excludes 404 pages
    article_dates = {p['slug']: p.get('updated') or p['published'] for p in pages}
    latest_date = max([*article_dates.values(), *(r['checked'] for r in resources)])
    route_dates = {}
    for route in all_sitemap_routes:
        clean = route.removeprefix("zh/").removeprefix("zh")
        if clean in article_dates:
            route_dates[route] = article_dates[clean]
        elif clean == "resources":
            route_dates[route] = max((r['checked'] for r in resources), default=latest_date)
        elif clean == "guides":
            route_dates[route] = max((article_dates[p['slug']] for p in pages if p.get('kind') == 'guide' or p['slug'].startswith('guides/')), default=latest_date)
        elif clean == "updates":
            route_dates[route] = max((article_dates[p['slug']] for p in pages if p.get('kind') == 'release' or p['slug'].startswith('updates/')), default=latest_date)
        elif clean == "features":
            route_dates[route] = max((article_dates[p['slug']] for p in pages if p.get('kind') == 'feature' or p['slug'].startswith('features/')), default=latest_date)
        elif clean == "learn":
            route_dates[route] = max((article_dates[p['slug']] for p in pages if p.get('kind') in ('guide', 'introduction') or p['slug'].startswith('guides/')), default=latest_date)
        else:
            route_dates[route] = latest_date

    sitemap_xml = build_sitemap(route_dates, effective_base_url)
    (output_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

    # 14. Render Feed (/feed.xml) - Editorial articles (all kinds except about)
    feed_pages = sorted([p for p in pages if p.get("kind") != "about"], key=lambda p: p["published"], reverse=True)
    feed_xml = build_atom_feed(site_data, feed_pages, effective_base_url, locale="en", content_dir=content_dir)
    (output_dir / "feed.xml").write_text(feed_xml, encoding="utf-8")

    # 15. Render robots.txt
    robots_txt = build_robots_txt(effective_base_url)
    (output_dir / "robots.txt").write_text(robots_txt, encoding="utf-8")

    total_emitted = len(all_sitemap_routes) + (2 if zh_overlays else 1)
    print(f"Build complete. Emitted {total_emitted} routes and assets to {output_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Commons standard-library static generator")
    parser.add_argument("--content-dir", default="content", help="Directory containing site.json, pages.json, resources.json")
    parser.add_argument("--output-dir", default="_site", help="Destination directory for static site output")
    parser.add_argument("--assets-dir", default="assets", help="Directory containing style, scripts, and SVG assets")
    parser.add_argument("--base-url", default=None, help="Base URL override (origin only, e.g. https://auditcommons.org)")

    args = parser.parse_args()
    repo_root = Path.cwd().resolve()
    content_dir = (repo_root / args.content_dir).resolve()
    output_dir = (repo_root / args.output_dir).absolute()
    assets_dir = (repo_root / args.assets_dir).resolve()

    try:
        build_site(
            repo_root=repo_root,
            content_dir=content_dir,
            output_dir=output_dir,
            assets_dir=assets_dir,
            base_url_override=args.base_url,
        )
        return 0
    except Exception as e:
        sys.stderr.write(f"Build failed: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
