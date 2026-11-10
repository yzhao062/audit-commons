from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from build import build_article_page
from check import HtmlStructureExtractor
from editorial_media import bind_media, render_media


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

    def test_official_logo_binds_and_renders_as_news_lead(self):
        site = {
            'name': 'Audit Commons', 'tagline': 'News about AI auditing.',
            'maintainer': {'name': 'Yue Zhao', 'url': 'https://yzhao062.github.io/'},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'media').mkdir()
            data = b'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80"><rect width="300" height="80"/></svg>'
            (root / 'media/logo.svg').write_bytes(data)
            media = {
                'src': '/assets/media/logo.svg', 'kind': 'logo', 'width': 300, 'height': 80,
                'alt': 'Example Lab logo', 'caption': 'Official Example Lab logo, shown for identification.',
                'credit': 'Example Lab', 'source_url': 'https://example.org/brand/',
                'download_url': 'https://example.org/logo.svg',
                'license': 'Trademark; editorial identification', 'license_url': 'https://example.org/terms/',
                'sha256': sha256(data).hexdigest(), 'changes': 'Unmodified.',
            }
            manifest = {'assets': {'logo': media}, 'articles': {'news/example': 'logo'},
                        'resources': {'example': 'logo'}}
            (root / 'media.json').write_text(json.dumps(manifest), encoding='utf-8')
            page = {'slug': 'news/example', 'kind': 'news', 'title': 'Example News',
                    'summary': 'Example summary.', 'published': '2026-11-09'}
            resources = [{'id': 'example'}]
            self.assertEqual(bind_media(root, root, [page], resources), [(root / 'media/logo.svg').resolve()])
            self.assertEqual((page['_media']['kind'], resources[0]['_media']['kind']), ('logo', 'logo'))

            for context in ('lead', 'index', 'compact'):
                with self.subTest(context=context):
                    parsed = HtmlStructureExtractor()
                    parsed.feed(render_media(page, context, '/news/example/'))
                    self.assertEqual([image['src'] for image in parsed.images], [media['src']])
                    self.assertIn('/news/example/', {href for href, _ in parsed.links})
            for locale in ('en', 'zh'):
                with self.subTest(locale=locale):
                    output = build_article_page(page, site, '<p>Example.</p>', 'https://auditcommons.org', locale=locale)
                    parsed = HtmlStructureExtractor()
                    parsed.feed(output)
                    image = next(image for image in parsed.images if image['src'] == media['src'])
                    self.assertEqual((image['alt'], image['width'], image['height']), (media['alt'], '300', '80'))
                    self.assertLessEqual({media['source_url'], media['license_url']}, {href for href, _ in parsed.links})
                    article = next(json.loads(raw) for raw in parsed.json_ld_scripts
                                   if json.loads(raw).get('@type') == 'NewsArticle')
                    self.assertEqual(article['image']['url'], 'https://auditcommons.org' + media['src'])
                    self.assertEqual(article['image']['creditText'], media['credit'])

            active = b'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80"><script/></svg>'
            (root / 'media/logo.svg').write_bytes(active)
            media['sha256'] = sha256(active).hexdigest()
            (root / 'media.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'active SVG content'):
                bind_media(root, root, [dict(page)], [])

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
