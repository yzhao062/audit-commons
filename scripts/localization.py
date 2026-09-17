#!/usr/bin/env python3
"""
Audit Commons Localization Module
Implements the translation overlay contract, validation, HTML-aware link localization,
SEO alternate tags, and Chinese UI catalogs for the Simplified Chinese edition.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "zh")

LOCALE_LANG = {
    "en": "en",
    "zh": "zh-CN",
}

LOCALE_OG = {
    "en": "en_US",
    "zh": "zh_CN",
}

REQUIRED_NAV_ITEMS_ZH = [
    ("最新", "/zh/latest/"),
    ("学习", "/zh/learn/"),
    ("资源", "/zh/resources/"),
    ("关于", "/zh/about/"),
]

FORMAT_DISPLAY_LABELS_ZH = {
    "Paper": "论文",
    "Tool": "工具",
    "Benchmark": "基准评测",
    "Dataset": "数据集",
    "Standard": "规范标准",
    "Collection": "精选合集",
}

CATEGORY_DISPLAY_LABELS_ZH = {
    "All": "全部",
    "Evaluation": "评估",
    "Security": "安全",
    "Governance": "治理",
    "Reading": "阅读",
    "Tools": "工具",
}

SECTION_DISPLAY_LABELS_ZH = {
    "Runtime Monitoring and Guardrails": "运行时监控与防护",
    "Tools and Platforms": "工具与平台",
    "Datasets and Benchmarks": "数据集与基准",
    "Standards and Governance": "标准与治理",
    "Failure Attribution and Diagnosis": "故障归因与诊断",
    "Security Auditing and Scanners": "安全审计与扫描工具",
    "Audit Trails and Decision Records": "审计轨迹与决策记录",
    "Reliability and Robustness": "可靠性与稳健性",
    "Surveys and Foundations": "综述与基础知识",
    "The Auditable Agents Ecosystem": "Auditable Agents 生态系统",
}

KIND_LABELS_ZH = {
    "introduction": "导读",
    "guide": "实践指南",
    "release": "动态发布",
    "news": "新闻简讯",
    "feature": "深度解读",
    "about": "关于本站",
}


def normalize_slug(slug: str) -> str:
    """Normalize route slug by removing leading/trailing slashes and any zh prefix."""
    clean = slug.strip("/")
    if clean == "zh" or clean.startswith("zh/"):
        clean = clean[2:].lstrip("/")
    return clean


def canonical_for(base_url: str, slug: str, locale: str = "en") -> str:
    """
    Compute canonical URL for a given route slug and locale.
    Guarantees self-canonical URLs for each locale.
    """
    base = base_url.rstrip("/")
    clean = normalize_slug(slug)
    if clean in ("404.html", "404"):
        return f"{base}/zh/404.html" if locale == "zh" else f"{base}/404.html"

    if locale == "zh":
        if not clean:
            return f"{base}/zh/"
        return f"{base}/zh/{clean}/"

    # Default English
    if not clean:
        return f"{base}/"
    return f"{base}/{clean}/"


def route_href(slug: str, locale: str = "en") -> str:
    """Generate root-relative internal link for a route and locale."""
    clean = normalize_slug(slug)
    if clean in ("404.html", "404"):
        return "/zh/404.html" if locale == "zh" else "/404.html"

    if locale == "zh":
        if not clean:
            return "/zh/"
        return f"/zh/{clean}/"

    # Default English
    if not clean:
        return "/"
    return f"/{clean}/"


def get_hreflang_tags(base_url: str, slug: str, has_zh: bool = True) -> str:
    """
    Generates reciprocal hreflang alternate tags for SEO.
    Includes en, zh-CN, and x-default (pointing to English root).
    """
    if not has_zh:
        return ""
    clean_slug = normalize_slug(slug)
    if clean_slug in ("404.html", "404"):
        return ""
    en_url = canonical_for(base_url, clean_slug, locale="en")
    zh_url = canonical_for(base_url, clean_slug, locale="zh")
    return f"""  <link rel="alternate" hreflang="en" href="{html.escape(en_url, quote=True)}">
  <link rel="alternate" hreflang="zh-CN" href="{html.escape(zh_url, quote=True)}">
  <link rel="alternate" hreflang="x-default" href="{html.escape(en_url, quote=True)}">"""


def render_language_switcher(slug: str, current_locale: str = "en", has_zh: bool = True) -> str:
    """
    Renders header language switch links (EN / 中文).
    Marks the current locale with active class and aria-current="true".
    Without JS, works as plain link to equivalent page;
    progressive JS preserves search and hash parameters across switches.
    """
    if not has_zh:
        return ""
    clean_slug = normalize_slug(slug)
    en_href = route_href(clean_slug, locale="en")
    zh_href = route_href(clean_slug, locale="zh")

    en_active = ' class="lang-link is-active" aria-current="true"' if current_locale == "en" else ' class="lang-link"'
    zh_active = ' class="lang-link is-active" aria-current="true"' if current_locale == "zh" else ' class="lang-link"'

    return f"""      <nav class="lang-switch" aria-label="{"Language selector" if current_locale == "en" else "语言切换"}">
        <a href="{en_href}" hreflang="en" lang="en"{en_active}>EN</a>
        <span class="lang-sep" aria-hidden="true">/</span>
        <a href="{zh_href}" hreflang="zh-CN" lang="zh-CN"{zh_active}>中文</a>
      </nav>"""


def localize_body_html(body_html: str, locale: str = "en") -> str:
    """
    Localizes root-relative navigational URLs inside article body HTML.
    Strictly preserves:
    - External URLs (http, https, mailto, tel, javascript)
    - Asset URLs (/assets/..., /favicon.svg, /social-preview)
    - In-page fragment IDs (#heading)
    - Relative URLs without leading /
    Transforms root-relative internal routes (/about/, /start-here/#steps, etc.) to /zh/...
    Transforms /feed.xml to /zh/feed.xml.
    """
    if locale != "zh":
        return body_html

    def _replace_href(match: re.Match[str]) -> str:
        prefix = match.group(1)  # e.g. href="
        url = match.group(2)
        quote = match.group(3)

        if not url:
            return match.group(0)

        # Skip external, protocol-relative, javascript, mailto, or in-page fragment anchors
        if url.startswith(("//", "http://", "https://", "mailto:", "tel:", "javascript:", "#")):
            return match.group(0)

        # Skip static assets
        if url.startswith(("/assets/", "/favicon.svg", "/social-preview")):
            return match.group(0)

        # Already localized
        if url.startswith("/zh/"):
            return match.group(0)

        # Localize feed
        if url == "/feed.xml":
            return f'{prefix}/zh/feed.xml{quote}'

        # Localize root or root-relative internal link
        if url.startswith("/"):
            return f'{prefix}/zh{url}{quote}'

        return match.group(0)

    # Match href="..." and href='...'
    pattern = re.compile(r'(\bhref\s*=\s*["\'])([^"\']*)(["\'])', re.IGNORECASE)
    return pattern.sub(_replace_href, body_html)


def compute_page_source_sha256(original_page: Dict[str, Any], english_body_text: str) -> str:
    """
    Computes source_sha256 for a page per contract:
    hashlib.sha256((json.dumps(original_page, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    + "\n" + English body text read as UTF8 with universal newlines).encode("utf-8")).hexdigest()
    """
    canonical_json = json.dumps(original_page, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    normalized_body = english_body_text.replace("\r\n", "\n").replace("\r", "\n")
    content_to_hash = canonical_json + "\n" + normalized_body
    return hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()


def compute_resource_source_sha256(original_resource: Dict[str, Any]) -> str:
    """
    Computes source_sha256 for a resource per contract:
    hashlib.sha256((json.dumps(original_resource, ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode("utf-8")).hexdigest()
    """
    canonical_json = json.dumps(original_resource, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_media_source_sha256(media: Dict[str, Any]) -> str:
    """Fingerprint the English prose translated in a media overlay."""
    return compute_resource_source_sha256({key: media[key] for key in ("alt", "caption")})


def display_date(date_str: str, locale: str = "en") -> str:
    """
    Formats YYYY-MM-DD date into localized string:
    - en: '16 Sep 2026'
    - zh: '2026年9月16日'
    """
    if not isinstance(date_str, str):
        raise ValueError(f"Date must be a string, got {type(date_str).__name__}")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        raise ValueError(f"Invalid date format '{date_str}'; expected YYYY-MM-DD")
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid calendar date '{date_str}': {e}") from e

    if locale == "zh":
        return f"{dt.year}年{dt.month}月{dt.day}日"
    return f"{dt.day} {dt.strftime('%b')} {dt.year}"


def validate_translation_overlays(
    content_dir: Path,
    raw_pages: List[Dict[str, Any]],
    raw_resources: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Validates translation overlays under content/zh/ before modifying output.
    Returns parsed overlays dictionary containing 'pages', 'resources', 'media', and 'bodies'.
    Returns None if content/zh does not exist (supporting source-less test fixtures).
    Raises ValueError / FileNotFoundError with explicit actionable messages on any failure.
    """
    zh_dir = content_dir / "zh"
    if not zh_dir.exists():
        return None

    if not zh_dir.is_dir():
        raise ValueError(f"content/zh exists but is not a directory: {zh_dir}")

    # 1. Validate content/zh/pages.json
    pages_file = zh_dir / "pages.json"
    if not pages_file.exists():
        raise FileNotFoundError(f"Missing required Chinese pages overlay: {pages_file}")
    try:
        pages_overlay = json.loads(pages_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid JSON in {pages_file}: {e}") from e

    if not isinstance(pages_overlay, dict):
        raise ValueError(f"content/zh/pages.json must be a JSON object keyed by English page slug, got {type(pages_overlay).__name__}")

    # 2. Validate content/zh/resources.json
    res_file = zh_dir / "resources.json"
    if not res_file.exists():
        raise FileNotFoundError(f"Missing required Chinese resources overlay: {res_file}")
    try:
        res_overlay = json.loads(res_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid JSON in {res_file}: {e}") from e

    if not isinstance(res_overlay, dict):
        raise ValueError(f"content/zh/resources.json must be a JSON object keyed by resource ID, got {type(res_overlay).__name__}")

    # 3. Validate content/zh/media.json (optional but validated when present)
    media_file = zh_dir / "media.json"
    media_overlay: Dict[str, Any] = {}
    if media_file.exists():
        try:
            media_overlay = json.loads(media_file.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Invalid JSON in {media_file}: {e}") from e
        if not isinstance(media_overlay, dict):
            raise ValueError(f"content/zh/media.json must be a JSON object keyed by media key, got {type(media_overlay).__name__}")

    # --- Check Pages Coverage & Schemas ---
    english_slugs = {p["slug"] for p in raw_pages}
    zh_slugs = set(pages_overlay.keys())

    missing_slugs = english_slugs - zh_slugs
    if missing_slugs:
        sorted_missing = sorted(missing_slugs)
        raise ValueError(
            f"Missing Chinese translation for page slug(s): {sorted_missing}. "
            f"All {len(raw_pages)} pages must be translated in content/zh/pages.json."
        )

    unknown_slugs = zh_slugs - english_slugs
    if unknown_slugs:
        raise ValueError(f"Unknown page slug(s) in content/zh/pages.json: {sorted(unknown_slugs)}")

    bodies_dir = (zh_dir / "bodies").resolve()
    if not bodies_dir.exists() or not bodies_dir.is_dir():
        raise FileNotFoundError(f"Missing required directory for Chinese body files: {bodies_dir}")

    allowed_page_fields = {"title", "summary", "topics", "body_file", "source_sha256", "affiliation_disclosure"}
    loaded_bodies: Dict[str, str] = {}

    for orig_page in raw_pages:
        slug = orig_page["slug"]
        p_trans = pages_overlay[slug]
        if not isinstance(p_trans, dict):
            raise ValueError(f"Translation entry for page '{slug}' must be a JSON object")

        # Prohibited fields check
        extra_fields = set(p_trans.keys()) - allowed_page_fields
        if extra_fields:
            raise ValueError(
                f"Prohibited field(s) {sorted(extra_fields)} in Chinese overlay for page '{slug}'. "
                f"Do not translate slug, author, URLs, date fields, or add other page fields."
            )

        # Required fields check
        for req_field in ("title", "summary", "topics", "body_file", "source_sha256"):
            if req_field not in p_trans:
                raise ValueError(f"Chinese overlay for page '{slug}' missing required field '{req_field}'")
            if not p_trans[req_field] and req_field != "topics":
                raise ValueError(f"Chinese overlay for page '{slug}' has empty required field '{req_field}'")

        if orig_page.get("affiliation_disclosure") and not p_trans.get("affiliation_disclosure"):
            raise ValueError(f"Chinese overlay for page '{slug}' missing required 'affiliation_disclosure'")

        if not isinstance(p_trans["topics"], list) or len(p_trans["topics"]) != len(orig_page.get("topics", [])):
            raise ValueError(
                f"Chinese overlay for page '{slug}' topics must be a list of same length as English topics "
                f"(expected {len(orig_page.get('topics', []))}, got {len(p_trans.get('topics', []))})"
            )

        # Body file path security & existence
        bf_str = p_trans["body_file"]
        if not isinstance(bf_str, str) or not bf_str.startswith("zh/bodies/") or not bf_str.endswith(".html"):
            raise ValueError(
                f"Chinese body_file for page '{slug}' must be 'zh/bodies/<basename>.html', got '{bf_str}'"
            )

        bf_path = (content_dir / bf_str).resolve()
        if not bf_path.is_relative_to(bodies_dir):
            raise ValueError(f"Chinese body file path traversal detected for page '{slug}': {bf_str}")
        if not bf_path.is_file():
            raise FileNotFoundError(f"Chinese body file not found for page '{slug}': {bf_path}")

        # Universal newline body read
        body_text = bf_path.read_text(encoding="utf-8")
        loaded_bodies[slug] = body_text

        # Validate source_sha256
        en_body_path = (content_dir / orig_page["body_file"]).resolve()
        en_body_text = en_body_path.read_text(encoding="utf-8")
        expected_hash = compute_page_source_sha256(orig_page, en_body_text)
        given_hash = p_trans["source_sha256"]
        if given_hash != expected_hash:
            raise ValueError(
                f"Stale Chinese translation for page '{slug}': source_sha256 mismatch "
                f"(expected {expected_hash}, got {given_hash}). English content has changed."
            )

    # --- Check Resources Coverage & Schemas ---
    english_res_ids = {r["id"] for r in raw_resources}
    zh_res_ids = set(res_overlay.keys())

    missing_res_ids = english_res_ids - zh_res_ids
    if missing_res_ids:
        raise ValueError(
            f"Missing Chinese translation for {len(missing_res_ids)} resource(s) including: {sorted(missing_res_ids)[:5]}. "
            f"All {len(raw_resources)} resources must be translated in content/zh/resources.json."
        )

    unknown_res_ids = zh_res_ids - english_res_ids
    if unknown_res_ids:
        raise ValueError(f"Unknown resource ID(s) in content/zh/resources.json: {sorted(unknown_res_ids)[:5]}")

    allowed_res_fields = {"summary", "source_sha256"}
    for orig_res in raw_resources:
        rid = orig_res["id"]
        r_trans = res_overlay[rid]
        if not isinstance(r_trans, dict):
            raise ValueError(f"Translation entry for resource '{rid}' must be a JSON object")

        extra_res_fields = set(r_trans.keys()) - allowed_res_fields
        if extra_res_fields:
            raise ValueError(
                f"Prohibited field(s) {sorted(extra_res_fields)} in Chinese overlay for resource '{rid}'. "
                f"Only 'summary' and 'source_sha256' are allowed (names and tokens remain original)."
            )

        if "summary" not in r_trans or not isinstance(r_trans["summary"], str) or not r_trans["summary"].strip():
            raise ValueError(f"Chinese overlay for resource '{rid}' missing non-empty 'summary'")

        if "source_sha256" not in r_trans or not isinstance(r_trans["source_sha256"], str):
            raise ValueError(f"Chinese overlay for resource '{rid}' missing 'source_sha256'")

        expected_res_hash = compute_resource_source_sha256(orig_res)
        given_res_hash = r_trans["source_sha256"]
        if given_res_hash != expected_res_hash:
            raise ValueError(
                f"Stale Chinese translation for resource '{rid}': source_sha256 mismatch "
                f"(expected {expected_res_hash}, got {given_res_hash}). English resource has changed."
            )

    # --- Check Media Overlay Schemas ---
    manifest_file = content_dir / "media.json"
    source_media = json.loads(manifest_file.read_text(encoding="utf-8"))["assets"] if manifest_file.exists() else {}
    if set(media_overlay) != set(source_media):
        raise ValueError(f"Chinese media translation coverage mismatch: missing={sorted(set(source_media) - set(media_overlay))}, unknown={sorted(set(media_overlay) - set(source_media))}")
    for m_key, m_val in media_overlay.items():
        if not isinstance(m_val, dict):
            raise ValueError(f"Media translation entry for '{m_key}' must be a JSON object")
        for req in ("alt", "caption"):
            if req not in m_val or not isinstance(m_val[req], str) or not m_val[req].strip():
                raise ValueError(f"Media translation for '{m_key}' missing non-empty '{req}'")
        if set(m_val) != {"alt", "caption", "source_sha256"}:
            raise ValueError(f"Media translation for '{m_key}' must contain only alt, caption, and source_sha256")
        if m_val["source_sha256"] != compute_media_source_sha256(source_media[m_key]):
            raise ValueError(f"Stale Chinese media translation for '{m_key}': source_sha256 mismatch; review the translated alt and caption")

    return {
        "pages": pages_overlay,
        "resources": res_overlay,
        "media": media_overlay,
        "bodies": loaded_bodies,
    }


def apply_page_overlay(orig_page: Dict[str, Any], page_overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Applies Chinese page overlay to an original English page dictionary."""
    localized = dict(orig_page)
    localized["title"] = page_overlay["title"]
    localized["summary"] = page_overlay["summary"]
    localized["topics"] = list(page_overlay["topics"])
    if "affiliation_disclosure" in page_overlay:
        localized["affiliation_disclosure"] = page_overlay["affiliation_disclosure"]
    localized["body_file"] = page_overlay["body_file"]
    return localized


def apply_resource_overlay(orig_res: Dict[str, Any], res_overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Applies Chinese resource overlay to an original English resource dictionary."""
    localized = dict(orig_res)
    localized["summary"] = res_overlay["summary"]
    return localized


def apply_media_overlay(media_asset: Dict[str, Any], media_overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Applies Chinese media overlay to a media asset dictionary."""
    if not media_asset or not media_overlay:
        return media_asset
    localized = dict(media_asset)
    if "alt" in media_overlay:
        localized["alt"] = media_overlay["alt"]
    if "caption" in media_overlay:
        localized["caption"] = media_overlay["caption"]
    return localized
