# Audit Commons Field Portal

Research, tools, and community for AI auditing.

Audit Commons introduces AI auditing through practical guides, selected resources, and sourced updates. The first edition focuses on AI agents.

---

## Quickstart & Local Development

This repository uses a standard-library Python 3.12 static generator without external dependencies or package managers.

### Prerequisites

- Python 3.12+ (standard library only)

### 1. Build the Static Site

Generate the static portal into `_site/`:

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
```

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
│   ├── site.js                 # Filter and search enhancement for /resources/
│   ├── mark.svg                # Brand icon mark
│   ├── favicon.svg             # Browser favicon
│   ├── audit-lens.svg          # Auditing workflow schematic
│   ├── social-preview.svg      # Vector social preview card
│   └── social-preview.png      # Raster card for link previews
├── content/                    # Structured editorial data & HTML bodies
│   ├── site.json               # Site identity, maintainer info, and base URL
│   ├── pages.json              # Route registry (start-here, guides, updates, about)
│   ├── resources.json          # Curated benchmarks, toolchains, and specifications
│   └── bodies/                 # Editorial HTML fragments
│       ├── start-here.html
│       ├── audit-an-agent-action.html
│       ├── catchbench-0-1-2.html
│       └── about.html
├── scripts/
│   ├── build.py                # Standard-library static site generator
│   ├── check.py                # Output, link, anchor, schema, and safety validator
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
