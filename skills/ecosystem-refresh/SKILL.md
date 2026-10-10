---
name: ecosystem-refresh
description: Combined ecosystem workflow linking upstream Awesome Auditable AI pull-request intake with downstream Audit Commons catalog synchronization and weekly editorial refresh.
---

# Ecosystem Refresh: Awesome Auditable AI and Audit Commons

Run from the Audit Commons repository root. Coordinates upstream intake from
[Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai) with downstream updates to
[Audit Commons](https://auditcommons.org).

Read [AGENTS.local.md](../../AGENTS.local.md), [CONTRIBUTING.md](../../CONTRIBUTING.md),
[Awesome contribution rules](https://github.com/yzhao062/awesome-auditable-ai/blob/main/CONTRIBUTING.md), and [docs/maintenance.md](../../docs/maintenance.md).
For detailed article drafting, learning path curation, and lead selection, link directly to
[skills/weekly-refresh/SKILL.md](../weekly-refresh/SKILL.md) rather than duplicating full guides.

## Governance and Review Invariants

- **Separation of authorization:** Upstream merge authorization and downstream publication
  authorization are distinct. Preserve existing scope authorization where already granted;
  request explicit approval before expanding scope. The skill never grants approvals or
  configures scheduling.
- **Passing CI is not inclusion:** Green checks verify formatting, syntax, and link availability,
  but do not establish auditable AI relevance or factual accuracy. Do not merge merely because CI passes.
- **Accreditation and classification:** Follow [Awesome contribution rules](https://github.com/yzhao062/awesome-auditable-ai/blob/main/CONTRIBUTING.md)
  for `[Standard]` and `[Framework]` entries. Accurately identify private author-issued frameworks
  without claiming third-party or accredited standards status.
- **Attribution and maintainer fixes:** Preserve author credit and pull-request history. Maintainers
  may fix formatting, links, and meaningful summaries directly without automatically requiring author
  revision; defer only when necessary evidence is missing.
- **Review freshness:** Bind each review to the exact branch head and diff or staged tree digest. Re-review
  changed content before merging or publishing; a commit of the reviewed staged tree preserves its
  content review, while an unchanged HEAD with modified staging requires re-review.
- **Reviewer independence:** Coordinator checks do not count as independent review. Upstream PR review uses per-PR
  `/prun` workers, coordinator checks, and an independent `/vet` reviewer: Claude when Codex
  coordinates, or Codex when Claude coordinates. Downstream AC publication gates
  rely on `/vet both`, resolved to two independent reviewers (for Codex coordinator, Claude and Agy;
  for Claude coordinator, Codex and Agy).
- **Integration ownership:** Discovery runs in parallel bounded `/prun` units without a fixed tiny cap;
  shared registries remain under a single integration owner.

## Workflow Phases

### Phase 1: Upstream PR Intake, Review, and Merge

Run this phase inside the Awesome checkout or integration clone.

1. **Inventory open PRs:** Query open pull requests on `yzhao062/awesome-auditable-ai`, recording branch
   names, authors, and exact HEAD commit SHAs (`headRefOid`).
2. **Bounded per-PR review:** Dispatch bounded Agy `/prun` workers to verify each submission against
   [Awesome contribution rules](https://github.com/yzhao062/awesome-auditable-ai/blob/main/CONTRIBUTING.md): auditable AI scope, 4-column paper/dataset tables,
   standalone tool/framework syntax with license and active years, inspectable repos, and factual claims.
3. **Maintainer fix and review:** Maintainers may apply simple formatting or summary corrections directly
   while preserving author attribution. Re-verify the updated head. Defer PRs only when necessary evidence is absent.
4. **Independent review and checks:** Run coordinator verification and independent `/vet` review on the
   exact HEAD commit SHA, using Claude when Codex coordinates or Codex when Claude coordinates. Confirm automated link audit and inventory checks pass (`tools/inventory.py`,
   `tools/check_links.py`).
5. **Authorized merge:** Verify the actual remote, branch, and upstream. Before execution, show the exact
   `gh pr merge <number> --merge --match-head-commit <reviewed-sha>` command and any scoped `git add`,
   `git commit`, and `git push <remote> <branch>` commands. Apply current human authorization; ask only
   when it does not cover the scope. Merge approved PRs pinned to the reviewed HEAD commit SHA.
   Refresh derived inventory claims and social-card assets with `tools/recount.py` and
   `assets/render_social.py` as needed. If batching merges followed by maintainer corrections is
   explicitly authorized, review the combined result and repair counts promptly. Verify final `main` CI.

### Phase 2: Downstream Catalog Synchronization

1. **Parse accepted delta:** Compare the updated upstream `main` README against the pinned snapshot recorded in
   [docs/resource-catalog.md](../../docs/resource-catalog.md). Parse structured resource records, ignoring
   companion link count or whitespace-only changes.
2. **Preserve enrichments:** Update the pinned revision, normalized snapshot digest, and review date together.
   Then run `python scripts/import_awesome.py --source-file <snapshot.md> --check-only`.
   Apply a scoped delta; do not overwrite the published catalog with a full import.
   Preserve baseline entries and custom enrichments detailed in [docs/resource-catalog.md](../../docs/resource-catalog.md)
   (format classifications, maintainer relationship disclosures, and custom secondary links).
3. **Sync bilingual overlays:** Update `content/resources.json` and `content/zh/resources.json`, recomputing
   affected translation digests (`source_sha256`) with `scripts/localization.py`.

### Phase 3: Editorial Refresh, Validation, and Deployment

1. **Evidence-based discovery:** Dispatch bounded discovery units via `/prun` with Agy workers across the
   requested date window. Follow [weekly-refresh](../weekly-refresh/SKILL.md) evidence standards: cite primary URLs,
   event dates, verified claims, and limits; separate promises from implementations; record no-change if quiet.
2. **Substantive news media:** Every news article requires a relevant lead image in `content/media.json` and
   `content/zh/media.json` per [docs/media.md](../../docs/media.md). The build calls `editorial_media.bind_media`
   to reject missing or logo leads in real content; `scripts/test_news_media.py` tests regression fixtures.
   Conduct manual visual review to reject title cards, generic decoration, or pure text-box diagrams.
   Disclose AI generation in both languages.
3. **Validation and preview:** Run the validation suite (`build.py`, `check.py`, `check_localization.py`,
   `check_navigation.py`, `check_reading_lists.py`, `test_news_media.py`). For content or media modifications,
   preview locally with `scripts/browser_check.py` and inspect rendered desktop and mobile cards.
4. **Refresh record:** Document the refresh in `docs/refreshes/YYYY-MM-DD.md` before staging and review.
5. **Prepublication gate:** Stage only intended files. Run `/vet both` (evaluating exact staged content across
   two independent reviewers).
6. **Authorized deployment:** Verify the actual remote, branch, and upstream. Before execution, show the exact
   scoped `git add`, `git commit`, and `git push <remote> <branch>` commands. Apply existing publication
   authorization or request approval for the new scope. Commit, push, and verify live routes on
   `auditcommons.org` and `auditcommons.org/zh/` along with the Atom feed and sitemap.
