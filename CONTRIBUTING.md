# Contributing to Audit Commons

Audit Commons publishes news briefs, explainers, practical learning materials, and selected resources about AI auditing, with an initial emphasis on AI agents.

For recurring editorial work, follow the [maintenance playbook](docs/maintenance.md). For photographs, logos, figures, and screenshots, use the [editorial image guide](docs/media.md), including provenance, rights, captions, and local asset validation.

---

## Editorial Philosophy: Claims Need Evidence

The foundational principle of Audit Commons is:

> **Claims need evidence. AI is no exception.**

We prioritize:
1. **Primary Sources**: Every listed benchmark, risk framework, security sandbox, or specification must link directly to primary sources (e.g. official repository, peer-reviewed paper, or formal institutional specification).
2. **Cautious, Verified Descriptions**: Summaries describe what tools and frameworks actually do based on verified evidence, rather than vendor marketing, capability claims, or prospective projections.
3. **No Fabricated Benchmarks or Invented Schemas**: Case studies and worksheets must reflect real tool semantics, actual command signatures, and reproducible traces. Worked examples must be explicitly labeled as hypothetical where appropriate.
4. **Scope Boundaries**: Explain the auditing question, available evidence, and limits of each resource or example.

---

## Affiliation & Disclosure Policy

Transparency regarding project affiliations is required:
- **Maintainer Projects**: Any tool, library, or benchmark authored or maintained by Audit Commons maintainers (e.g., Yue Zhao) must be explicitly designated with `"relationship": "Maintainer project"` in `content/resources.json`.
- **External Resources**: Independent projects are designated with `"relationship": "External resource"`.
- **Article Disclosures**: Any practical guide or release announcement involving maintainer-affiliated work must include an explicit disclosure block (`affiliation_disclosure`) detailing the nature of the involvement.
- **Maintainer Identity**: The portal is maintained by Yue Zhao. Resource inclusion does not imply endorsement, membership, or certification.

---

## Submission & Editorial Review Process

### 1. Proposing a Curated Resource

To propose a benchmark, sandbox, or framework:
1. Ensure the resource is active, public, and provides primary documentation.
2. For a new individual entry, read the project's primary documentation and record the date checked (`YYYY-MM-DD`). For a catalog import, record the exact upstream snapshot and the date the entry was checked against that snapshot. A catalog review does not imply a live endpoint check, replicated result, or software test.
3. Contributions should be submitted via the companion [Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai) repository or by emailing [yzhao062@gmail.com](mailto:yzhao062@gmail.com). Submissions in English or Chinese are welcome.
4. For inclusion in `content/resources.json`, entries follow this schema:

```json
{
  "id": "resource-identifier",
  "name": "Resource Name",
  "category": "Evaluation",
  "summary": "Cautious, factual description of capabilities.",
  "url": "https://example.org/project",
  "owner": "Institutional or Author Name",
  "relationship": "External resource",
  "source_urls": [
    "https://example.org/primary-paper",
    "https://github.com/example/project"
  ],
  "checked": "2026-09-15"
}
```

Permitted categories: `Evaluation`, `Security`, `Governance`, `Reading`, `Tools`.

The resource library also accepts `format`: `Paper`, `Tool`, `Benchmark`, `Dataset`, `Standard`, or `Collection`. These drive the format tabs; categories remain topic filters. Optional `source_section`, `venue`, `links` (`[{"label": "Code", "url": "https://example.org/code"}]`), and `catalog_source` preserve context and provenance. Imported entries use a pinned upstream README URL in `catalog_source`. See [the catalog maintenance guide](docs/resource-catalog.md) for the snapshot and refresh procedure. Retain original publication status and maintainer affiliations, including co-authored papers.

### 2. Proposing Articles

News briefs report source-dated developments. Features explain research and its implications. Guides teach concepts or walk readers through practical methods. Release notes document specific changes to tools and benchmarks.

- **Author Field**: All records must set `"author": "Audit Commons"` to reflect the shared editorial identity (no personal bylines).
- **Body HTML**: Placed under `content/bodies/{slug}.html`. Must contain clean semantic HTML with `<h2>`, `<h3>`, `<p>`, `<table>`, and `<pre><code>` blocks. Do **not** include an outer `<article>` tag or a duplicate `<h1>` heading (page templates supply the primary header).
- **Dates**: Must follow `YYYY-MM-DD`. `published` is the date an article first appears on Audit Commons; `updated` records an editorial revision. News and release entries also include `event_date`, the date of the reported development. Do not present older work as newly released.
- **Kinds and routes**: Use `news` under `news/`, `feature` under `features/`, and `guide` under `guides/`. Existing `release` entries under `updates/` and the `introduction` page retain their canonical URLs. Section indexes and the feed are generated from the registry.
- **Evidence**: Link factual claims to primary sources in the article body and list those sources in `source_urls`. Separate a source's findings from editorial interpretation; state limitations and label hypothetical examples.
- **Discovery**: Give each article a distinct title and summary that describe the question or development it covers. Answer the central question early. Optional `related_slugs` lists existing article slugs for a short Continue reading section; use relevant connections, not duplicate keyword pages. Keep canonical URLs stable and update dates only after meaningful revisions. See [Search visibility](docs/search-visibility.md) for the measurement routine.

---

## Pre-Submission Verification

Resource `formats` may list several supported types, including the primary `format`. Supply a source or artifact link for each additional type. Tabs count matching unique resources; counts across tabs may overlap. Keep a single catalog record for a work with linked paper, code, and data artifacts.

Before opening a pull request or submitting content:

1. **Build the Portal**:
   ```bash
   python scripts/build.py
   ```
2. **Run the Full Verification Suite**:
   ```bash
   python scripts/check.py
   ```
   The check script verifies:
   - Schema validity for `site.json`, `pages.json`, and `resources.json`.
   - Date formats and absence of duplicate slugs or IDs.
   - Integrity of internal hyperlinks and in-page anchor fragments (e.g. `#main`, `#contribute`, `#corrections`).
   - Structural XML validity of `sitemap.xml` and `feed.xml`.
   - Absence of leaked private files or repository build artifacts.
   - Semantic DOM element presence and accessibility requirements.
