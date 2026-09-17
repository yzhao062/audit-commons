# Audit Commons

News, analysis, and learning about AI auditing.

Audit Commons is an editorial publication with a unified four-item primary navigation: **Latest**, **Learn**, **Resources**, and **About** (Chinese: **最新**, **学习**, **资源**, **关于**). It publishes source-dated news briefs, research explainers, and practical auditing guides, with an initial focus on AI agents. In-depth features are integrated into Latest as **Analysis** (**深度解读**); existing `/features/` and `/zh/features/` routes remain accessible as legacy topic indexes. Existing article URLs, canonicals, translations, and media hashes remain strictly intact.

The **Learn** section provides a structured, three-step editorial learning path:

1. **Understand auditable AI** (`/start-here/`): Conceptual baseline distinguishing evaluation, monitoring, and auditing (~2 min reading).
2. **Read an evaluation report** (`/guides/how-to-read-an-agent-eval-report/`): Five critical questions for evaluating benchmark reports (~4 min reading + ~10 min worked critique).
3. **Audit an agent action** (`/guides/audit-an-agent-action/`): Evidence procedure and plaintext worksheet for external tool calls (~4 min reading + ~15 min worksheet exercise).

Each step pairs clear learning outcomes with realistic reading-versus-activity time estimates, editorial source media, and direct links to foundational catalog resources (such as NIST AI RMF, Inspect, and AgentDojo). Additional guides appear in an additional reading section below the curated path.

The homepage leads with the newest featured analysis, while its news column and Latest index are ordered by publication date. Dates remain visible, and editors should refresh featured coverage as the publication grows.

The Resources library adapts the companion Awesome Auditable AI catalog into format tabs with topic filters, search, and links to papers, code, and data. All entries remain in the initial HTML for reading without JavaScript. Catalog provenance and the offline refresh procedure are documented in [Resource catalog](docs/resource-catalog.md).

News and selected resources include locally hosted photographs, project logos, figures, and screenshots. See [Editorial images](docs/media.md) for the contribution and attribution workflow.

Audit Commons publishes in English (`/`) as its root canonical edition, alongside a Simplified Chinese edition (`/zh/`) powered by non-destructive translation overlays. See the [Localization playbook](docs/localization.md) for data contracts and specifications.

For recurring updates, start with the [Editorial maintenance playbook](docs/maintenance.md).
The repository-local [weekly-refresh skill](skills/weekly-refresh/SKILL.md) routes weekly editorial work across news, learning, resources, media, and Chinese translation. It is registered in `AGENTS.local.md` and can be invoked by asking for a weekly refresh; it does not install a schedule or enable automatic publication.

---

## Quickstart & Local Development

This repository uses a standard-library Python 3.12 static generator without external dependencies or package managers.

### Prerequisites

- Python 3.12+ (standard library only)

### 1. Build the Static Site

Generate the static site into `_site/`:

```bash
python scripts/build.py
```

#### Generator Options

```bash
python scripts/build.py --content-dir content --output-dir _site --base-url https://auditcommons.org
```

- `--content-dir`: Directory containing `site.json`, `pages.json`, `resources.json`, and `bodies/` (default: `content`).
- `--output-dir`: Output destination directory (default: `_site`). Protected by strict safety guardrails: denies source directories, repository root, and `.git`; requires empty directory or valid `.generator-owned` ownership marker before cleaning.
- `--base-url`: Canonical base URL origin override (`https` or local `http` only, e.g. `https://auditcommons.org` or `http://localhost:8000`). Subpaths are rejected to preserve root-relative links.
- `--assets-dir`: Directory containing CSS, JS, and SVG assets (default: `assets`).

### 2. Run Verification Suite

Validate source schemas, date formats, internal hyperlinks, in-page fragment targets, sitemap/feed structure, private file exclusion, output safety, and accessibility requirements:

```bash
python scripts/check.py
python scripts/check_localization.py
python scripts/check_navigation.py
python scripts/check_reading_lists.py
```

The same suite checks search metadata: unique titles and descriptions, canonical URLs, crawler access, article schema consistency, visible breadcrumbs, and resources catalog contracts (including format taxonomy schema validation and a 100-row all-formats fixture test). Setup receipts and the ongoing measurement routine are in [Search visibility](docs/search-visibility.md).

