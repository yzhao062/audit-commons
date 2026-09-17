# Resource Catalog Specification & Provenance

This document records the provenance, licensing, schema contract, and synchronization process for the Audit Commons Resource Catalog (`content/resources.json`).

---

## 1. Upstream Source, Pinned Revision & Integrity

The Resource Catalog imports curated entries from the companion [Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai) repository.

- **Upstream Repository**: [`https://github.com/yzhao062/awesome-auditable-ai`](https://github.com/yzhao062/awesome-auditable-ai)
- **Pinned Commit Revision**: `2ac4b36328e9d84dbfb7a99c64fbe507dae28288`
- **Normalized LF UTF-8 SHA256**: `bf51fe0299a4846663ab52e13452fe312167bf8f7ba425c8fd5ce642ba041976`
- **Upstream License**: Creative Commons Zero v1.0 Universal (CC0 1.0) Public Domain Dedication ([`awesome-LICENSE`](https://creativecommons.org/publicdomain/zero/1.0/))
- **Site-Wide License Status**: Site-wide license selection for Audit Commons remains **pending**. Upstream catalog metadata is imported under CC0 1.0 attribution, but Audit Commons does not inherit another site's license or bind unpublished sections.

---

## 2. Provenance, Affiliation & Review Disclosure

### Review Scope & Date Semantics
The Resource Catalog records snapshot review dates via the `checked` field:
- **Baseline Curated Entries (`checked: "2026-09-15"`)**: The original 6 curated baseline resources retain their original review date from the initial site launch.
- **Synchronized Catalog Entries (`checked: "2026-09-16"`)**: All entries imported from the upstream snapshot use the snapshot review date (`2026-09-16`).

The `checked` date indicates that a catalog entry was verified against the pinned snapshot records and confirmed for:
- Destination URL syntax and canonicalization (e.g. arXiv `/abs/` over `/pdf/`, root repository trailing slash normalization).
- Upstream curation alignment, category classification, and semantic format determination.
- Absence of promotional hype or unsubstantiated vendor marketing language in summaries.

**Provenance Clarification**: The `checked` date verifies upstream snapshot record consistency and URL syntax. It does **not** constitute independent empirical replication of paper findings, live network endpoint probing, or runtime safety testing of software packages. Summaries reflect upstream catalog curation.

### Affiliation & Maintainer Project Disclosure
In accordance with [`CONTRIBUTING.md`](../CONTRIBUTING.md), transparent affiliation disclosure is strictly enforced to avoid undisclosed self-promotion:
- **Maintainer Projects (`"relationship": "Maintainer project"`)**: Any tool, benchmark, catalog, or research paper authored, co-authored, or maintained by Audit Commons maintainer Yue Zhao is explicitly classified as a Maintainer project. Exactly **9** records carry this designation:
  1. `awesome-auditable-ai`: Companion upstream curated catalog maintained by Yue Zhao.
  2. `auditable-agents`: Auditable Agents ecosystem portal and community registry.
  3. `catchbench`: Benchmark for behavioral consistency and failure detection in tool-using agents.
  4. `auditable`: Runtime auditing library and trace instrumentation engine.
  5. `auditable-agents-paper`: Auditable Agents framework paper (arXiv:2604.05485).
  6. `grade`: Research paper on graph representation of agent execution dependencies (arXiv:2606.22741).
  7. `aegis-runtime`: Runtime policy enforcement and kill switch wrapper (Justin0504/Aegis, co-authored paper arXiv:2603.12621).
  8. `agent-audit-paper`: Static security analysis system for agent applications (CAIS 2026, arXiv:2603.22853).
  9. `agent-audit`: Static security scanner for LLM agents mapping to OWASP Agentic Top 10 (HeadyZhang/agent-audit).
- **External Resources (`"relationship": "External resource"`)**: All independent research papers, open-source platforms, benchmarks, datasets, and standards are classified as External resources (**192** records).

### Attribution Policy
- For academic research papers without a single institutional author, the `owner` field neutrally records `"Authors listed in the paper"` rather than inventing speculative or partial author rosters.
- Formal standards credit their publishing bodies (e.g. NIST, ISO/IEC, MITRE, OWASP, OpenTelemetry / CNCF, IETF, European Union, Cloud Security Alliance).
- Open-source platforms and tools credit their maintainer organizations or developer communities.

---

## 3. Catalog Data Contract

Every record in `content/resources.json` conforms to the following schema contract:

| Field | Type | Requirement | Description | Permitted Values / Format |
|---|---|---|---|---|
| `id` | string | Required | Unique kebab-case slug | `^[a-z0-9]+(-[a-z0-9]+)*$` |
| `name` | string | Required | Plain-text resource title | Clean string, stripped of Markdown |
| `category` | string | Required | Legacy topic grouping | `Evaluation`, `Security`, `Governance`, `Reading`, `Tools` |
| `format` | string | Optional for legacy entries; supplied by importer | Semantic resource format; legacy default is `Collection` | `Paper`, `Tool`, `Benchmark`, `Dataset`, `Standard`, `Collection` |
| `formats` | string[] | Optional for legacy entries; supplied by importer | All supported formats, including the primary `format`; non-empty and duplicate-free | Same six format names |
| `summary` | string | Required | Factual, concise summary | Plain text stripped of Markdown markup |
| `url` | string | Required | Canonical primary URL | Valid HTTP/HTTPS URL |
| `owner` | string | Required | Publisher or neutral attribution | Institution, organization, or `"Authors listed in the paper"` |
| `relationship` | string | Required | Affiliation disclosure | `"Maintainer project"` (9 items) or `"External resource"` (192 items) |
| `source_urls` | string[] | Required | Primary source URLs | Non-empty array of valid URLs |
| `checked` | string | Required | Review date | `YYYY-MM-DD` (`"2026-09-15"` for baseline 6; `"2026-09-16"` for snapshot imports) |
| `source_section` | string | Optional | Upstream section heading | Exact section heading name from source snapshot |
| `venue` | string | Optional | Publication venue | E.g. `ICML 2025`, `Preprint 2026`, `CAIS 2026` |
| `links` | object[] | Optional | Secondary links | Array of `{"label": string, "url": string}` |
| `catalog_source` | string | Optional | Pinned upstream README link | URL with pinned commit and section anchor |

---

## 4. Coverage & Deduplication Statistics

The snapshot contains 204 raw entries across 9 substantive sections, plus the original 6 curated resources.

### Deduplication & Baseline Preservation
1. **Original 6 Preservation**: The 6 baseline entries are identified by explicit IDs (`nist-ai-rmf`, `inspect-aisi`, `agentdojo`, `awesome-auditable-ai`, `catchbench`, `auditable-agents`) and preserved at indices `0..5` of `content/resources.json` to keep homepage featured resources intact.
2. **Upstream Matching against Original 6**: 4 entries in the 204 raw items duplicated original resources and were enriched in-place rather than inserted as duplicates:
   - `NIST AI 100-1, AI Risk Management Framework` &rarr; enriched `nist-ai-rmf`
   - `Inspect` &rarr; enriched `inspect-aisi`
   - `AgentDojo` &rarr; enriched `agentdojo`
   - `CatchBench` &rarr; enriched `catchbench`
3. **Cross-Listed Deduplication**: 5 papers cross-listed between topical sections and the *Datasets and Benchmarks* section were deduplicated into single canonical records with combined paper and benchmark/dataset links:
   - `ReliabilityBench` (Reliability and Robustness &harr; Datasets and Benchmarks)
   - `TRAIL` (Failure Attribution and Diagnosis &harr; Datasets and Benchmarks)
   - `Which Agent Causes Task Failures and When?` (Failure Attribution &harr; Datasets and Benchmarks)
   - `Aegis: Automated Error Generation` (Failure Attribution &harr; Datasets and Benchmarks)
   - `τ-bench` (Reliability and Robustness &harr; Datasets and Benchmarks)

### Exact Counts
- **Total Raw Items Parsed**: 204
- **Preserved Original Entries**: 6
- **Deduplicated vs Original Entries**: 4
- **Deduplicated Cross-Listed Entries**: 5
- **Newly Added Unique Entries**: 195
- **Total Resources in Catalog**: **201**

### Breakdown by Relationship (`relationship`)
| Relationship | Count | Description |
|---|---|---|
| `External resource` | 192 | Independent academic research, industry tools, benchmarks, and standards |
| `Maintainer project` | 9 | Resources authored, co-authored, or maintained by Yue Zhao |
| **Total** | **201** | |

### Breakdown by Primary Format (`format`)

These mutually exclusive primary labels preserve the original classification. The interface filters on `formats`, so its tab counts overlap instead of using this table.
| Format | Count | Semantic Definition |
|---|---|---|
| `Paper` | 94 | Standalone research papers, diagnostic studies, and surveys |
| `Tool` | 45 | Software libraries, runtime platforms, debuggers, scanners, or guardrails |
| `Benchmark` | 40 | Evaluative testbeds, benchmark suites, and testing environments |
| `Standard` | 18 | Formal specifications, protocols, regulatory articles, and risk frameworks |
| `Collection` | 3 | Curated catalogs, ecosystems, or reading list collections |
| `Dataset` | 1 | Standalone corpora and annotated trajectory datasets |
| **Total** | **201** | |

### Tab memberships (`formats`)

Paper: 139; Tool: 45; Benchmark: 41; Dataset: 7; Standard: 18; Collection: 3. The All tab contains 201 unique resources. A paper with a released dataset appears in both tabs, with one card per tab.

The importer merges format memberships from cross-listed records, adds Paper for a linked paper or arXiv abstract, and adds Dataset only for a specifically identified dataset link or a Hugging Face dataset URL. It does not classify a code repository as a tool or dataset merely because it has code, and does not infer datasets from a venue name or incidental mention in a summary. Legacy records without `formats` use their single `format`, or Collection if both fields are absent.

The MAST dataset link was added during editorial review on September 16, 2026, following the [authors' repository](https://github.com/multi-agent-systems-failure-taxonomy/MAST) to [MAST-Data](https://huggingface.co/datasets/mcemri/MAST-Data). It supplements the pinned catalog record. The seven Dataset entries are Who&When, MAST-Data, TRAIL, AEGIS (attribution), PALADIN, GAIA, and PACT. A dataset label indicates an identified artifact, not unrestricted access, licensing approval, or independent validation of its contents.

### Breakdown by Category (`category`)
| Category | Count | Topic Focus |
|---|---|---|
| `Evaluation` | 66 | Benchmarks, failure attribution, and reliability measurement |
| `Governance` | 47 | Audit trails, decision provenance, specifications, and regulatory frameworks |
| `Security` | 41 | Prompt injection, sandboxing, vulnerability scanners, and guardrails |
| `Tools` | 37 | Tracing platforms, telemetry instrumentation, and runtime execution |
| `Reading` | 10 | Surveys, foundational literature, and curated reading lists |
| **Total** | **201** | |

### Breakdown by Section (`source_section`)
| Section | Count |
|---|---|
| Runtime Monitoring and Guardrails | 29 |
| Tools and Platforms | 28 |
| Datasets and Benchmarks | 26 |
| Standards and Governance | 25 |
| Failure Attribution and Diagnosis | 25 |
| Security Auditing and Scanners | 23 |
| Audit Trails and Decision Records | 22 |
| Reliability and Robustness | 13 |
| Surveys and Foundations | 9 |
| The Auditable Agents Ecosystem | 1 |
| **Total** | **201** |

---

## 5. Catalog Synchronization & Refresh Workflow

The importer script (`scripts/import_awesome.py`) is zero-dependency, reproducible, and strictly deterministic.

### Running the Importer
```bash
# Dry-run validation check:
python scripts/import_awesome.py --source-file <path-to-awesome-source.md> --check-only

# Execute import and update content/resources.json:
python scripts/import_awesome.py --source-file <path-to-awesome-source.md>
```

### Fail-Closed Integrity & Validation Invariants
- **Mandatory `--source-file`**: The importer requires an explicit `--source-file` argument. Ambient path guessing or default search paths are prohibited to avoid reading arbitrary files.
- **Fail-Closed Snapshot Verification**: Before parsing, the importer computes the normalized LF UTF-8 SHA256 checksum of the source snapshot and asserts exact match with `EXPECTED_SNAPSHOT_SHA256` (`bf51fe0299a4846663ab52e13452fe312167bf8f7ba425c8fd5ce642ba041976`). If the hash differs, the script aborts immediately with a non-zero status without modifying `content/resources.json`.
- **Lockstep Constant Updates**: On future snapshot updates, the three metadata constants in `scripts/import_awesome.py` must be updated together in lockstep:
  1. `PINNED_REVISION`: Commit SHA of the upstream snapshot (`2ac4b36328e9d84dbfb7a99c64fbe507dae28288`).
  2. `EXPECTED_SNAPSHOT_SHA256`: Normalized LF UTF-8 SHA256 digest of the new snapshot file.
  3. `SNAPSHOT_REVIEW_DATE`: Date of snapshot review and verification (`YYYY-MM-DD`).
- **Output Path Safety**: The output path cannot match the source path, preventing accidental source destruction. Output files must have `.json` extension.
- **Pre-Write Baseline Verification**: Before writing, the importer inspects existing `content/resources.json` to verify the presence of all 6 expected original resource IDs (`nist-ai-rmf`, `inspect-aisi`, `agentdojo`, `awesome-auditable-ai`, `catchbench`, `auditable-agents`). If the file is missing, invalid JSON, or missing any expected ID, the script errors out before any write occurs.
- **Preserved Order & Baseline**: The 6 baseline entries are preserved at indices `0..5` with `checked: "2026-09-15"`.
- **Full Snapshot Refresh Policy**: During a full snapshot refresh, non-upstream resources other than the 6 baseline curated entries are replaced by the newly synchronized snapshot entries. Only the 6 baseline resources are permanently anchored.
- **Zero Network Invariant**: The script operates purely on local files with no network access during build or import.
- **Portable Output**: No private machine paths, user names, or environment-specific strings are emitted to output files.

### Verification Suite
After any catalog modification, run the static build and validation suite:
```bash
# 1. Build static output
python scripts/build.py

# 2. Run full schema, link, and accessibility validation
python scripts/check.py
```
All 201 resources are checked for schema compliance and rendered internal links. External link reachability is not tested.

The `aegis-runtime` paper link (arXiv:2603.12621) was added during editorial review to document co-authorship; it is not part of the pinned README record. Imported sentence fragments otherwise retain the upstream wording and capitalization.

---

## 6. Task-Oriented Resource Selections (Reading Lists)

To help practitioners navigate the catalog for specific operational tasks without wading through the full 201-item catalog, Audit Commons publishes three curated reading paths in `content/reading-lists.json` under the heading **Start with a task** (**从任务开始**):

1. **Evaluate an agent before deployment** (`evaluate-agent-deployment`): Select realistic tasks, measure tool-use consistency, and review failure traces before release.
2. **Secure tool use and prompt injection** (`secure-tool-use-prompt-injection`): Test injection resistance, separate instructions from untrusted data, and scan tool configurations.
3. **Governance and evidence foundations** (`governance-evidence-foundations`): Identify audit questions, document model bounds, map decision provenance, and capture OpenTelemetry execution traces.

### 6.1 Schema Contract (`content/reading-lists.json`)

`content/reading-lists.json` is a JSON array of selection objects adhering to the following schema:

| Field | Type | Requirement | Description |
|---|---|---|---|
| `id` | string | Required | Unique kebab-case slug matching `^[a-z0-9]+(-[a-z0-9]+)*$` |
| `title` | object | Required | Bilingual titles with non-empty `en` and `zh` strings |
| `purpose` | object | Required | Bilingual summary of selection scope with non-empty `en` and `zh` strings |
| `items` | object[] | Required | Ordered array of 4 to 6 curated resource items |
| `items[].resource_id` | string | Required | Existing catalog `id` in `content/resources.json` |
| `items[].rationale` | object | Required | Bilingual action-oriented justification (one sentence) with non-empty `en` and `zh` strings |

### 6.2 Editorial Curation Rules & Invariants

1. **Catalog Truth & No Fabricated URLs**: Every `resource_id` must match an existing record in `content/resources.json`. Metadata (title, canonical URL, format, relationship, owner) is pulled directly from the catalog. Direct canonical URLs prevent filter-hidden anchor navigation bugs.
2. **Action-Oriented Rationales**: Rationale text must instruct the reader on what to do with each resource (e.g. choose task &rarr; measure &rarr; review evidence) rather than restating a generic abstract. Each rationale is exactly one sentence.
3. **Reading Suggestions, Not Certification**: Selections are reading suggestions to orient practice and testing, not formal certifications, compliance guarantees, or institutional endorsements.
4. **Maintainer Project Cap & Tag Disclosure**: To prevent undisclosed self-promotion, each selection enforces a hard cap of **at most 1 maintainer project** (`relationship: "Maintainer project"`). Maintainer affiliation is disclosed via the existing card tag, never duplicated in rationale prose. External resources (such as OpenInference) are preferred whenever suitable.
5. **Item Boundaries**: Each selection contains between 4 and 6 items arranged in logical sequence.
6. **Bilingual Completeness**: English and Chinese texts must be supplied for every `title`, `purpose`, and item `rationale`. Translations must not be empty or whitespace-only.
7. **Accessible Static Presentation**: Selections render as native `<details>` and `<summary>` rows on the Resources page (`/resources/`, `/zh/resources/`), remaining fully functional without JavaScript. Summary children use valid phrasing elements (`<span>`). The markup does not use the `.resource-card` CSS class to preserve catalog filter isolation and tab counts.
8. **Concise Learn Bridge**: A single sentence on `/learn/` and `/zh/learn/` links directly to `/resources/#curated-selections` without duplicating another learning curriculum or adding parallel promotional CTA buttons.

### 6.3 Validation & CI Enforcement

Curated selections are strictly verified prior to any output modification:
```bash
python scripts/check_reading_lists.py
```
This suite verifies JSON schema compliance, cross-checks all resource IDs against `content/resources.json`, tests negative fail-closed rejection cases (unknown IDs, duplicate IDs, missing translations, maintainer cap breaches), and inspects emitted HTML in `_site` for both language editions.
