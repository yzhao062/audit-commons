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
    ("Start here", "/start-here/"),
    ("Resources", "/resources/"),
    ("Guides", "/guides/"),
    ("Updates", "/updates/"),
    ("About", "/about/"),
]


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
    robots_tag = '<meta name="robots" content="noindex, nofollow">' if is_404 else '<meta name="robots" content="index, follow">'

    # Navigation links
    nav_links_html = []
    clean_current = current_slug.strip("/")
    for label, target in REQUIRED_NAV_ITEMS:
        target_slug = target.strip("/")
        is_active = (clean_current == target_slug) or (target_slug and clean_current.startswith(target_slug))
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
          <span class="brand-subtitle">Research &amp; Verification</span>
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
        <h2>Portal Routes</h2>
        <ul>
          <li><a href="/start-here/">Start here</a></li>
          <li><a href="/resources/">Auditing Resources</a></li>
          <li><a href="/guides/">Practical Guides</a></li>
          <li><a href="/updates/">Field Updates</a></li>
          <li><a href="/about/">About</a></li>
        </ul>
      </div>

      <div class="footer-col footer-editorial">
        <h2>Connect</h2>
        <ul>
          <li><a href="/about/#contribute">Contribution Guide</a></li>
          <li><a href="/about/#corrections">Submit Corrections</a></li>
          <li><a href="/feed.xml">Atom Feed</a></li>
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


