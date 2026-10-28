#!/usr/bin/env python3
"""Extract structural observations from a PPTX. Human visual review remains required."""
import argparse
import hashlib
import json
from pathlib import Path
from pptx import Presentation
import pptx
from analysis_cache import cache_key, put, get

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def inventory(path):
    p = Presentation(path)
    pages = []
    for number, slide in enumerate(p.slides, 1):
        shapes = []
        def collect(shapes_):
          result = []
          for s in shapes_:
            item = {'type': str(s.shape_type), 'left': s.left, 'top': s.top,
                    'width': s.width, 'height': s.height, 'shape_id': s.shape_id,
                    'name': s.name, 'rotation': s.rotation}
            if s.has_text_frame:
                item['text'] = s.text
                item['fonts'] = sorted({r.font.name for para in s.text_frame.paragraphs
                                        for r in para.runs if r.font.name})
                item['runs'] = [{'text': r.text, 'font': r.font.name,
                                 'size_pt': r.font.size.pt if r.font.size else None,
                                 'bold': r.font.bold}
                                for para in s.text_frame.paragraphs for r in para.runs]
            # Raw theme/rgb colors, bullets, preset geometry, arrows and connectors
            # preserve evidence without guessing effective inherited appearance.
            tags = {'srgbClr', 'schemeClr', 'prstGeom', 'buChar', 'buAutoNum',
                    'headEnd', 'tailEnd', 'ln', 'solidFill', 'xfrm'}
            item['visual_properties'] = [{'tag': e.tag.rsplit('}', 1)[-1], 'attrs': dict(e.attrib)}
                                         for e in s._element.iter() if e.tag.rsplit('}', 1)[-1] in tags]
            if hasattr(s, 'image'):
                item['image_sha256'] = hashlib.sha256(s.image.blob).hexdigest()
                item['image_part'] = str(s.part.related_part(s._element.blipFill.blip.rEmbed).partname)
            if hasattr(s, 'shapes'):
                item['children'] = collect(s.shapes)
            if s.has_table:
                item['table'] = [[c.text for c in row.cells] for row in s.table.rows]
            item['has_chart'] = s.has_chart
            result.append(item)
          return result
        shapes = collect(slide.shapes)
        pages.append({'page': number, 'shapes': shapes})
    return {'sha256': sha(path), 'canvas_emu': [p.slide_width, p.slide_height],
            'pages': pages, 'visual_review_required': True,
            'limits': 'Includes grouped objects and raw formatting. Theme/inherited font/color resolution, page roles, instructor/video regions and educational meaning still require actual visual observations. This inventory is not an approved profile.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('pptx'); p.add_argument('--output', required=True)
    p.add_argument('--cache-dir', default=str(ROOT / '.local/prototype-cache'))
    args = p.parse_args()
    key = cache_key([args.pptx], [__file__, ROOT / 'prototype-policy.json'])
    key['pptx_library_version'] = pptx.__version__
    data = get(args.cache_dir, key)
    hit = data is not None
    if not hit:
        data = json.dumps(inventory(args.pptx), ensure_ascii=False).encode('utf-8')
    with Path(args.output).open('xb') as f:
        f.write(data)
    if not hit:
        put(args.cache_dir, key, args.output)
    print(json.dumps({'cache_hit': hit, 'sha256': sha(args.pptx), 'educational_quality_verified': False}))


if __name__ == '__main__': main()