#### Verification Options

```bash
python scripts/check.py --content-dir content --output-dir _site --base-url https://auditcommons.org
```

- `--skip-source`: Skips content schema checks when validating output files alone.
- `--skip-safety`: Skips output directory refuse/safety tests.

### 3. Local Preview Server

Serve the generated static output locally:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory _site
```

Visit `http://127.0.0.1:8765/`. All routes and content remain fully readable with JavaScript disabled.

---

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── check.yml           # Build, validation and GitHub Pages deployment
├── assets/                     # Styles, SVGs, and progressive enhancement script
│   ├── style.css               # Typography, colors, and responsive layout
│   ├── site.js                 # Filter, format tabs, keyboard nav, and search enhancement for /resources/
│   ├── mark.svg                # Brand icon mark
│   ├── favicon.svg             # Browser favicon
│   ├── audit-lens.svg          # Retained workflow illustration (not used on the homepage)
│   ├── social-preview.svg      # Vector social preview card
│   └── social-preview.png      # Raster card for link previews
├── content/                    # Structured editorial data & HTML bodies
│   ├── site.json               # Site identity, maintainer info, and base URL
│   ├── pages.json              # Article registry (news, features, guides, start-here, about)
│   ├── resources.json          # Curated benchmarks, toolchains, and specifications
│   └── bodies/                 # Editorial HTML fragments
│       ├── start-here.html
│       ├── audit-an-agent-action.html
│       ├── catchbench-0-1-2.html
│       ├── optstop-bayesian-early-stopping.html
│       ├── nist-nccoe-agent-identity-concept-paper.html
│       ├── benchmark-scores-and-agent-safety.html
│       ├── how-to-read-an-agent-eval-report.html
│       └── about.html
├── content/zh/                 # Simplified Chinese translation overlays
│   ├── pages.json              # Localized article metadata & digests
│   ├── resources.json          # Localized resource summaries & digests
│   ├── media.json              # Localized media alt text & captions
│   └── bodies/                 # Localized article HTML fragments
├── scripts/
│   ├── build.py                # Standard-library static site generator
│   ├── check.py                # Output, link, anchor, schema, and safety validator
│   ├── check_localization.py   # Dedicated localization invariant test suite
│   ├── check_navigation.py     # Navigation, learning path, and editorial category checks
│   ├── localization.py         # Translation overlay contract & SEO helpers
│   └── browser_check.py        # Optional Playwright acceptance checks
├── CONTRIBUTING.md             # Editorial guidelines and submission procedures
└── README.md                   # Development guide and deployment documentation
```

---

## Deployment & Launch Gate

### Continuous Integration (CI)

Automated CI (`.github/workflows/check.yml`) runs on push and pull request to verify:

1. Static site build completes without errors.
2. Output directory safety tests pass (protected paths survive, stale files are cleared).
3. All internal links, fragment anchors, and local assets resolve.
4. Sitemap (`sitemap.xml`) and Atom feed (`feed.xml`) pass XML validation.
5. No private repository files, python scripts, or scratch files leak into build output.

### Deployment Approach & Launch Gate

GitHub Pages deployment uses its official artifact actions. Pull requests build and verify the site. Pushes to `main`, or a manual workflow run on `main`, also publish the verified `_site/` artifact. Repository Pages settings must use GitHub Actions as the source and `auditcommons.org` as the custom domain. Only `_site/` is published; never publish the repository root.

> [!NOTE]
> **Publishing and reuse**
> Publication requires the maintainer's authorization. A reuse license has not yet been selected; no license is inherited from another project. Before the first deployment, create the website repository, configure Pages, and verify the custom domain, DNS and HTTPS.

## Browser checks

Optional development dependency: install Playwright and Chromium with `python -m pip install playwright` and `python -m playwright install chromium`. With the local preview running, run `python scripts/browser_check.py --base-url http://127.0.0.1:8765`. Add `--screenshots <directory>` to retain desktop and mobile screenshots. This checks navigation, layout overflow, keyboard access, filters, and reading without JavaScript. The static build itself needs only the Python standard library.
