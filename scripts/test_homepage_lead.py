import unittest

from build import build_homepage


class HomepageLeadTests(unittest.TestCase):
    def setUp(self):
        self.site = {
            'name': 'Audit Commons',
            'tagline': 'News, analysis, and learning about AI auditing.',
            'maintainer': {'name': 'Yue Zhao', 'url': 'https://yzhao062.github.io/'},
        }
        self.pages = [
            {'slug': 'news/selected', 'kind': 'news', 'title': 'Selected News', 'published': '2026-09-27'},
            {'slug': 'features/default', 'kind': 'feature', 'title': 'Default Analysis', 'published': '2026-09-16'},
            {'slug': 'about', 'kind': 'about', 'title': 'About', 'published': '2026-09-27'},
        ]

    def render(self, locale='en'):
        return build_homepage(self.site, self.pages, [], 'https://auditcommons.org', locale=locale)

    def test_selected_news_leads_both_editions_once(self):
        self.site['homepage_lead'] = 'news/selected'
        for locale in ('en', 'zh'):
            with self.subTest(locale=locale):
                output = self.render(locale)
                lead = output.split('id="pub-lead-heading"', 1)[1].split('</h1>', 1)[0]
                self.assertIn('Selected News', lead)
                self.assertEqual(output.count('Selected News'), 1)
                prefix = '/zh' if locale == 'zh' else ''
                self.assertIn(f'href="{prefix}/news/selected/"', lead)

    def test_absent_selection_preserves_analysis_priority(self):
        output = self.render()
        lead = output.split('id="pub-lead-heading"', 1)[1].split('</h1>', 1)[0]
        self.assertIn('Default Analysis', lead)

    def test_invalid_or_about_selection_is_rejected(self):
        for slug in ('news/missing', 'about'):
            with self.subTest(slug=slug):
                self.site['homepage_lead'] = slug
                with self.assertRaisesRegex(ValueError, 'Unknown editorial homepage lead'):
                    self.render()


if __name__ == '__main__':
    unittest.main()
