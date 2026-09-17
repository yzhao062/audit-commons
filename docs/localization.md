# Audit Commons Localization & Chinese Edition Playbook

This document specifies the architecture, data contracts, and operational workflow for the Simplified Chinese (`/zh/`) edition of Audit Commons.

Audit Commons serves English as its canonical root edition (`/`) and publishes a fully localized Simplified Chinese edition (`/zh/`) using a non-destructive **translation overlay contract**.

---

## 1. Architectural Principles

1. **English Root as Source of Truth**: All primary structural metadata, slugs, publication dates, source URLs, ownership attributions, and relationships originate in English content sources (`content/site.json`, `content/pages.json`, `content/resources.json`, `content/bodies/`, `content/media.json`).
2. **Translation Overlays**: Chinese translations live in parallel overlay files under `content/zh/`. Overlays only contain localized user-facing prose (titles, summaries, body text, image captions). They never duplicate canonical facts like dates or URLs.
3. **Cryptographic Integrity & Stale Detection**: Every translated page, resource record, and media description includes a `source_sha256` fingerprint of the English source. If an English article, resource, or media description is edited without updating its Chinese counterpart, the build system halts immediately before modifying output files.
4. **Zero Remote Dependencies**: The Chinese edition relies exclusively on local, system-native CJK font stacks (`PingFang SC`, `Hiragino Sans GB`, `Microsoft YaHei`, `Source Han Sans SC`, `Noto Sans CJK SC`). No external fonts, analytics, or runtime CDNs are used.
5. **No-JS Resilience & Progressive Enhancement**: All content, navigation, and cross-language switching function as standard semantic HTML hyperlinks without JavaScript. When JavaScript is enabled, search queries, category filters, and fragment anchors are synchronized across language switches.

---

## 2. File Organization

```text
content/
├── site.json               # Global publication metadata & base URL
├── pages.json              # English article registry & metadata
├── resources.json          # English 201-resource catalog
├── media.json              # Media registry (dimensions, credits, source hashes)
├── bodies/                 # English article body HTML fragments
│   ├── start-here.html
│   ├── audit-an-agent-action.html
│   └── ...
└── zh/                     # Chinese translation overlays
    ├── pages.json          # Article overlays (title, summary, topics, disclosure, source_sha256)
    ├── resources.json      # Resource overlays (summary, source_sha256)
    ├── media.json          # Media alt text and caption overlays
    └── bodies/             # Localized article body HTML fragments
        ├── start-here.html
        ├── audit-an-agent-action.html
        └── ...
```

---

## 3. Translation Overlay Contracts

### 3.1 Articles (`content/zh/pages.json`)

The file is a JSON object mapping each article's immutable English `slug` to its translation overlay:

```json
{
  "guides/audit-an-agent-action": {
    "title": "审计智能体行动：外部工具调用证据工作表",
    "summary": "一份实用的工作表与操作流程，用于审查可检验的证据是否支持关于 AI 智能体行动的主张。",
    "topics": [
      "智能体审计",
      "证据工作表",
      "工具调用"
    ],
    "body_file": "zh/bodies/audit-an-agent-action.html",
    "source_sha256": "8367f94f51c005839bea10e6398e7e782c74df898228362fe930538d39477474",
    "affiliation_disclosure": "Audit Commons 由 Yue Zhao 维护。此处描述的流程体现了实用的证据收集方法，不构成正式认证。"
  }
}
```

- **Allowed Keys**: `title`, `summary`, `topics`, `body_file`, `affiliation_disclosure`, `source_sha256`.
- **Prohibited Keys**: `slug`, `published`, `updated`, `event_date`, `author`, `kind`, `source_urls`, `related_slugs`.
- **Digest Contract**: `source_sha256` is computed as:
  ```python
  content_to_hash = json.dumps(original_page, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" + normalized_english_body_text
  source_sha256 = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()
  ```

### 3.2 Resources (`content/zh/resources.json`)

The file is a JSON object mapping each resource's immutable `id` to its localized summary:

```json
{
  "nist-ai-rmf": {
    "summary": "一套用于梳理 AI 风险、责任、度量与管理的自愿性框架。可用于构建审计所需回答的核心问题。",
    "source_sha256": "7c045398ad1411bc187220869ec06783a4c5fd20fc5b08a36898cce4ce403b25"
  }
}
```

- **Allowed Keys**: `summary`, `source_sha256`.
- **Prohibited Keys**: `id`, `name`, `category`, `format`, `formats`, `url`, `owner`, `relationship`, `checked`, `source_section`, `venue`, `catalog_source`, `links`, `source_urls`.
- **Digest Contract**: `source_sha256` is computed as:
  ```python
  canonical_json = json.dumps(original_resource, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
  source_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
  ```

### 3.3 Media (`content/zh/media.json`)

Provides localized image alt text and editorial captions:

```json
{
  "metr": {
    "alt": "METR 标志",
    "caption": "METR，相关报道调查中指明的独立评估机构。",
    "source_sha256": "20669e132f9d5739a9d744b37e7050ea51243d7c5b21b48ee91f7708f8df8032"
  }
}
```

