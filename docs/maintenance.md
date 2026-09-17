# Editorial maintenance playbook

This is the repeatable workflow for updating Audit Commons. It records decisions from the September 16, 2026 development and review cycle. Counts and measurements in linked documents describe dated snapshots; inspect current content before using them as a baseline.

## Editorial direction

Readers should immediately recognize a place to learn, follow news, and find useful resources. Lead with identifiable stories, dates, sources, explanations, and a browsable library. Keep subscription invitations quiet and secondary to reading. Avoid a product-style hero, repeated calls to action, promotional claims, or giving maintainer projects disproportionate prominence.

Use visual variety where it adds information: relevant photographs for news, author figures for research explanations, real interface screenshots for guides, and official project marks or previews for resources. A generic diagram does not substitute for a requested news photograph. Text-only entries are appropriate when no relevant, usable image exists. Do not require a picture on every card.

## Where updates belong

| Change | Source of truth |
|---|---|
| Article title, summary, type, dates, sources, related articles | `content/pages.json` |
| Article prose and source-linked explanation | `content/bodies/` HTML fragments |
| Resource entries and overlapping format memberships | `content/resources.json` |
| Pinned catalog import and classification | `scripts/import_awesome.py`, `scripts/resource_formats.py` |
| Image provenance, article/resource mappings | `content/media.json` |
| Chinese article overlays and bodies | `content/zh/pages.json`, `content/zh/bodies/` |
| Chinese resource catalog overlays | `content/zh/resources.json` |
| Chinese image alt & caption overlays | `content/zh/media.json` |
| Local image bytes and retained legal notices | `assets/media/` |
| Rendering, presentation, resource filtering | `scripts/build.py`, `scripts/editorial_media.py`, `scripts/localization.py`, `assets/style.css`, `assets/site.js` |
| Generated pages, sitemap, feed | `_site/`, rebuilt from sources; never hand-edit |

Read [contribution rules](../CONTRIBUTING.md) before editing. The detailed references are [news source research](news-pacing-sources.md), [catalog synchronization](resource-catalog.md), [editorial images](media.md), [search visibility](search-visibility.md), [bilingual localization](localization.md), and [newsletter proposal](newsletter.md).

## Primary navigation and section roles

The publication maintains an agreed four-item primary navigation across English and Chinese: **Latest**, **Learn**, **Resources**, and **About** (Chinese: **最新**, **学习**, **资源**, **关于**).

- **Latest** (`/latest/`, `/zh/latest/`): Chronological stream of all published editorial items (news briefs, deep analysis, practical guides, and release updates). Features are integrated under Latest as **Analysis** (**深度解读**); existing `/features/` and `/zh/features/` URLs remain accessible as legacy topic archives. The stream includes accessible, progressively enhanced filter controls (`All`, `News`, `Analysis`, `Guides`, `Releases`) that persist `?kind=...` query state across reloads and language switches, while falling back gracefully to a complete readable list without JavaScript. Deep article breadcrumbs point back to Latest.
- **Learn** (`/learn/`, `/zh/learn/`): A structured, three-step editorial learning path replacing the earlier flat list:

  1. *Understand auditable AI* (`/start-here/`): Conceptual baseline distinguishing evaluation, monitoring, and auditing, and explaining evidence boundaries beyond model text (~2 min reading).
  2. *Read an evaluation report* (`/guides/how-to-read-an-agent-eval-report/`): Five critical evaluation questions applied to benchmark reports (~4 min reading + ~10 min worked critique).
  3. *Audit an agent action* (`/guides/audit-an-agent-action/`): Five core evidence elements and a plaintext evidence worksheet for external tool calls (~4 min reading + ~15 min worksheet exercise).

  Future practical guides automatically populate an *Additional Guides & Reference* (*延伸阅读与参考指南*) section below the curated path to ensure discoverability without URL duplication.
- **Resources** (`/resources/`, `/zh/resources/`): Searchable, filterable catalog of curated papers, tools, benchmarks, datasets, standards, and collections adapted from Awesome Auditable AI.
- **About** (`/about/`, `/zh/about/`): Editorial policies, disclosures, maintainer background, and contribution procedures.

### Maintenance requirements for Learn and Latest

- **Learn step integrity:** Each curated step must specify an explicit learning outcome, an editorial time estimate distinguishing reading time from worksheet/activity practice (currently 2/4/4 reading minutes for roughly 316/740/698 English words; revisit after substantive edits and when reviewing Chinese pacing), a direct link, and practical related catalog resources using curated queries (`?q=...`), categories (`?category=...`), or formats (`?format=...`). Avoid maintainer overpromotion by highlighting external foundational resources (e.g., NIST AI RMF, UK AISI Inspect, ETH Zurich AgentDojo).
- **No duplicate URLs:** Articles retain their single canonical URL across sections. Guides appear either in the 3-step sequence or in the additional reading list, never duplicated.
- **Bilingual synchronization:** All updates to Learn headings, outcomes, time estimates, and resource labels must be synchronized across English and Chinese (`/zh/learn/`) with appropriate localized typography and link targets.
- **Accessible filtering:** Latest filter buttons must maintain semantic ARIA attributes (`aria-pressed`), and article cards must include `data-kind` attributes matching source kinds (`news`, `feature`, `guide`, `release`). All content must remain fully visible and readable when JavaScript is disabled.
- **Preserve legacy routes:** Ensure existing routes (`/features/`, `/zh/features/`, `/guides/`, `/updates/`) remain operational for external referrers and bookmarks.

