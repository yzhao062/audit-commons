#!/usr/bin/env python3
"""
Audit Commons Static Site Generator
Builds the complete Audit Commons field portal using standard Python 3.12 library only.
Generates the field portal from its editorial content and static assets.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


DEFAULT_BASE_URL = "https://auditcommons.org"
MARKER_FILENAME = ".generator-owned"
MARKER_SIGNATURE = "Audit Commons Static Site Generator Ownership Marker\nversion=1\n"

REQUIRED_NAV_ITEMS = [
    ("Latest", "/latest/"),
    ("Features", "/features/"),
    ("Learn", "/learn/"),
    ("Resources", "/resources/"),
    ("About", "/about/"),
]

# Slug prefixes that activate each nav item for sub-pages.
# Exact match takes priority; this map handles children of each section.
NAV_SLUG_PREFIXES: dict[str, list[str]] = {
    "latest":    ["latest", "news/", "updates/"],
    "features":  ["features/"],
    "learn":     ["learn", "guides/", "start-here"],
    "resources": ["resources"],
    "about":     ["about"],
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


def display_date(date_str: str) -> str:
    date = parse_date(date_str)
    return f"{date.day} {date.strftime('%b')} {date.year}"


def publication_identity(site_data: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    return {
        "@type": "Organization",
        "@id": canonical_for(base_url, "about") + "#publication",
        "name": site_data.get("name", "Audit Commons"),
        "url": canonical_for(base_url, "about"),
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


def canonical_for(base_url: str, slug: str) -> str:
    """
    Compute canonical URL for a given route slug.
    Consistently applies validated base_url origin rather than trusting stored values blindly.
    """
    base = base_url.rstrip("/")
    if not slug or slug == "/":
        return f"{base}/"
    if slug == "404.html" or slug == "/404.html":
        return f"{base}/404.html"
    clean_slug = slug.strip("/")
    return f"{base}/{clean_slug}/"


def route_href(slug: str) -> str:
    """Generate root-relative internal link for a route."""
    if not slug or slug == "/":
        return "/"
    if slug == "404.html" or slug == "/404.html":
        return "/404.html"
    clean_slug = slug.strip("/")
    return f"/{clean_slug}/"


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
) -> str:
    """Renders a complete HTML page matching the DOM and accessibility contract."""
    site_name = escape(site_data.get("name", "Audit Commons"))
    site_tagline = escape(site_data.get("tagline", "Research, tools, and community for AI auditing."))
    maintainer = site_data.get("maintainer", {})
    maintainer_name = escape(maintainer.get("name", "Yue Zhao"))
    maintainer_url = escape(maintainer.get("url", "https://viterbi-web.usc.edu/~yzhao010/"))

    escaped_title = escape(title)
    full_title = f"{escaped_title} | {site_name}" if title != site_name else site_name
    escaped_desc = escape(description)
    escaped_canonical = escape(canonical_url)
    social_png_url = f"{base_url.rstrip('/')}/assets/social-preview.png"

    # Robots tag: 404 must not be indexed
    robots_tag = '<meta name="robots" content="noindex, follow">' if is_404 else '<meta name="robots" content="index, follow, max-image-preview:large">'

    # Navigation links - use exact match + explicit prefix map to avoid substring collisions
    nav_links_html = []
    clean_current = current_slug.strip("/")
    for label, target in REQUIRED_NAV_ITEMS:
        target_slug = target.strip("/")
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


    # JSON-LD Structured Data with script breakout protection
    json_ld_html = ""
    if json_ld:
        safe_json_str = serialize_json_ld(json_ld)
        json_ld_html = f'<script type="application/ld+json">\n{safe_json_str}\n</script>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{full_title}</title>
  <meta name="description" content="{escaped_desc}">
  <link rel="canonical" href="{escaped_canonical}">
  {robots_tag}

  <!-- Open Graph / Facebook -->
  <meta property="og:site_name" content="{site_name}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:title" content="{full_title}">
  <meta property="og:description" content="{escaped_desc}">
  <meta property="og:url" content="{escaped_canonical}">
  <meta property="og:image" content="{social_png_url}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="{site_name}: {site_tagline}">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{full_title}">
  <meta name="twitter:description" content="{escaped_desc}">
  <meta name="twitter:image" content="{social_png_url}">

  <!-- Feed and Favicon -->
  <link rel="alternate" type="application/atom+xml" title="{site_name} Feed" href="{base_url.rstrip('/')}/feed.xml">
  <link rel="icon" href="/favicon.svg?v=graphite" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/style.css">
  <script src="/assets/site.js" defer></script>
  {extra_meta}
  {json_ld_html}
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="site-header">
    <div class="container header-container">
      <a href="/" class="brand" aria-label="Audit Commons Homepage">
        <img src="/assets/mark.svg?v=graphite" alt="" width="38" height="38" class="brand-icon">
        <span class="brand-text">
          <span class="brand-title">Audit Commons</span>
          <span class="brand-subtitle">AI Auditing</span>
        </span>
      </a>
      <nav class="site-nav" aria-label="Main Navigation">
        {nav_html}
      </nav>
    </div>
  </header>

  <main id="main" tabindex="-1">
{body_content}
  </main>

  <footer class="site-footer">
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
          <li><a href="/features/">Features</a></li>
          <li><a href="/learn/">Learn</a></li>
          <li><a href="/resources/">Resources</a></li>
          <li><a href="/about/">About</a></li>
        </ul>
      </div>

      <div class="footer-col footer-editorial">
        <h2>Connect</h2>
        <ul>
          <li><a href="/about/#contribute">Contribution Guide</a></li>
          <li><a href="/about/#corrections">Submit Corrections</a></li>
          <li><a href="/feed.xml">Atom Feed</a></li>
          <li><a href="https://github.com/yzhao062/audit-commons">Website source</a></li>
          <li><a href="https://github.com/yzhao062/awesome-auditable-ai">Awesome Auditable AI</a></li>
        </ul>
      </div>
    </div>
    <div class="container footer-bottom">
      <p class="footer-copy">&copy; 2026 Audit Commons. {site_tagline}</p>
    </div>
  </footer>
</body>
</html>"""


