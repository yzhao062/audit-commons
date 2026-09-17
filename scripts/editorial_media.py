"""Curated, locally hosted media kept separate from imported catalog records."""

from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


def bind_media(content_dir, assets_dir, pages, resources):
    manifest_path = content_dir / 'media.json'
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assets = manifest['assets']
    media_root = (assets_dir / 'media').resolve()
    files = set()
    for key, media in assets.items():
        for field in ('src', 'kind', 'alt', 'caption', 'credit', 'source_url',
                      'license', 'license_url', 'sha256', 'changes'):
            if not isinstance(media.get(field), str) or not media[field].strip():
                raise ValueError(f'Media {key}: missing {field}')
        if media['kind'] not in {'photo', 'logo', 'screenshot', 'figure'}:
            raise ValueError(f'Media {key}: unknown kind')
        for field in ('width', 'height'):
            if type(media.get(field)) is not int or media[field] <= 0:
                raise ValueError(f'Media {key}: invalid {field}')
        for field in ('source_url', 'license_url', 'download_url'):
            url = urlparse(media.get(field, ''))
            if url.scheme != 'https' or not url.netloc:
                raise ValueError(f'Media {key}: invalid {field}')
        for field in ('src', 'license_file', 'notice_file'):
            if field not in media:
                continue
            src = media[field]
            if not src.startswith('/assets/media/'):
                raise ValueError(f'Media {key}: expected a local media path')
            file = (assets_dir / src.removeprefix('/assets/')).resolve()
            if not file.is_relative_to(media_root) or not file.is_file():
                raise ValueError(f'Media {key}: missing or unsafe local asset')
            files.add(file)
            if field == 'src':
                data = file.read_bytes()
                if file.suffix.lower() not in {'.png', '.jpg', '.webp', '.svg'}:
                    raise ValueError(f'Media {key}: unsupported image type')
                if sha256(data).hexdigest() != media['sha256']:
                    raise ValueError(f'Media {key}: asset digest changed; review provenance')
                if file.suffix.lower() == '.svg':
                    root = ET.fromstring(data)
                    for element in root.iter():
                        tag = element.tag.rsplit('}', 1)[-1].lower()
                        if tag in {'script', 'foreignobject'}:
                            raise ValueError(f'Media {key}: active SVG content')
                        for attr, value in element.attrib.items():
                            attr = attr.rsplit('}', 1)[-1].lower()
                            embedded_bitmap = tag == 'image' and value.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,'))
                            if attr.startswith('on') or (attr == 'href' and not value.startswith('#') and not embedded_bitmap):
                                raise ValueError(f'Media {key}: active or external SVG reference')
                    if re.search(rb'@import\b|url\(\s*[\"\']?\s*(?:https?:|//|data:)', data, re.I):
                        raise ValueError(f'Media {key}: external SVG style reference')
    for section, items, id_field in [('articles', pages, 'slug'), ('resources', resources, 'id')]:
        records = {item[id_field]: item for item in items}
        for record_id, media_id in manifest[section].items():
            if record_id not in records or media_id not in assets:
                raise ValueError(f'Media mapping {section}/{record_id}: unknown record or asset')
            records[record_id]['_media'] = assets[media_id]
    return sorted(files)


def media_credit(media):
    return (f'<a href="{escape(media["source_url"], quote=True)}">{escape(media["credit"])}</a>'
            f' · <a href="{escape(media["license_url"], quote=True)}">{escape(media["license"])}</a>')


def social_image_eligible(media):
    return bool(media and media['kind'] != 'screenshot'
                and not media['src'].lower().endswith('.svg') and media['width'] >= 600)


def render_media(record, context='index', href='', priority=False):
    media = record.get('_media')
    if not media:
        return ''
    image = (f'<img src="{escape(media["src"], quote=True)}" alt="{escape(media["alt"], quote=True)}" '
             f'width="{media["width"]}" height="{media["height"]}" '
             f'loading="{"eager" if priority else "lazy"}" decoding="async"'
             f'{" fetchpriority=\"high\"" if priority else ""}>')
    target = href or media['src']
    rel = ' rel="noopener noreferrer"' if target.startswith('https://') else ''
    frame = f'<a class="media-frame" href="{escape(target, quote=True)}"{rel}>{image}</a>'
    caption = ''
    if context not in {'resource', 'compact'}:
        caption = f'<figcaption>{escape(media["caption"])} <span class="media-credit">{media_credit(media)}</span></figcaption>'
    return f'<figure class="editorial-media media-{media["kind"]} media-{context}">{frame}{caption}</figure>'
