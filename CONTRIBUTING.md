# Contributing to Audit Commons

Thank you for your interest in contributing to the **Audit Commons** field portal.

Audit Commons introduces AI auditing through practical guides, selected resources, and sourced updates, with an initial emphasis on AI agents.

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
2. Verify the project's documentation and record the date checked (`YYYY-MM-DD`).
3. Contributions should be submitted via the companion [Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai) repository or by contacting the maintainer via [his university homepage](https://viterbi-web.usc.edu/~yzhao010/).
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

### 2. Proposing Practical Guides or Field Updates

Practical guides and field updates provide step-by-step methodologies and release notes.

- **Author Field**: All records must set `"author": "Audit Commons"` to reflect the shared editorial identity (no personal bylines).
- **Body HTML**: Placed under `content/bodies/{slug}.html`. Must contain clean semantic HTML with `<h2>`, `<h3>`, `<p>`, `<table>`, and `<pre><code>` blocks. Do **not** include an outer `<article>` tag or a duplicate `<h1>` heading (page templates supply the primary header).
- **Dates**: Must follow `YYYY-MM-DD`. Review dates reflect the editorial verification date.

---

## Pre-Submission Verification

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