Every source asset must have exactly one matching media overlay; missing or unknown keys fail the build. Compute `source_sha256` with `compute_media_source_sha256(asset)` from `scripts.localization`, using the English asset record in `content/media.json`. The digest covers its `alt` and `caption`; image bytes, original credits, and licenses remain in the shared registry. Review the translated prose before refreshing this digest.

### 3.4 Article Body Localization (`content/zh/bodies/*.html`)

Body HTML files contain translated prose with HTML markup. Link localization rules:
- **Root-relative internal routes**: Automatically converted from `href="/guides/..."` to `href="/zh/guides/..."` at build time.
- **Feed links**: Converted from `href="/feed.xml"` to `href="/zh/feed.xml"`.
- **Preserved unchanged**: External URLs (`https://...`), static assets (`/assets/...`, `/favicon.svg`), and in-page anchor fragments (`#heading`).

---

## 4. SEO & Structured Data Contract

Every generated page conforms to strict internationalization SEO requirements:

| Element | English (`/`) | Chinese (`/zh/`) |
|---|---|---|
| `<html lang="...">` | `en` | `zh-CN` |
| `<meta property="og:locale">` | `en_US` | `zh_CN` |
| `<link rel="canonical">` | Self-referencing (`https://auditcommons.org/...`) | Self-referencing (`https://auditcommons.org/zh/...`) |
| `rel="alternate" hreflang="en"` | Reciprocal link to English route | Reciprocal link to English route |
| `rel="alternate" hreflang="zh-CN"` | Reciprocal link to Chinese route | Reciprocal link to Chinese route |
| `rel="alternate" hreflang="x-default"` | Points to root English route | Points to root English route |
| JSON-LD `inLanguage` | `en` | `zh-CN` |
| 404 Pages (`/404.html`, `/zh/404.html`) | `noindex`, 0 hreflang tags | `noindex`, 0 hreflang tags |

---

## 5. UI & Typography

### 5.1 System CJK Font Stacks

In `assets/style.css`, system CJK font stacks are integrated into custom properties:

```css
--font-serif: "Iowan Old Style", "Apple Garamond", "Baskerville", "Georgia Pro", "Palatino Linotype", "Palatino", Georgia, "Times New Roman", "Source Han Serif SC", "Noto Serif CJK SC", "Songti SC", "SimSun", serif;
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", "Source Han Sans SC", "Noto Sans CJK SC", sans-serif;
```

CJK typography styling includes `:lang(zh-CN)` rules for line height (`1.75`), paragraph spacing, and strict word breaking (`line-break: strict; word-break: break-word;`).

### 5.2 Header Language Switcher

The header includes an accessible language switcher (`<nav class="lang-switch">`):
- Displays `EN / 中文`.
- The active language link carries `aria-current="true"` and `class="lang-link is-active"`.
- Without JavaScript, links directly resolve to the equivalent counterpart page.
- With JavaScript (`assets/site.js`), `syncLanguageSwitchLinks()` dynamically appends current query parameters (`?category=Reading&q=...`) and hash fragments to the language switch targets upon filter interactions.

---

## 6. Maintenance & Verification Workflow

### 6.1 Adding or Updating Content

1. Edit or add the English source record in `content/pages.json` or `content/resources.json`.
2. Translate the changed prose and review it against the English source. Keep attribution, uncertainty, dates, named entities, and source links intact. Article bodies belong in `content/zh/bodies/`; preserve the existing basename recorded in `body_file`.
3. Compute the digest after reviewing the translation. For example, run this Python from the repository root, changing the selected slug or resource ID as needed:

   ```python
   import json
   from pathlib import Path
   from scripts.localization import compute_page_source_sha256, compute_resource_source_sha256

   content = Path("content")
   pages = json.loads((content / "pages.json").read_text(encoding="utf-8"))
   page = next(p for p in pages if p["slug"] == "guides/how-to-read-an-agent-eval-report")
   print(compute_page_source_sha256(page, (content / page["body_file"]).read_text(encoding="utf-8")))

   resources = json.loads((content / "resources.json").read_text(encoding="utf-8"))
   resource = next(r for r in resources if r["id"] == "inspect-aisi")
   print(compute_resource_source_sha256(resource))
   ```

4. Store the reviewed source's digest in the corresponding overlay entry's `source_sha256`. A digest proves source alignment, not translation accuracy. Do not bulk-refresh digests merely to silence a build error.

### 6.2 Running the Test Suites

All tests must pass with zero errors:

```bash
# 1. Build both editions
python scripts/build.py

# 2. Run core verification suite
python scripts/check.py

# 3. Run dedicated localization invariant suite (also required in CI)
python scripts/check_localization.py

# 4. Run Playwright for layout or interaction changes, using the existing preview port
python scripts/browser_check.py --base-url http://127.0.0.1:8765
```

If no preview server is running, start `python -m http.server 8765 --bind 127.0.0.1 --directory _site` in a separate terminal. The browser suite checks both-language summary searches, filter state, updated article anchors, plain-link switching without JavaScript, and narrow-screen overflow. Counts grow with the catalog; the initial bilingual edition had 38 generated HTML routes including both 404 pages.
