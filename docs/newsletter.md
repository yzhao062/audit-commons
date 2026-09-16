# Weekly brief: launch proposal

Status: editorial and integration proposal, not a live email subscription service. The website currently offers its working Atom feed at `/feed.xml`, with follow links on the homepage, article pages, and footer. No subscriber emails are collected by this repository.

## Reader promise

Proposed name: **Audit Commons Weekly**.

Proposed signup copy, to publish once email delivery is ready:

> A weekly reading list for AI auditing. Important developments, one practical explanation, and resources worth exploring, with links to the original sources.
>
> Get the weekly brief. Free to read. Unsubscribe at any time.

Place the signup after the homepage lead/news section and at the end of articles. Keep RSS beside the email option. Use a quiet inline section matching the publication's typography, without a modal or page-blocking overlay. A past issue should be available beside the signup so readers can see what they are subscribing to.

## Editorial format

Each issue should take about three minutes to scan:

1. **This week's developments:** up to three sourced news items, each with a short explanation of why it matters and a link to the complete article.
2. **One idea explained:** a practical concept from the learning section, with a link to the guide.
3. **From the library:** one or two useful resources, including format, purpose, and any maintainer affiliation.
4. **A question for readers:** a specific invitation to suggest a source, correction, or question for a future issue.

Select material rather than emailing the full list of new links. Skip an issue when there is no worthwhile update. Distinguish newly published reporting from older resources newly added to the catalog; do not present catalog import dates as research publication dates.

## Proposed delivery integration

Buttondown is a candidate, pending the owner's platform choice and account setup. It supports [embedded subscription forms](https://docs.buttondown.com/building-your-subscriber-base) and [weekly RSS-to-email drafts](https://docs.buttondown.com/rss-to-email), including Atom feeds. Review current plan terms when configuring the service; this document does not authorize a purchase.

Start with weekly draft generation from `https://auditcommons.org/feed.xml`, then edit the selection and add the library item before sending. The current article feed does not include individual catalog additions. Do not treat a feed connection as permission to email contacts or enable unattended sending.

Before enabling the email signup, confirm the real account URL, sender and reply-to addresses, subscription confirmation flow, unsubscribe link, and a concise explanation of which provider receives the submitted email address. Keep all API credentials and subscriber data outside the public repository. Test signup, confirmation, one test issue, and unsubscribe using an explicitly authorized test address. Domain sender verification follows the chosen provider's actual DNS instructions.

## Assess usefulness

Start with confirmed subscriptions, clicks back to articles/resources, replies, and unsubscribes. Treat email opens as a secondary signal. Keep the first review focused on whether readers return and whether the issues are useful enough to sustain; choose a measurement implementation after selecting the email platform.
