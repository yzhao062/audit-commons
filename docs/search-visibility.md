# Search visibility

Audit Commons serves readable HTML, stable canonical article URLs, an XML sitemap, an Atom feed, source links, publication dates, and a visible editorial identity. Search visibility work should help people find useful reporting and explanations. It does not guarantee indexing, ranking, or citations in generated answers.

## Webmaster setup

On September 16, 2026, the maintainer verified the `auditcommons.org` Domain property in Google Search Console and the `https://auditcommons.org/` site in Bing Webmaster Tools using DNS records at Namecheap. Both belong to the maintainer's selected personal account. Keep the verification DNS records in place; no verification tokens or private account details belong in this repository.

The submitted sitemap is `https://auditcommons.org/sitemap.xml`.

| Service | Observed setup receipt on September 16, 2026 |
| --- | --- |
| Google Search Console | Ownership verified; sitemap processed successfully; 8 pages discovered |
| Bing Webmaster Tools | Ownership verified; sitemap status Success; 8 URLs discovered; no errors or warnings |

These receipts describe the deployed version at setup time. The editorial redesign and subsequent search metadata changes were still local. Discovered URLs are not a count of indexed pages. Search and AI citation performance were not yet available; do not record unavailable data as measured zeros. Bing's dashboard exposes an AI Performance beta report, but no citation results were available at setup.

After an authorized deployment, check that the live sitemap contains the new article URLs and that both services can read it. Inspect the homepage and one new article with each service's URL inspection tool. Use a request for indexing when the tool indicates it is appropriate; repeated submissions are not a ranking strategy.

## Release checks

Run `python scripts/build.py` and `python scripts/check.py` before publication. The existing CI validation runs the same checks. Search checks enforce unique titles and descriptions, self-referencing canonicals, crawler access, the 404 indexing exclusion, and agreement between article metadata, source records, and visible breadcrumbs. Related reading stays in ordinary HTML links so navigation works without JavaScript.

After publication, verify the live homepage, one article, `robots.txt`, and `sitemap.xml` return HTTP 200, and a nonexistent URL returns HTTP 404. Inspect the rendered canonical and robots tags. A local build passing does not establish that hosting or search engines see the same output.

Use Article for explainers and guides, NewsArticle for news briefs, and BreadcrumbList for visible navigation. Audit Commons is the shared editorial identity; link it to the About page. Structured data must describe visible content. Do not add invented ratings, institutional endorsements, personal authors, or a generic publication logo as an article's representative image. Add relevant article images when editorially useful, with descriptive alternative text and appropriate reuse rights.

Keep published URLs stable. Change `updated` only for a meaningful editorial revision, not to make an old article appear fresh. News records retain a separate source-event date. Sitemap dates derive from content records rather than the build clock.

## Weekly editorial and measurement routine

Once reports contain enough data, compare the latest complete 28 days with the previous 28 days, allowing for each service's reporting delay. New sites may need a baseline period before that comparison is meaningful. This is a manual routine, not an installed automation.

| Question | Evidence to record | Action |
| --- | --- | --- |
| Can engines discover the pages? | Sitemap status, indexed/excluded URLs, URL inspection reason | Fix accidental blocks, wrong canonicals, broken routes, and links before adding more content |
| Which questions bring readers? | GSC and Bing queries, impressions, clicks, CTR, landing pages, average position with query/device context | Improve pages that already answer those questions; avoid changing titles based on tiny samples |
| Are explanations being cited? | Bing AI Performance when populated; identifiable referral visits if measurement is added | Inspect the cited source page and improve evidence, clarity, and attribution; do not equate Bing coverage with every LLM |
| Is coverage useful and current? | Verified primary-source developments, corrections, missing learning topics | Publish selected news with context and maintain durable guides |

Initial topic clusters are AI auditing versus evaluation and monitoring, reading AI agent evaluation reports, and evidence for agent tool calls. Use these as editorial questions, not keywords to repeat. Each new article should answer its central question early, distinguish reported facts from interpretation, link primary evidence, state limits, and link a small number of relevant guides or explainers through `related_slugs`. Prefer a useful new angle or substantive update over overlapping thin pages. External links should come from relevant, authentic references rather than purchased or automated link schemes.

## Search and AI retrieval references

- [Google: AI features and your website](https://developers.google.com/search/docs/appearance/ai-features): ordinary indexing and SEO foundations apply; no special AI text file or schema is required for eligibility.
- [Google: Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article) and [Breadcrumb structured data](https://developers.google.com/search/docs/appearance/structured-data/breadcrumb): keep metadata consistent with the article and its navigation.
- [Bing Webmaster Guidelines](https://www.bing.com/webmasters/help/webmaster-guidelines-30fba23a): discovery, content quality, canonicalization, and evidence matter for search and grounding.
- [OpenAI crawler documentation](https://developers.openai.com/api/docs/bots): OAI-SearchBot serves search discovery; GPTBot has a separate training purpose. Current robots.txt permits crawlers generally. This work does not change the site's training policy.

There is no universal registration that ensures retrieval by every LLM. Do not present an `llms.txt` file, structured data, or sitemap submission as an AI ranking guarantee. Revisit optional mechanisms such as IndexNow when the publishing cadence justifies them and their live behavior can be verified.
