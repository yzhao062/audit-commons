---
name: weekly-refresh
description: Refresh Audit Commons news, learning articles, and resource selections from verified sources, including Chinese translations and relevant media. Use for weekly refresh, editorial refresh, 每周更新, or 内容刷新 in this repository. Produces reviewed local changes; scheduling, email delivery, and publication are separate actions.
---

# Audit Commons weekly refresh

Run from the Audit Commons repository root. Read [AGENTS.local.md](../../AGENTS.local.md), [the maintenance playbook](../../docs/maintenance.md), and [contribution rules](../../CONTRIBUTING.md). Follow the requested scope: research-only requests produce candidates, while requests to refresh content include implementation and validation.

## Use the established refresh profile

For an implemented weekly refresh, use this sequence unless the user narrows it:

1. **Catalog delta:** Treat [Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai) as the default resource intake. Compare its current upstream state with the pinned revision and digest. Compare parsed resource records, not only raw README text. A companion-link, count, formatting, or other metadata-only change does not justify a repin or a catalog rewrite.
2. **Low-cost discovery:** Use `/prun` for bounded, read-only discovery. Separate the work into an upstream catalog delta, official news, and new papers or tools when those units are useful. Each unit returns primary URLs, dates, supported claims, evidence limits, and a proposed destination. Workers do not edit, commit, or push. The coordinating agent selects the batch and owns integration.
3. **Local integration:** The coordinating agent writes the English source, adds or verifies media, writes the Chinese edition, recomputes affected translation hashes, and builds locally. It keeps one integration owner for shared registries and generated routes.
4. **Prepublication gate:** Stage only intended paths, then run `/vet both`, meaning Codex and Agy, sequentially on the final staged batch. Resolve blocking findings and repeat affected checks. Commit and push only after current-scope authorization, then verify the Pages run and changed public routes.

A quiet week may produce no content change. Record a no-change outcome in the response instead of repinning, redating, or publishing a placeholder.

## Establish the window

Inspect Git status, recent editorial commits, and existing `content/pages.json`, `content/resources.json`, and `content/reading-lists.json`. Preserve pending work. Use the requested date window; otherwise use the last completed editorial refresh through today, or the past seven days when no record exists. Report coverage gaps instead of silently claiming that missed weeks were reviewed. A deployment or documentation commit is not an editorial refresh.

Search existing titles, canonical source URLs, paper identifiers, project repositories, and resource IDs before drafting. Distinguish a new event from a correction, a new version of existing work, and an old resource newly cataloged. Retain existing URLs and IDs for the same work.

## Route candidates before writing