## A recurring update cycle

For an agent-led refresh, use the repository-local [weekly-refresh skill](../skills/weekly-refresh/SKILL.md), registered in `AGENTS.local.md`. For example: "Run weekly-refresh for the past seven days; update worthwhile news and resources in English and Chinese, then validate the local changes." The skill routes candidates to the appropriate content type and loads the detailed guides only when needed. It is a reusable manual workflow; no scheduled task has been enabled.

1. Read `AGENTS.md` and `AGENTS.local.md`, inspect Git status and recent history, and identify unpublished work. Preserve other contributors' changes. Confirm which checkout and preview server belong to this site.
2. Review candidate developments from primary sources. Select items with a concrete reader benefit: a consequential event, an explanation of evidence, a useful released artifact, or a material correction. Skip a thin week instead of filling a quota.
3. Update or add articles, resource records, and relevant media using the rules below. Link related explanations and resources. Keep one canonical URL per article in each language; a new section or presentation does not require a duplicate page.
4. Build and validate the changed source. For visual or interactive changes, inspect the rendered pages and run browser checks. Review the homepage as well as the page edited, because lead selection and shared components affect both.
5. Complete any requested independent review on the actual final changes. Record actionable feedback and its disposition. Repeat affected checks after fixes; an earlier passing report does not certify a later revision.
6. Prepare a scoped diff and publish only with explicit authorization. Then verify the deployment and the changed public pages. Record the outcome using the template below.

This is a manual workflow, not an installed recurring job or an authorization to send email or publish future changes.

## News and learning: preserve the evidence boundary

Distinguish a CEO's statement, a conditional commitment, a reported plan, a specific training pause, and a verified organizational action. A pause affecting one workload is not evidence that a lab has stopped research. A planned external investigation is not a completed audit or certification.

Prefer the original post, announcement, paper, or report. When the primary post cannot be verified, attribute the claim to the reporting source and state the limitation. Do not silently turn a journalist's paraphrase into a direct CEO quotation. Keep source links close to the claim they support.

Keep event dates separate from publication and substantive update dates. A newly imported older paper is not new research. Change update dates for meaningful revisions, not merely because a build ran. Preserve corrections and explain material changes rather than disguising them as fresh stories.

Explain what a resource can teach the reader and what its evidence cannot establish. Disclose maintainer authorship or co-authorship; inclusion does not imply endorsement or independent validation.

## Resources: classification and safe refreshes

Use `format` for the primary label and `formats` for all evidenced memberships. A paper with a released dataset may appear in both tabs while remaining one record. Tab counts overlap; the All count is unique resources. A benchmark or code repository does not automatically qualify as a dataset. Find a specific data artifact or dataset destination before adding that membership.

Merge paper, code, and data links for the same work. Preserve stable resource IDs, affiliation disclosures, and curated baseline entries. Upstream Markdown can contain escaped link labels and cross-listed papers; inspect parsed results rather than assuming every line is one unique resource.