def build_homepage(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    resources: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Generates the rich homepage fulfilling all contract requirements."""
    site_desc = escape(site_data.get("description", "An open field portal providing research, evidence worksheets, and curated tooling for auditing autonomous AI agents and systems."))

    # Find featured practical guide (guides/audit-an-agent-action or first guide)
    featured_guide = next((p for p in pages if p.get("slug") == "guides/audit-an-agent-action"), None)
    if not featured_guide:
        featured_guide = next((p for p in pages if p.get("kind") == "guide"), None)

    # Find latest update (updates/catchbench-0-1-2 or first release)
    latest_update = next((p for p in pages if p.get("slug") == "updates/catchbench-0-1-2"), None)
    if not latest_update:
        latest_update = next((p for p in pages if p.get("kind") == "release"), None)

    # Curated resource preview (up to 4-6 resources)
    preview_resources = resources[:3]

    # Build Featured Guide Card
    featured_guide_html = ""
    if featured_guide:
        fg_slug = featured_guide["slug"]
        fg_title = escape(featured_guide["title"])
        fg_summary = escape(featured_guide["summary"])
        fg_topics = "".join(f'<span class="tag">{escape(t)}</span>' for t in featured_guide.get("topics", []))
        featured_guide_html = f"""
    <section class="section featured-guide-section">
      <div class="container">
        <div class="section-heading">
          <span class="eyebrow">Methodology</span>
          <h2>Featured Practical Guide</h2>
        </div>
        <article class="article-card featured-guide-card">
          <div class="article-card-header">
            <span class="tag tag-featured">Practical Guide</span>
            <h3><a href="/{fg_slug}/">{fg_title}</a></h3>
          </div>
          <p class="article-summary">{fg_summary}</p>
          <div class="article-card-meta">
            <div class="tags">{fg_topics}</div>
            <a href="/{fg_slug}/" class="button">Read practical worksheet &rarr;</a>
          </div>
        </article>
      </div>
    </section>"""

    # Build Selected Resources Preview
    resource_cards_html = []
    for r in preview_resources:
        r_name = escape(r.get("name", ""))
        r_url = escape(r.get("url", "#"))
        r_cat = escape(r.get("category", ""))
        r_rel = escape(r.get("relationship", ""))
        r_sum = escape(r.get("summary", ""))
        r_owner = escape(r.get("owner", ""))
        card = f"""
          <article class="resource-card preview-card">
            <div class="resource-card-header">
              <div class="tags">
                <span class="tag tag-category" data-category="{r_cat}">{r_cat}</span>
                <span class="tag tag-relationship">{r_rel}</span>
              </div>
              <h3><a href="{r_url}">{r_name} <span class="external-arrow" aria-hidden="true">&nearr;</span></a></h3>
            </div>
            <p class="resource-summary">{r_sum}</p>
            <div class="resource-meta">
              <span class="resource-owner">Owner: {r_owner}</span>
            </div>
          </article>"""
        resource_cards_html.append(card)
    resources_grid_html = "\n".join(resource_cards_html)

    # Build Latest Update Preview
    latest_update_html = ""
    if latest_update:
        up_slug = latest_update["slug"]
        up_title = escape(latest_update["title"])
        up_summary = escape(latest_update["summary"])
        up_date = escape(latest_update.get("published", ""))
        latest_update_html = f"""
    <section class="section latest-update-section">
      <div class="container">
        <div class="section-heading">
          <span class="eyebrow">Dispatches</span>
          <h2>Latest Field Update</h2>
        </div>
        <article class="article-card update-preview-card">
          <div class="article-card-header">
            <time class="update-date" datetime="{up_date}">{up_date}</time>
            <h3><a href="/{up_slug}/">{up_title}</a></h3>
          </div>
          <p class="article-summary">{up_summary}</p>
          <div class="article-card-footer">
            <a href="/{up_slug}/" class="button button-secondary">Read release note &rarr;</a>
            <a href="/updates/" class="all-updates-link">All updates archive &rarr;</a>
          </div>
        </article>
      </div>
    </section>"""

    body_content = f"""
    <section class="hero">
      <div class="container hero-container">
        <div class="hero-copy">
          <span class="eyebrow">Field Portal for Auditable AI</span>
          <h1 class="hero-title">Claims need evidence.<br>AI is no exception.</h1>
          <p class="hero-lead">{site_desc}</p>
          <div class="hero-actions">
            <a href="/start-here/" class="button">Start here</a>
            <a href="/resources/" class="button button-secondary">Browse resources</a>
          </div>
        </div>
        <div class="hero-visual">
          <img src="/assets/audit-lens.svg?v=graphite" alt="Auditing Workflow: Claim, Evidence, and Finding" width="520" height="420" class="hero-schematic">
        </div>
      </div>
    </section>

    <section class="section routes-section">
      <div class="container">
        <div class="section-heading">
          <span class="eyebrow">Orientation</span>
          <h2>Start with your task</h2>
          <p class="section-lead">Three pathways designed for researchers, evaluators, and system auditors.</p>
        </div>
        <div class="routes">
          <article class="route-card">
            <span class="route-number">01</span>
            <h3><a href="/start-here/">Understand the field</a></h3>
            <p>Explore how evaluation, monitoring, and auditing answer different questions and work together.</p>
            <a href="/start-here/" class="button button-secondary">Start here &rarr;</a>
          </article>

          <article class="route-card">
            <span class="route-number">02</span>
            <h3><a href="/guides/audit-an-agent-action/">Audit an Agent Action</a></h3>
            <p>Use a practical worksheet to connect an action request, its authorization, and a service receipt to a bounded finding.</p>
            <a href="/guides/audit-an-agent-action/" class="button button-secondary">View practical guide &rarr;</a>
          </article>

          <article class="route-card">
            <span class="route-number">03</span>
            <h3><a href="/resources/">Explore Toolchains</a></h3>
            <p>Search and filter curated primary-source benchmarks, evaluation harnesses, security sandboxes, and auditable governance specifications.</p>
            <a href="/resources/" class="button button-secondary">Explore resources &rarr;</a>
          </article>
        </div>
      </div>
    </section>

    {featured_guide_html}

    <section class="section resources-preview-section">
      <div class="container">
        <div class="section-heading">
          <span class="eyebrow">Curated Directory</span>
          <h2>Selected Resources &amp; Toolchains</h2>
          <p class="section-lead">Selected tools and references with maintainer disclosures. Sources are listed in the full directory.</p>
        </div>
        <div class="resource-grid">
          {resources_grid_html}
        </div>
        <div class="section-footer">
          <a href="/resources/" class="button button-secondary">View full directory ({len(resources)} resources) &rarr;</a>
        </div>
      </div>
    </section>

    {latest_update_html}
"""

    json_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_data.get("name", "Audit Commons"),
        "headline": "Audit Commons",
        "url": f"{base_url.rstrip('/')}/",
        "description": site_desc,
        "publisher": {
            "@type": "Organization",
            "name": site_data.get("name", "Audit Commons"),
            "url": f"{base_url.rstrip('/')}/",
        },
    }

    return render_html_page(
        title=site_data.get("name", "Audit Commons"),
        description=site_desc,
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
    """Generates the guides index page."""
    guides = [p for p in pages if p.get("kind") == "guide" or p.get("slug", "").startswith("guides/")]

    cards_html = []
    for g in guides:
        g_slug = g["slug"]
        g_title = escape(g["title"])
        g_summary = escape(g["summary"])
        g_date = escape(g.get("published", ""))
        g_topics = "".join(f'<span class="tag">{escape(t)}</span>' for t in g.get("topics", []))

        card = f"""
        <article class="article-card">
          <div class="article-card-header">
            <span class="eyebrow">Practical Guide</span>
            <h2><a href="/{g_slug}/">{g_title}</a></h2>
          </div>
          <p class="article-summary">{g_summary}</p>
          <div class="article-card-meta">
            <span class="date">Published: <time datetime="{g_date}">{g_date}</time></span>
            <div class="tags">{g_topics}</div>
          </div>
          <a href="/{g_slug}/" class="button button-secondary">Read practical guide &rarr;</a>
        </article>"""
        cards_html.append(card)

    cards_markup = "\n".join(cards_html) if cards_html else '<p class="empty-state">No guides published yet.</p>'

    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">Methodology</span>
        <h1>Practical Auditing Guides</h1>
        <p class="page-lead">Actionable procedures, empirical worksheets, and verification checklists for auditing AI agent behavior.</p>
      </header>

      <div class="article-list">
        {cards_markup}
      </div>
    </div>
"""

    return render_html_page(
        title="Practical Auditing Guides",
        description="Actionable procedures, empirical worksheets, and verification checklists for auditing AI agent behavior.",
        canonical_url=canonical_for(base_url, "guides"),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="guides",
        og_type="website",
    )


def build_updates_index(
    site_data: Dict[str, Any],
    pages: List[Dict[str, Any]],
    base_url: str,
) -> str:
    """Generates the updates index page."""
    updates = [p for p in pages if p.get("kind") == "release" or p.get("slug", "").startswith("updates/")]

    cards_html = []
    for u in updates:
        u_slug = u["slug"]
        u_title = escape(u["title"])
        u_summary = escape(u["summary"])
        u_date = escape(u.get("published", ""))
        u_topics = "".join(f'<span class="tag">{escape(t)}</span>' for t in u.get("topics", []))

        card = f"""
        <article class="article-card">
          <div class="article-card-header">
            <span class="eyebrow">Field Update</span>
            <h2><a href="/{u_slug}/">{u_title}</a></h2>
          </div>
          <p class="article-summary">{u_summary}</p>
          <div class="article-card-meta">
            <span class="date">Published: <time datetime="{u_date}">{u_date}</time></span>
            <div class="tags">{u_topics}</div>
          </div>
          <a href="/{u_slug}/" class="button button-secondary">Read full update &rarr;</a>
        </article>"""
        cards_html.append(card)

    cards_markup = "\n".join(cards_html) if cards_html else '<p class="empty-state">No updates published yet.</p>'

    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">Dispatches</span>
        <h1>Field Updates &amp; Releases</h1>
        <p class="page-lead">Notices, release evaluations, and primary-source progress updates across the AI auditing ecosystem.</p>
      </header>

      <div class="article-list">
        {cards_markup}
      </div>
    </div>
"""

    return render_html_page(
        title="Field Updates & Releases",
        description="Announcements, toolchain updates, and releases from the AI auditing ecosystem.",
        canonical_url=canonical_for(base_url, "updates"),
        base_url=base_url,
        site_data=site_data,
        body_content=body_content,
        current_slug="updates",
        og_type="website",
    )


def build_article_page(
    page: Dict[str, Any],
    site_data: Dict[str, Any],
    body_html: str,
    base_url: str,
) -> str:
    """Generates an individual article / content page."""
    slug = page["slug"]
    title = page["title"]
    summary = page.get("summary", "")
    author = page.get("author", "Audit Commons")
    published = page.get("published", "")
    updated = page.get("updated", "")
    kind = page.get("kind", "article")
    topics = page.get("topics", [])
    source_urls = page.get("source_urls", [])
    disclosure = page.get("affiliation_disclosure", "")

    canonical_url = canonical_for(base_url, slug)

    kind_labels = {
        "introduction": "Orientation",
        "guide": "Practical Guide",
        "release": "Field Update",
        "about": "Portal Overview",
    }
    eyebrow_text = kind_labels.get(kind, "Article")

    topics_markup = "".join(f'<span class="tag">{escape(t)}</span>' for t in topics)

    sources_section = ""
    source_heading = "Primary sources" if kind == "release" else "Related resources"
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
        <dt>Last Reviewed</dt>
        <dd><time datetime="{escape(updated)}">{escape(updated)}</time></dd>"""

    body_content = f"""
    <div class="container">
      <header class="page-header">
        <span class="eyebrow">{escape(eyebrow_text)}</span>
        <h1>{escape(title)}</h1>
        <p class="page-lead">{escape(summary)}</p>
      </header>

      <div class="article-layout">
        <article class="article-body">
          {body_html}
        </article>

        <aside class="article-aside">
          <div class="article-meta">
            <h3>Document Details</h3>
            <dl class="meta-list">
              <dt>Editorial Identity</dt>
              <dd>{escape(author)}</dd>
              <dt>Published</dt>
              <dd><time datetime="{escape(published)}">{escape(published)}</time></dd>
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

    og_type = "article" if kind in ("guide", "release") else "website"
    json_ld: Dict[str, Any]
    if kind in ("guide", "release"):
        json_ld = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": summary,
            "author": {
                "@type": "Organization",
                "name": author,
                "url": f"{base_url.rstrip('/')}/",
            },
            "publisher": {
                "@type": "Organization",
                "name": site_data.get("name", "Audit Commons"),
                "url": f"{base_url.rstrip('/')}/",
            },
            "datePublished": published,
            "dateModified": updated or published,
            "mainEntityOfPage": canonical_url,
        }
    else:
        json_ld = {
            "@context": "https://schema.org",
            "@type": "WebPage",
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
        json_ld=json_ld,
    )


def build_404_page(site_data: Dict[str, Any], base_url: str) -> str:
    """Generates the usable 404 error page (never indexed in sitemap)."""
    body_content = """
    <div class="container">
      <header class="page-header error-header">
        <span class="eyebrow">Error 404</span>
        <h1>Page Not Found</h1>
        <p class="page-lead">The requested route does not exist in the Audit Commons field portal.</p>
      </header>

      <div class="empty-state error-content">
        <p>The page may have moved or the URL may contain a typographical error. You can navigate directly to one of the primary sections below:</p>
        <ul class="error-nav-list">
          <li><a href="/">Portal Home</a>: Overview, schematic, and core tasks</li>
          <li><a href="/start-here/">Start Here</a>: Distinctions between evaluation, monitoring, and auditing</li>
          <li><a href="/resources/">Resources</a>: Searchable directory of benchmarks, sandboxes, and specifications</li>
          <li><a href="/guides/">Practical Guides</a>: Step-by-step auditing worksheets and execution checks</li>
          <li><a href="/updates/">Field Updates</a>: Sourced research and software updates</li>
          <li><a href="/about/">About</a>: Scope, maintainer disclosures, and contributions</li>
        </ul>
      </div>
    </div>
"""

    return render_html_page(
        title="Page Not Found",
        description="The requested page could not be located in the Audit Commons portal.",
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
            source_label = "Primary sources" if p.get("kind") == "release" else "Related resources"
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
        if slug.split('/')[0] in {'assets', 'resources', 'index', '404'} or slug in {'guides', 'updates'}:
            raise ValueError(f"Page slug collides with a generated route: {slug}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate slug detected in pages.json: '{slug}'")
        seen_slugs.add(slug)

        for req_field in ("title", "summary", "author", "published", "kind", "body_file"):
            if req_field not in page:
                raise ValueError(f"Page '{slug}' missing required field '{req_field}'")

        parse_date(page["published"])
        if page.get("updated"):
            parse_date(page["updated"])

        body_file = (content_dir / page["body_file"]).resolve()
        if not body_file.is_relative_to(content_dir.resolve()) or body_file.suffix != '.html':
            raise ValueError(f"Body path must be HTML inside content: {page['body_file']}")
        if not body_file.is_file():
            raise FileNotFoundError(f"Body file not found for page '{slug}': {body_file}")

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

    # 8. Render Guides Index (/guides/)
    guides_html = build_guides_index(site_data, pages, effective_base_url)
    guides_dir = output_dir / "guides"
    guides_dir.mkdir(parents=True, exist_ok=True)
    (guides_dir / "index.html").write_text(guides_html, encoding="utf-8")

    # 9. Render Updates Index (/updates/)
    updates_html = build_updates_index(site_data, pages, effective_base_url)
    updates_dir = output_dir / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    (updates_dir / "index.html").write_text(updates_html, encoding="utf-8")

    # 10. Render Individual Content Pages from pages.json
    all_sitemap_routes = ["", "resources", "guides", "updates"]
    for page in pages:
        slug = page["slug"].strip("/")
        body_file = content_dir / page["body_file"]
        body_html = body_file.read_text(encoding="utf-8")

        article_html = build_article_page(page, site_data, body_html, effective_base_url)
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
    sitemap_xml = build_sitemap(route_dates, effective_base_url)
    (output_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")

    # 13. Render Feed (/feed.xml) - Articles with kind release or guide
    feed_pages = [p for p in pages if p.get("kind") in ("release", "guide")]
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