| Candidate or reader need | Destination | Read when applicable |
|---|---|---|
| Consequential announcement, evaluation result, policy development, or verified change in lab practice | `news` article; event date and original source visible | [News evidence examples](../../docs/news-pacing-sources.md) |
| A research result that needs explanation of its evidence and limitations | `feature` article, surfaced as Analysis under Latest | [Search and article structure](../../docs/search-visibility.md) |
| A recurring practical question with a usable method or worked exercise | `guide`; link from Learn without duplicating its fixed introductory sequence | [Learn section rules](../../docs/maintenance.md#primary-navigation-and-section-roles) |
| New paper, tool, benchmark, dataset, standard, or collection | One resource record, with evidenced overlapping formats and useful paper/code/data links | [Catalog refresh](../../docs/resource-catalog.md) |
| Material change to an already covered tool | Update existing coverage or use `release` if it warrants a separate story | [Contribution rules](../../CONTRIBUTING.md) |
| Retraction, obsolete instructions, broken destination, or factual correction | Repair the existing record/article first; explain material corrections | [Maintenance](../../docs/maintenance.md) |
| Weekly email digest | Curated draft from published material, only if requested; the feed is not an email service | [Newsletter status and integration](../../docs/newsletter.md) |

An item can justify both an article and a catalog entry when each serves a distinct reader need. Cross-link them. Do not generate separate articles for each artifact of one paper.

## Discover and select

Browse current primary sources. Start from sources already cited by the site and companion [Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai), then follow new evidence outward: original lab announcements and executive posts; evaluator reports; paper abstracts/full text and associated artifacts; official releases; standards bodies. The historical news-source note is an example, not a complete or current watchlist. Search results and social screenshots are leads, not sufficient evidence by themselves.

Prefer consequential developments, reproducible artifacts, useful explanations, and corrections. Within that pool, favor gaps in coverage and reader questions over more coverage of maintainer projects. Do not set a minimum number of articles or add material merely to fill a week. A typical small batch may contain a few news items and resource additions; a guide should earn its place through a concrete learning outcome.

For each selected item, retain the primary URL, event/publication date, claim supported, unresolved limitation, intended destination, and affiliation. Keep rejected leads in session scratch unless they explain a durable editorial decision. If a primary source is inaccessible, use explicitly attributed reliable reporting with the limitation visible, or defer the claim. A CEO's conditional promise is not an implemented research pause; inclusion is not independent validation or endorsement.

## Apply a bounded editorial batch

- **Articles:** edit `content/pages.json` and its referenced HTML body. Answer the reader's question early; include primary links near claims, dates, limits, and applicable disclosures. Preserve `published`; change `updated` only for a substantive edit. Review homepage lead placement, including `homepage_lead` in `content/site.json`, which persists until changed, and related links after adding a story. Do not redate old work or reset feed identities to make a batch look fresh.
- **Catalog:** inspect current upstream differences before importing. For a few additions, make scoped edits. For a full snapshot refresh, follow the pinned-revision/digest procedure and first run `python scripts/import_awesome.py --source-file <local-snapshot.md> --check-only`. Review generated differences in a disposable copy before replacing the working catalog. The importer preserves only its six baseline entries; reconcile other editorial additions, secondary links, disclosures, translations, media mappings, and reading-list IDs deliberately. A source snapshot check is not a live-link or software test. Check destinations for the records actually added or materially changed.
- **Resource submissions:** keep Awesome Auditable AI as the public issue and pull-request channel. A merged upstream entry becomes eligible for the next reviewed catalog refresh, where Audit Commons normalizes and deduplicates it. Describe the result as possible visibility in both the GitHub list and Audit Commons; do not promise automatic or immediate site publication.
- **Selections:** revise `content/reading-lists.json` only when a resource improves its task path. Keep stable catalog IDs, bilingual reasons, four to six entries per path, and at most one maintainer project per path. Do not rotate selections just to create activity.
- **Images:** every `news` article must have a relevant lead image registered in `content/media.json`, with Chinese alt text and caption in `content/zh/media.json`. Consult [media rules](../../docs/media.md). Prefer relevant source photographs, author figures, and real screenshots with verified asset-specific rights, credits, dimensions, and local bytes. If suitable source imagery is unavailable, create a clearly labeled pictorial editorial illustration with substantive visual content that explains the story. Disclose AI-generated images in both language captions; keep them distinct from documentary evidence and measured results. A news article with no image is incomplete and must not pass the publication gate. Images remain optional for other content types.
- **Chinese:** follow [localization](../../docs/localization.md) for every changed article, resource, or image description. Review the translation before recomputing `source_sha256` with the existing helpers in `scripts/localization.py`. Refresh only reviewed affected records; changing hashes alone does not update a translation. Reading-list translations live alongside English in their own configuration.
- **Discovery:** maintain useful titles, summaries, related links, and visible provenance. Use actual Search Console reports when accessible to identify crawl failures and reader queries. Missing measurements remain unavailable. Do not promise rankings or LLM citations, generate keyword variants, or change crawl rules as part of routine editorial work.

## Validate, review, and hand off

Run once on the final content batch, then repeat affected checks only after changes:

```bash
python scripts/build.py
python scripts/check.py
python scripts/check_localization.py
python scripts/check_navigation.py
python scripts/check_reading_lists.py
python scripts/test_news_media.py
git diff --check
```

### Required News Illustration Check

Every `news` item, including existing news, must pass this check before publication:

- Require a substantive news image: a relevant photograph, source figure, real screenshot, or a clearly labeled pictorial editorial illustration. Logos, wordmarks, title cards, generic decoration, and pure text-box diagrams do not satisfy this requirement. Inspect the visual content rather than accepting its registry kind. Disclose AI-generated images in both language captions.
- Confirm a relevant lead image is registered, its local asset exists, and both languages have reviewed alt text, caption, credit, and rights information. Run `scripts/test_news_media.py` to verify the missing-image and news-logo rejection gates. Resource listings may still use logos.
- Open the rendered article and its Latest card in both languages. Scroll each image into view so lazy loading runs; confirm that it loads, has nonzero intrinsic dimensions, and is visibly displayed on desktop and narrow screens. An image path or a passing registry check alone does not establish a visible illustration.
- Inspect the actual picture and caption together for relevance and legibility. Retain a screenshot of the checked news card and article. Confirm that full-content feed entries also include the image and attribution.
- After an authorized deployment, repeat the visual check on the public URLs. A missing, broken, hidden, unrelated, or non-substantive image leaves the news item incomplete; repair it before reporting the refresh complete.

Inspect homepage/Latest placement alongside changed articles. For image, layout, navigation, or filtering changes, also run the browser checks from the maintenance playbook using the actual preview port. For skill/documentation-only edits, validate paths and the diff instead of rebuilding the site.

For a research-only request, stop after returning a source-grounded candidate set. For an implemented refresh, follow the established `/prun` discovery and `/vet both` gate above. Identify an unavailable reviewer and do not substitute a self-review for that reviewer.

Report what changed and why, sources and evidence limits, checks actually completed, and remaining items. For a substantial batch, use the maintenance playbook's update-record fields in `docs/refreshes/YYYY-MM-DD.md`; for small corrections, use the commit description. Record no-change outcomes in the response without changing dates or creating a dummy commit.

Apply existing publication authorization to its stated scope. When publication is authorized, show exact scoped commit/push commands, verify the remote and branch, and verify both the resulting Pages deployment and changed public routes. Otherwise leave a reviewable local diff. This skill does not schedule itself, send a newsletter, or authorize future releases. A later scheduling request should choose cadence, time zone, and whether each run prepares a draft or publishes.
