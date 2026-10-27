# Auditable Agents Companion Pass

The Auditable Agents ecosystem site at https://auditable-agents.github.io/ lives in the sibling checkout `auditable-agents.github.io`. It is a separate repository, not part of Audit Commons. Its [maintainer guide](../../../../auditable-agents.github.io/README.md) governs card format, status labels, and ordering; this reference adds the weekly procedure. The pass covers new talks, media coverage, and papers.

The user has authorized recurring read-only discovery and local edits to that site as part of the weekly refresh. This is not authorization to publish, commit, push, send mail, or create a schedule.

## Preserve Existing Content

Changes are additive only, because the page carries existing proposal-linked content.

1. Before editing, record the local HEAD of the site checkout as this run's baseline (`git -C ../auditable-agents.github.io rev-parse HEAD`) and save copies of the original `index.html` and `README.md` bytes in session scratch, outside any repository.
2. After editing, confirm that `git -C ../auditable-agents.github.io diff --numstat <baseline> -- index.html README.md` reports zero deleted lines, and that every original line from the saved copies is still present in its original order. Confirm that existing element IDs, anchors, links, and scripts are unchanged.
3. Never rewrite an original claim, count, or date. When an earlier entry is wrong or outdated, append a dated correction or follow-up next to it. Additive-only is not permission to leave a known falsehood without a visible correction.

## Window and Sources

Review from the last completed ecosystem check through today. Record the actual coverage and any gaps. Do not add content to fill a week, and do not redate existing entries.

- **Outlook** in the built-in browser: professional talk invitations, published programs, and media correspondence.
- **Gmail** when relevant and accessible.
- **Public sources:** original media articles, and public paper, version, and code sources such as arXiv, DOI records, and repository releases.
- **Local research files:** leads only, confirmed against a public or primary source.

Do not send mail. Never copy raw email text, contacts, credentials, travel logistics, or private manuscript or proposal information into the public repository. A missing login does not block other sources; report it as a coverage gap.

## Inclusion Rules

- **Talks:** a confirmed invitation becomes an `upcoming` entry with title, host, and date. Show only the month when sources disagree on the exact date. Never infer that a talk was delivered because its date has passed. Record completion only with evidence, such as a recording, a published program, or organizer confirmation, as an appended dated follow-up.
- **Media:** add only an article that has actually been published, with its outlet and publication date. An interview request or pending piece is not coverage.
- **Papers:** add only a verified public release, with title, identifier (arXiv ID and version, or DOI), date, and a claim scope that matches the public source. Never add a private draft. A preprint alone does not support an accepted or published claim.
- **Cards:** add a news card, and a Research card when relevant, only for items relevant to auditable AI that are not already on the page. Give each a stable ID as the maintainer guide specifies. Deduplicate by canonical URL, DOI, arXiv ID and version, or host and event. A new version of existing work is a follow-up on the existing card, not a duplicate.
- **Order:** insert by event or publication date as the maintainer guide describes, without reordering existing cards. The Added date records when the card was added and stays separate from the event date.
- **Wording:** add a URL only after opening it; never invent an event URL. Do not imply endorsement, partnership, or adoption.

These simple cards do not follow the Audit Commons article image, media registry, or bilingual requirements.

## Evidence Records

- Link public evidence on the card where available.
- Keep sanitized verification receipts and the coverage report (window, sources checked, gaps, decisions) in the sibling `research-impact` repository at `impact/weekly/YYYY-MM-DD.md`, or in a private snapshot linked from it.
- Update `impact/events.csv` under the existing stage rules in [the impact README](../../../../research-impact/impact/README.md). A private confirmed invitation is a pending event and must not count toward publicly verified X1.
- Do not add the ecosystem site to the frozen numeric metric cohort.
- Each repository owns its changes: page edits in `auditable-agents.github.io`, private records in `research-impact`.

## Validate and Hand Off

- Open every new link and confirm it supports the stated claim. Review the scoped diff against the baseline, confirm anchor IDs are unique, and rerun the preservation check.
- For layout changes, check the page in a browser at desktop and narrow widths and in each theme the page supports.
- Run the existing `/vet` gate before publication. Commit or push only with current-scope authorization and exact scoped commands. No future automatic push has been granted, and this pass creates no scheduler.
- In an unchanged week, do not modify the site. Record the no-change or partial-coverage outcome privately in the weekly report.
