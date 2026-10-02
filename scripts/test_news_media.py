from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from build import build_article_page
from check import HtmlStructureExtractor
from editorial_media import bind_media


class NewsMediaTests(unittest.TestCase):
    def test_news_requires_a_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'News articles require registered lead images'):
                bind_media(root, root, [{'slug': 'news/example', 'kind': 'news'}], [])

    def test_news_requires_an_article_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {'assets': {}, 'articles': {}, 'resources': {}}
            (root / 'media.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'news/example: missing registered lead image'):
                bind_media(root, root, [{'slug': 'news/example', 'kind': 'news'}], [])

    def test_other_content_can_omit_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(bind_media(root, root, [{'slug': 'guide/example', 'kind': 'guide'}], []), [])

    def test_logos_are_rejected_for_news_but_allowed_for_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'media').mkdir()
            data = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
            (root / 'media/logo.svg').write_bytes(data)
            media = {
                'src': '/assets/media/logo.svg', 'kind': 'logo', 'width': 10, 'height': 10,
                'alt': 'Project logo', 'caption': 'Project logo.', 'credit': 'Project',
                'source_url': 'https://example.org/', 'download_url': 'https://example.org/logo.svg',
                'license': 'Editorial identification', 'license_url': 'https://example.org/',
                'sha256': sha256(data).hexdigest(), 'changes': 'Unmodified.',
            }
            manifest = {'assets': {'logo': media}, 'articles': {'news/example': 'logo'}, 'resources': {}}
            (root / 'media.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'a logo cannot serve as a substantive news image'):
                bind_media(root, root, [{'slug': 'news/example', 'kind': 'news'}], [])
            manifest.update(articles={}, resources={'example': 'logo'})
            (root / 'media.json').write_text(json.dumps(manifest), encoding='utf-8')
            resources = [{'id': 'example'}]
            bind_media(root, root, [], resources)
            self.assertEqual(resources[0]['_media']['kind'], 'logo')

    def test_pending_rights_are_visible_without_a_structured_license_claim(self):
        site = {
            'name': 'Audit Commons', 'tagline': 'News about AI auditing.',
            'maintainer': {'name': 'Yue Zhao', 'url': 'https://yzhao062.github.io/'},
        }
        media = {
            'src': '/assets/media/example.svg', 'kind': 'figure',
            'width': 1000, 'height': 530, 'alt': 'Editorial illustration',
            'caption': 'An editorial illustration.', 'credit': 'Audit Commons',
            'source_url': 'https://auditcommons.org/news/example/',
            'license': 'Reuse license pending',
            'license_url': 'https://auditcommons.org/about/#reuse',
        }
        page = {
            'slug': 'news/example', 'kind': 'news', 'title': 'Example News',
            'summary': 'Example summary.', 'published': '2026-09-27', '_media': media,
        }
        for pending in (True, False):
            for locale in ('en', 'zh'):
                with self.subTest(pending=pending, locale=locale):
                    media['license_pending'] = pending
                    output = build_article_page(page, site, '<p>Example.</p>', 'https://auditcommons.org', locale=locale)
                    parsed = HtmlStructureExtractor()
                    parsed.feed(output)
                    article = next(json.loads(raw) for raw in parsed.json_ld_scripts
                                   if json.loads(raw).get('@type') == 'NewsArticle')
                    self.assertIn(media['license_url'], {href for href, _ in parsed.links})
                    self.assertEqual('license' in article['image'], not pending)
                    if not pending:
                        self.assertEqual(article['image']['license'], media['license_url'])


if __name__ == '__main__':
    unittest.main()