Follow the [catalog refresh procedure](resource-catalog.md#5-catalog-synchronization--refresh-workflow). A new upstream snapshot requires updating its pinned revision, normalized source digest, and review date together. Run the importer's `--check-only` mode first. The importer verifies local snapshot integrity; it does not test every external URL or reproduce research results.

Before a full refresh, identify editorial additions outside the upstream snapshot. Only the six baseline entries are permanently anchored by the current importer; other additions can be replaced. Compare the output and deliberately restore still-valid enrichments. Review media mappings afterward: the separate media registry survives imports, but a removed or renamed resource can leave an invalid mapping.

## Images: lessons from the first illustrated edition

Follow [Editorial images](media.md) for registry fields and rights. Verify what an image actually depicts, its original date, exact credit, and asset-specific permissions. An institution's logo is not evidence of an affiliation. Label archive photographs with their dates, and present sourced charts or interface scores as illustrative material rather than results measured by Audit Commons.

Store assets locally with their provenance and applicable legal notices. Preserve downloaded bytes: Git line-ending conversion of an SVG changes its SHA-256 even when it looks identical. The media rules in `.gitattributes` prevent this. Do not reformat upstream license files to satisfy whitespace preferences.

Keep SVG validation strict. If an upstream logo/banner contains active content, external dependencies, or unsupported `foreignObject` markup, seek a safe static upstream alternative. Do not weaken the validator just to admit one asset. Any derivative needs an accurate changes record and updated dimensions and digest.

Preserve aspect ratios and legibility. Contain logos and scientific figures instead of cropping them, provide informative alt text and intrinsic dimensions, and avoid enlarging small images. Check light logos against the actual background. Keep full-resolution article images accessible while considering appropriately sized previews for lists.

Screenshots with example scores must keep their explanatory context. They use the generic social-preview fallback, as do SVGs and raster images below the current 600-pixel width threshold. Large raster photographs or figures may supply article previews. Metadata must describe what readers actually see.

Check transfer size as the library grows. The initial September 16 set was about 3.8 MB, with roughly 2.4 MB of media transferred after a full homepage scroll during review. These are historical observations, not a performance target or a current speed measurement. Lazy loading helps initial loading but does not eliminate total transfer; prefer suitable source thumbnails or documented derivatives for future growth.

## Verification and publication

Run from the repository root with Python 3.12 or newer:

```bash
python scripts/build.py
python scripts/check.py
python scripts/check_localization.py
python scripts/check_navigation.py
python scripts/check_reading_lists.py
```

For changes to images, layout, navigation, or resource filtering, use the optional Playwright setup in the [README](../README.md#browser-checks). Reuse an existing preview server when possible; otherwise start one in a separate terminal:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory _site
python scripts/browser_check.py --base-url http://127.0.0.1:8765
```

Use the actual server port if different. Inspect desktop and narrow mobile layouts, image decoding, captions and credit links, long titles, and overflow. For resource interactions, include combined filters, URL state, keyboard use, and reading without JavaScript. For documentation-only changes, check the diff, referenced paths, and commands; rerunning browser tests is unnecessary unless site behavior changed.

When Claude and Agy reviews are requested, use their available review channels and disclose an unavailable reviewer. Do not label a self-review as an independent review. Keep review scratch files, browser captures, credentials, and private account details outside published output.

Before release, inspect both staged and unstaged changes, stage only intended paths, and run `git diff --check` plus `git diff --cached --check`. Show the exact commit and push commands and obtain explicit authorization when it has not already been given for that scope. Verify the actual branch, upstream, and remote; do not assume the local branch is named `main`. Reconcile remote advances without force-pushing unrelated work.

A push to remote `main` triggers the current Pages deployment. Confirm the workflow's result, then check the changed public routes, images and credit links, canonical URLs, sitemap, and feed as relevant. A local build or a successful push alone does not demonstrate that the intended revision is live.

## Discovery and returning readers

The About page's `#contact` section and the site-wide footer provide the editorial contact route in both languages. The public editorial address is `hello@auditcommons.org`, selected by the maintainer on September 17, 2026. Namecheap catch-all email forwarding is configured to `yzhao062@gmail.com` and MX records are verified. Inbound receipt remains untested; record a successful end-to-end delivery separately rather than treating DNS configuration as delivery proof. Update both About bodies, the contribution guide, and the reviewed Chinese source digest together when changing the address.

Maintain readable initial HTML, descriptive titles and summaries, stable canonical URLs, visible source links and dates, and consistent structured data. Follow [Search visibility](search-visibility.md) for indexing checks and comparisons over complete reporting periods. Search-console setup receipts and submitted URL counts are dated records, not proof of current indexing or ranking. Actual Search Console observation on September 17, 2026: Performance and Indexing reports remain processing; sitemap reports status 'Success' (last read September 16, 2026, with 8 discovered URLs). This observation confirms sitemap processing only, and does not constitute proof of search indexing, ranking, or incoming organic traffic. No new measurement document or tracker is needed. Do not promise search position or LLM citation gains.

The Atom feed is working and provides full editorial content syndication; email delivery is a separate, unfinished setup described in the [newsletter proposal](newsletter.md). Task-oriented resource selections and complete syndication feeds outrank a newsletter scaffold in editorial priority because they immediately deliver browsable, verifiable reference value to readers without requiring speculative subscriber collection, fake signup workflows, or unfulfilled publication frequency promises. Keep that distinction visible. Do not present a signup form or weekly email promise as operational until delivery, confirmation, unsubscribe, and the provider disclosure are configured and tested. Use reader clicks, replies, and useful return visits to guide coverage when data exists; missing measurements are not zeros.

## Update record template

Use this in a release note or a dated repository note for substantial update batches. Omit private account information and tokens. Small corrections can record the same essentials in the commit description.

```text
Date and scope:
Reader benefit and affected routes:
Primary sources, event dates, and unresolved evidence limits:
Catalog snapshot revision/digest, preserved additions (if refreshed):
Media provenance/rights and any derivatives (if changed):
Validation commands and results on the final revision:
Independent review findings and disposition (if requested):
Publication authorization, commit, and deployment result:
Live verification and remaining follow-ups:
```