def _kind_label(kind: str) -> str:
    """Human-readable label for an article kind."""
    return {
        "introduction": "Orientation",
        "guide": "Guide",
        "release": "Release",
        "news": "News",
        "feature": "Feature",
        "about": "About",
    }.get(kind, "Article")


def build_homepage(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    resources: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Build editorial publication front page."""
    description = site_data.get("description", "Editorial coverage of AI auditing practice and research.")

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
        lp_label = _kind_label(lp_kind)
        lp_event_date = lp.get("event_date", "")
        lp_pub = lp.get("published", "")
        event_date_html = ""
        if lp_event_date and lp_event_date != lp_pub:
            event_date_html = f'<span class="pub-lead-event-date">Announced <time datetime="{escape(lp_event_date)}">{display_date(lp_event_date)}</time></span>'
        lead_html = f"""
    <section class="pub-lead-section" aria-labelledby="pub-lead-heading">
      <div class="pub-lead-meta">
        <span class="pub-lead-label">{escape(lp_label)}</span>
        {event_date_html}
        <span class="pub-lead-date">Published <time datetime="{escape(lp_pub)}">{display_date(lp_pub)}</time></span>
      </div>
      <h1 class="pub-lead-headline" id="pub-lead-heading">
        <a href="{route_href(lp['slug'])}">{escape(lp['title'])}</a>
      </h1>
      <p class="pub-lead-summary">{escape(lp.get('summary', ''))}</p>
      <p class="pub-lead-byline">By {escape(lp.get('author', 'Audit Commons'))}</p>
      <a class="pub-section-more" href="{route_href(lp['slug'])}">Read article &rarr;</a>
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
        item_label = _kind_label(item.get("kind", ""))
        item_event = item.get("event_date", "")
        item_pub = item.get("published", "")
        event_bit = ""
        if item_event and item_event != item_pub:
            event_bit = f'<span class="news-list-event">Announced <time datetime="{escape(item_event)}">{display_date(item_event)}</time></span> '
        disclosure_bit = f'<p class="news-list-disclosure">{escape(item.get("affiliation_disclosure", ""))}</p>' if item.get("kind") == "release" else ""
        news_rows += f"""
        <li class="news-list-item">
          <div class="news-list-meta"><span class="news-list-label">{escape(item_label)}</span>
          <span class="news-list-date">Published <time datetime="{escape(item_pub)}">{display_date(item_pub)}</time></span></div>
          <a class="news-list-title" href="{route_href(item['slug'])}">{escape(item['title'])}</a>
          {event_bit}{disclosure_bit}
        </li>"""

    news_section_html = ""
    if news_rows:
        news_section_html = f"""
    <section class="pub-news-section" aria-labelledby="news-list-heading">
      <div class="pub-section-bar">
        <h2 id="news-list-heading" class="pub-section-title">News &amp; Releases</h2>
        <a class="pub-section-more" href="/latest/">See all &rarr;</a>
      </div>
      <ul class="news-list">{news_rows}
      </ul>
    </section>"""

    # Learning articles (introduction + guide, not the lead)
    learn_items = [p for p in pages if p.get("kind") in ("introduction", "guide") and p is not lead_page]
    learn_entries = ""
    for p in learn_items:
        plabel = _kind_label(p.get("kind", ""))
        learn_entries += f"""
        <article class="reading-entry">
          <span class="eyebrow">{escape(plabel)}</span>
          <h3><a href="{route_href(p['slug'])}">{escape(p['title'])}</a></h3>
          <p>{escape(p.get('summary', ''))}</p>
        </article>"""

    learn_html = ""
    if learn_entries:
        learn_html = f"""
    <section class="pub-learn-section" aria-labelledby="learn-heading">
      <div class="pub-section-bar">
        <h2 id="learn-heading" class="pub-section-title">Learn</h2>
        <a class="pub-section-more" href="/learn/">All guides &rarr;</a>
      </div>
      <div class="pub-learning-grid">{learn_entries}</div>
    </section>"""

    # Selected resources (compact, top 6)
    res_rows = ""
    for res in resources[:6]:
        res_rows += f"""
        <li class="home-res-item">
          <a href="{escape(res['url'])}" class="home-res-link">{escape(res['name'])} <span aria-hidden="true">&nearr;</span></a>
          <span class="home-res-cat">{escape(res.get('category', ''))}{' · Maintainer project' if res.get('relationship') == 'Maintainer project' else ''}</span>
        </li>"""

    res_section_html = f"""
    <section class="pub-resources-section" aria-labelledby="res-heading">
      <div class="pub-section-bar">
        <h2 id="res-heading" class="pub-section-title">Selected Resources</h2>
        <a class="pub-section-more" href="/resources/">Full catalog &rarr;</a>
      </div>
      <ul class="home-res-list">{res_rows}
      </ul>
    </section>"""

    body_content = f"""
    <div class="container pub-home">
      <header class="pub-masthead">
        {'<p class="pub-site-name">AI auditing</p>' if lead_page else '<h1 class="pub-site-name">Audit Commons</h1>'}
        <p class="pub-scope">News, analysis &amp; learning</p>
      </header>

      <div class="pub-front-grid">
        <div class="pub-front-main">
          {lead_html}
        </div>
        <div class="pub-front-sidebar">
          {news_section_html}
        </div>
      </div>
      {learn_html}
      {res_section_html}
    </div>
"""
    json_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": canonical_for(base_url, "") + "#website",
        "inLanguage": "en",
        "name": site_data.get("name", "Audit Commons"),
        "url": f"{base_url.rstrip('/')}/",
        "description": description,
        "publisher": publication_identity(site_data, base_url),
    }
    return render_html_page(
        title="AI Auditing News, Guides & Resources",
        description=description,
        canonical_url=canonical_for(base_url, ""),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="",
        og_type="website",
        json_ld=json_ld,
    )



def build_resources_page(
    site_data: Dict[str, Any],
    resources: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Generates the searchable, filterable resource catalog."""
    categories = ["All", "Evaluation", "Security", "Governance", "Reading", "Tools"]

    filter_buttons_html = []
    for cat in categories:
        is_all = (cat == "All")
        pressed = "true" if is_all else "false"
        active_cls = " is-active" if is_all else ""
        btn = f'<button type="button" class="filter-button{active_cls}" data-filter="{cat}" aria-pressed="{pressed}">{cat}</button>'
        filter_buttons_html.append(btn)
    buttons_markup = "\n          ".join(filter_buttons_html)

    cards_html = []
    for r in resources:
        r_name = escape(r.get("name", ""))
        r_url = escape(r.get("url", "#"))
        r_cat = escape(r.get("category", ""))
        r_rel = escape(r.get("relationship", ""))
        r_sum = escape(r.get("summary", ""))
        r_owner = escape(r.get("owner", ""))
        r_checked = escape(r.get("checked", ""))
        source_urls = r.get("source_urls", [])

        search_terms = " ".join(str(r.get(key, "")) for key in ("name", "summary", "owner", "category", "relationship")).lower()

        sources_markup = ""
        if source_urls:
            items = "".join(f'<li><a href="{escape(u)}">{escape(u)}</a></li>' for u in source_urls)
            sources_markup = f"""
            <div class="resource-sources">
              <span class="sources-label">Primary sources:</span>
              <ul class="source-list">{items}</ul>
            </div>"""

        card = f"""
        <article class="resource-card" data-category="{r_cat}" data-search="{escape(search_terms)}">
          <div class="resource-card-header">
            <div class="tags">
              <span class="tag tag-category" data-category="{r_cat}">{r_cat}</span>
              <span class="tag tag-relationship">{r_rel}</span>
            </div>
            <h2><a href="{r_url}">{r_name} <span class="external-arrow" aria-hidden="true">&nearr;</span></a></h2>
          </div>
          <p class="resource-summary">{r_sum}</p>
          <div class="resource-meta">
            <span class="resource-owner"><strong>Owner:</strong> {r_owner}</span>
            <span class="resource-checked"><strong>Checked:</strong> <time datetime="{r_checked}">{r_checked}</time></span>
          </div>
          {sources_markup}
        </article>"""
        cards_html.append(card)

    total_count = len(resources)
    grid_html = "\n".join(cards_html)

    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">Catalog</span>
        <h1>Auditing Resources &amp; Toolchains</h1>
        <p class="page-lead">Curated benchmarks, risk frameworks, evaluation toolchains, and primary reference materials for AI auditing.</p>
      </header>

      <div id="resource-controls" hidden>
        <div class="resource-search-wrapper">
          <label for="resource-search" class="search-label">Search resources</label>
          <input type="search" id="resource-search" placeholder="Search by name, summary, owner, or topic..." autocomplete="off">
        </div>
        <div class="category-filters" role="group" aria-label="Filter by category">
          {buttons_markup}
        </div>
        <div id="resource-count" role="status" aria-live="polite">Showing all {total_count} resources</div>
      </div>

      <div id="no-results" class="empty-state" hidden>
        <p>No resources match your search or filter criteria.</p>
        <button type="button" data-action="reset" class="button button-secondary">Reset search</button>
      </div>

      <div class="resource-grid">
        {grid_html}
      </div>
    </div>
"""

    return render_html_page(
        title="Auditing Resources & Toolchains",
        description="Curated primary-source benchmarks, evaluation harnesses, and security sandboxes for AI auditing.",
        canonical_url=canonical_for(base_url, "resources"),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="resources",
        og_type="website",
    )


def build_guides_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    return _render_article_list_index(
        site_data=site_data, pages=[p for p in pages if p.get("kind") == "guide"],
        base_url=base_url, title="Guides", slug="guides", eyebrow="Learn",
        description="Practical guides to reading evidence and auditing AI systems.",
        empty_msg="No guides published yet.",
    )


def build_updates_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    return _render_article_list_index(
        site_data=site_data, pages=[p for p in pages if p.get("kind") == "release"],
        base_url=base_url, title="Releases", slug="updates", eyebrow="Latest",
        description="Release notes, sources, and maintainer disclosures.",
        empty_msg="No release notes published yet.",
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
) -> str:
    """Generic list-style index page for editorial article sections."""
    cards_html = []
    for p in sorted(pages, key=lambda x: x.get("published", ""), reverse=True):
        p_slug = p["slug"]
        p_title = escape(p["title"])
        p_summary = escape(p.get("summary", ""))
        p_pub = escape(p.get("published", ""))
        p_event = p.get("event_date", "")
        p_kind = _kind_label(p.get("kind", ""))
        p_topics = "".join(f'<span class="tag">{escape(t)}</span>' for t in p.get("topics", []))
        event_bit = ""
        if p_event and p_event != p.get("published", ""):
            event_bit = f'<span class="date">Announced <time datetime="{escape(p_event)}">{display_date(p_event)}</time></span> '
        disclosure_bit = f'<p class="catalog-attribution">{escape(p["affiliation_disclosure"])}</p>' if p.get("kind") == "release" and p.get("affiliation_disclosure") else ""
        card = f"""
        <article class="article-card">
          <div class="article-card-header">
            <span class="eyebrow">{escape(p_kind)}</span>
            <h2><a href="/{p_slug}/">{p_title}</a></h2>
          </div>
          <p class="article-summary">{p_summary}</p>
          <div class="article-card-meta">
            <span class="date">Published <time datetime="{p_pub}">{display_date(p_pub)}</time></span>{event_bit}
            <div class="tags">{p_topics}</div>
          </div>
          {disclosure_bit}
          <a href="/{p_slug}/" class="article-read-link">Read article &rarr;</a>
        </article>"""
        cards_html.append(card)
    cards_markup = "\n".join(cards_html) if cards_html else f'<p class="empty-state">{empty_msg}</p>'
    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">{escape(eyebrow)}</span>
        <h1>{escape(title)}</h1>
        <p class="page-lead">{escape(description)}</p>
      </header>
      <div class="article-list">
        {cards_markup}
      </div>
    </div>
"""
    return render_html_page(
        title=title,
        description=description,
        canonical_url=canonical_for(base_url, slug),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug=slug,
        og_type="website",
    )


def build_latest_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Generates /latest/ — all editorial additions sorted most-recent-first, excluding About."""
    editorial = [p for p in pages if p.get("kind") not in ("about",)]
    return _render_article_list_index(
        site_data=site_data,
        pages=editorial,
        base_url=base_url,
        title="Latest Additions",
        description="All editorial content added to Audit Commons, most recently published first.",
        eyebrow="Publication index",
        slug="latest",
        empty_msg="No articles published yet.",
    )


def build_features_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Generates /features/ — feature-kind articles."""
    features = [p for p in pages if p.get("kind") == "feature"]
    return _render_article_list_index(
        site_data=site_data,
        pages=features,
        base_url=base_url,
        title="Features",
        description="In-depth editorial features on AI auditing research, practice, and policy.",
        eyebrow="Features",
        slug="features",
        empty_msg="No features published yet.",
    )


def build_learn_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Generates /learn/ — introduction and guide kinds."""
    learn = [p for p in pages if p.get("kind") in ("introduction", "guide")]
    return _render_article_list_index(
        site_data=site_data,
        pages=learn,
        base_url=base_url,
        title="Learn",
        description="Orienting introductions and practical auditing guides for working with AI systems.",
        eyebrow="Learning resources",
        slug="learn",
        empty_msg="No guides published yet.",
    )


def build_article_page(
    page: Dict[str, Any],
    site_data: Dict[str, Any],
    body_html: str,
    base_url: str,
    related_pages: Optional[List[Dict[str, Any]]] = None,
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

    canonical_url = canonical_for(base_url, slug)
    section_name, section_slug = {
        "news": ("Latest", "latest"), "release": ("Latest", "latest"),
        "feature": ("Features", "features"), "guide": ("Learn", "learn"),
        "introduction": ("Learn", "learn"), "about": ("About", "about"),
    }[kind]
    trail = [("Home", canonical_for(base_url, ""))]
    if section_slug != slug:
        trail.append((section_name, canonical_for(base_url, section_slug)))
    trail.append((title, canonical_url))
    crumbs = "".join(
        f'<li><a href="{escape(urlparse(url).path)}">{escape(label)}</a></li>'
        if i < len(trail) - 1 else f'<li aria-current="page">{escape(label)}</li>'
        for i, (label, url) in enumerate(trail)
    )
    breadcrumbs = f'<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>{crumbs}</ol></nav>'
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
        related_links = "".join(
            f'<li><a href="{route_href(p["slug"])}">{escape(p["title"])}</a></li>'
            for p in related_pages
        )
        related_html = f'<section class="related-reading" aria-labelledby="related-reading"><h2 id="related-reading">Continue reading</h2><ul>{related_links}</ul></section>'

    kind_labels = {
        "introduction": "Orientation",
        "guide": "Practical Guide",
        "release": "Field Update",
        "news": "News",
        "feature": "Feature",
        "about": "About",
    }
    eyebrow_text = kind_labels.get(kind, "Article")

    topics_markup = "".join(f'<span class="tag">{escape(t)}</span>' for t in topics)

    sources_section = ""
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
        disclosure_section = f"""
        <div class="callout meta-disclosure">
          <h4>Affiliation &amp; Disclosure</h4>
          <p>{escape(disclosure)}</p>
        </div>"""

    updated_markup = ""
    if updated and updated != published:
        updated_markup = f"""
        <dt>Updated</dt>
        <dd><time datetime="{escape(updated)}">{display_date(updated)}</time></dd>"""

    # Event date: shown for news and release kinds, separate from published date
    event_date_markup = ""
    if event_date and event_date != published:
        event_date_markup = f"""
        <dt>Announced</dt>
        <dd><time datetime="{escape(event_date)}">{display_date(event_date)}</time></dd>"""

    header_meta = ""
    if kind != "about":
        event_text = f' &middot; Announced <time datetime="{escape(event_date)}">{display_date(event_date)}</time>' if event_date else ""
        header_meta = f'<p class="article-header-meta">By <a href="/about/">{escape(author)}</a> &middot; Published <time datetime="{escape(published)}">{display_date(published)}</time>{event_text}</p>'

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
          {body_html}
          {related_html}
        </article>

        <aside class="article-aside">
          <div class="article-meta">
            <h3>Document Details</h3>
            <dl class="meta-list">
              <dt>Type</dt>
              <dd>{escape(eyebrow_text)}</dd>
              <dt>Editorial Identity</dt>
              <dd>{escape(author)}</dd>
              <dt>Published</dt>
              <dd><time datetime="{escape(published)}">{display_date(published)}</time></dd>
              {event_date_markup}
              {updated_markup}
            </dl>

            {f'<div class="meta-section"><h4>Topics</h4><div class="tags">{topics_markup}</div></div>' if topics_markup else ''}
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
            "inLanguage": "en",
            "isPartOf": {"@id": canonical_for(base_url, "") + "#website"},
            "articleSection": section_name,
            "keywords": topics,
            "citation": source_urls,
            "isAccessibleForFree": True,
            "headline": title,
            "description": summary,
            "author": publication_identity(site_data, base_url),
            "publisher": publication_identity(site_data, base_url),
            "datePublished": published,
            "dateModified": updated or published,
            "mainEntityOfPage": canonical_url,
        }
    else:
        json_ld = {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "mainEntity": publication_identity(site_data, base_url),
            "name": title,
            "description": summary,
            "url": canonical_url,
        }

    return render_html_page(
        title=title,
        description=summary,
        canonical_url=canonical_url,
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug=slug,
        og_type=og_type,
        extra_meta=extra_meta,
        json_ld=json_ld,
    )


def build_404_page(site_data: Dict[str, Any], base_url: str) -> str:
    """Generates the usable 404 error page (never indexed in sitemap)."""
    body_content = """
    <div class="container">
      <header class="page-header error-header">
        <span class="eyebrow">Error 404</span>
        <h1>Page Not Found</h1>
        <p class="page-lead">We could not find this page on Audit Commons.</p>
      </header>

      <div class="empty-state error-content">
        <p>The page may have moved or the URL may contain a typographical error. You can navigate directly to one of the primary sections below:</p>
        <ul class="error-nav-list">
          <li><a href="/">Home</a>: The publication front page</li>
          <li><a href="/latest/">Latest</a>: Recent articles and news briefs</li>
          <li><a href="/features/">Features</a>: Research explainers and analysis</li>
          <li><a href="/learn/">Learn</a>: Introductions, guides, and worked examples</li>
          <li><a href="/resources/">Resources</a>: Searchable directory of benchmarks, sandboxes, and specifications</li>
          <li><a href="/about/">About</a>: Scope, maintainer disclosures, and contributions</li>
        </ul>
      </div>
    </div>
"""

    return render_html_page(
        title="Page Not Found",
        description="The requested page could not be found on Audit Commons.",
        canonical_url=canonical_for(base_url, "404.html"),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="404",
        og_type="website",
        is_404=True,
    )


def build_sitemap(routes: Dict[str, str], base_url: str) -> str:
    """
    Generates sitemap.xml for public routes.
    Explicitly excludes 404.html.
    """
    clean_base = base_url.rstrip("/")
    url_elements = []

    for route, modified in routes.items():
        if route == "404.html" or route.endswith("404.html"):
            continue
        clean_route = route.strip("/")
        loc = f"{clean_base}/" if not clean_route else f"{clean_base}/{clean_route}/"
        priority = "1.0" if not clean_route else "0.8"
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


def build_atom_feed(
    site_data: Dict[str, Any],
    feed_pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """
    Generates an Atom 1.0 feed (/feed.xml).
    Entries link canonical own update URLs and include primary sources in article summaries.
    """
    clean_base = base_url.rstrip("/")
    site_name = escape(site_data.get("name", "Audit Commons"))
    site_tagline = escape(site_data.get("tagline", "Research, tools, and community for AI auditing."))
    feed_url = f"{clean_base}/feed.xml"
    site_url = f"{clean_base}/"

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
        item_canonical = canonical_for(base_url, slug)
        source_urls = p.get("source_urls", [])

        sources_html = ""
        if source_urls:
            s_list = "".join(f'<li><a href="{escape(u)}">{escape(u)}</a></li>' for u in source_urls)
            source_label = "Primary sources" if p.get("kind") in ("release", "news") else "Related resources"
            sources_html = f"<p><strong>{source_label}:</strong></p><ul>{s_list}</ul>"

        entry_content = html.escape(f'<p>{summary}</p>{sources_html}<p><a href="{escape(item_canonical)}">Read complete article at Audit Commons</a></p>')

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

    # Validate page schemas & dates
    seen_slugs = set()
    for idx, page in enumerate(pages):
        slug = page.get("slug")
        if not slug:
            raise ValueError(f"Page record #{idx} missing required 'slug'")
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*", slug):
            raise ValueError(f"Invalid page slug: {slug!r}")
        if slug.split('/')[0] in {'assets', 'resources', 'index', '404'} or slug in {'guides', 'updates', 'latest', 'features', 'learn'}:
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

    prepare_output_directory(output_dir, repo_root, content_dir, assets_dir)
    # 5. Copy static assets
    copy_assets_safely(assets_dir, output_dir)

    # 6. Render Home Page (/)
    home_html = build_homepage(site_data, pages, resources, effective_base_url)
    (output_dir / "index.html").write_text(home_html, encoding="utf-8")

    # 7. Render Resources Page (/resources/)
    res_html = build_resources_page(site_data, resources, effective_base_url)
    res_dir = output_dir / "resources"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "index.html").write_text(res_html, encoding="utf-8")

    # 8. Render Guides Index (/guides/) — legacy URL kept
    guides_html = build_guides_index(site_data, pages, effective_base_url)
    guides_dir = output_dir / "guides"
    guides_dir.mkdir(parents=True, exist_ok=True)
    (guides_dir / "index.html").write_text(guides_html, encoding="utf-8")

    # 9. Render Updates Index (/updates/) — legacy URL kept
    updates_html = build_updates_index(site_data, pages, effective_base_url)
    updates_dir = output_dir / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    (updates_dir / "index.html").write_text(updates_html, encoding="utf-8")

    # 9b. New editorial section indices
    latest_html = build_latest_index(site_data, pages, effective_base_url)
    latest_dir = output_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    (latest_dir / "index.html").write_text(latest_html, encoding="utf-8")

    features_html = build_features_index(site_data, pages, effective_base_url)
    features_dir = output_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    (features_dir / "index.html").write_text(features_html, encoding="utf-8")

    learn_html_page = build_learn_index(site_data, pages, effective_base_url)
    learn_dir = output_dir / "learn"
    learn_dir.mkdir(parents=True, exist_ok=True)
    (learn_dir / "index.html").write_text(learn_html_page, encoding="utf-8")

    # 10. Render Individual Content Pages from pages.json
    all_sitemap_routes = ["", "resources", "guides", "updates", "latest", "features", "learn"]
    for page in pages:
        slug = page["slug"].strip("/")
        body_file = content_dir / page["body_file"]
        body_html = body_file.read_text(encoding="utf-8")

        article_html = build_article_page(
            page, site_data, body_html, effective_base_url,
            [page_lookup[slug] for slug in page.get("related_slugs", [])],
        )
        target_dir = output_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "index.html").write_text(article_html, encoding="utf-8")

        all_sitemap_routes.append(slug)

    # 11. Render Usable 404 Page (/404.html)
    page_404_html = build_404_page(site_data, effective_base_url)
    (output_dir / "404.html").write_text(page_404_html, encoding="utf-8")

    # 12. Render Sitemap (/sitemap.xml) - Excludes 404.html
    article_dates = {p['slug']: p.get('updated') or p['published'] for p in pages}
    latest_date = max([*article_dates.values(), *(r['checked'] for r in resources)])
    route_dates = {route: article_dates.get(route, latest_date) for route in all_sitemap_routes}
    route_dates['resources'] = max((r['checked'] for r in resources), default=latest_date)
    route_dates['guides'] = max((article_dates[p['slug']] for p in pages if p.get('kind') == 'guide' or p['slug'].startswith('guides/')), default=latest_date)
    route_dates['updates'] = max((article_dates[p['slug']] for p in pages if p.get('kind') == 'release' or p['slug'].startswith('updates/')), default=latest_date)
    route_dates['latest'] = latest_date
    route_dates['features'] = max((article_dates[p['slug']] for p in pages if p.get('kind') == 'feature' or p['slug'].startswith('features/')), default=latest_date)
    route_dates['learn'] = max((article_dates[p['slug']] for p in pages if p.get('kind') in ('guide', 'introduction') or p['slug'].startswith('guides/')), default=latest_date)
    sitemap_xml = build_sitemap(route_dates, effective_base_url)
    (output_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

    # 13. Render Feed (/feed.xml) - Editorial articles (all kinds except about); exclude About
    feed_pages = sorted([p for p in pages if p.get("kind") != "about"], key=lambda p: p["published"], reverse=True)
    feed_xml = build_atom_feed(site_data, feed_pages, effective_base_url)
    (output_dir / "feed.xml").write_text(feed_xml, encoding="utf-8")

    # 14. Render robots.txt
    robots_txt = build_robots_txt(effective_base_url)
    (output_dir / "robots.txt").write_text(robots_txt, encoding="utf-8")

    print(f"Build complete. Emitted {len(all_sitemap_routes) + 1} routes and assets to {output_dir}")




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
