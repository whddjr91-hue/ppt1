"""Bounded stdlib regression tests for native reuse and dependency-aware scope."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from xml.dom import minidom
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'tools/advanced-production/scripts'


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scope = load('native_scope_test', SCRIPTS / 'pptx-scope.py')
reuse = load('native_reuse_test', SCRIPTS / 'reuse-prototype.py')
P, A, R, PK, CT = scope.P, scope.A, scope.R, scope.PK, scope.CT


def rels(rows):
    ET.register_namespace('', PK)
    root = ET.Element(f'{{{PK}}}Relationships')
    for rid, kind, target in rows:
        ET.SubElement(root, f'{{{PK}}}Relationship', Id=rid, Type=R + '/' + kind, Target=target)
    return ET.tostring(root)


def slide(text):
    return f'''<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>
<p:nvGrpSpPr><p:cNvPr id="1" name="root"/></p:nvGrpSpPr><p:grpSpPr/>
<p:sp><p:nvSpPr><p:cNvPr id="2" name="native text"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="123" y="456"/><a:ext cx="700" cy="800"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:p><a:r><a:rPr sz="1400" b="1"/><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>
<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="5" name="native table"/></p:nvGraphicFramePr><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>A</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>B</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>
<p:pic><p:nvPicPr><p:cNvPr id="8" name="native image"/></p:nvPicPr><p:blipFill><a:blip r:embed="image"/></p:blipFill></p:pic>
</p:spTree></p:cSld></p:sld>'''.encode()


def fixture(path):
    types = ET.Element(f'{{{CT}}}Types')
    for ext, kind in [('rels', 'application/vnd.openxmlformats-package.relationships+xml'), ('xml', 'application/xml'), ('png', 'image/png'), ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]:
        ET.SubElement(types, f'{{{CT}}}Default', Extension=ext, ContentType=kind)
    for part, kind in [('ppt/presentation.xml', 'presentationml.presentation.main'), ('ppt/slides/slide7.xml', 'presentationml.slide'), ('ppt/slides/slide3.xml', 'presentationml.slide'), ('ppt/notesSlides/notesSlide1.xml', 'presentationml.notesSlide'), ('ppt/charts/chart1.xml', 'drawingml.chart')]:
        ET.SubElement(types, f'{{{CT}}}Override', PartName='/' + part, ContentType='application/vnd.openxmlformats-officedocument.' + kind + '+xml')
    ET.register_namespace('', CT)
    files = {'[Content_Types].xml': ET.tostring(types),
             '_rels/.rels': rels([('doc', 'officeDocument', 'ppt/presentation.xml'), ('core', 'metadata/core-properties', 'docProps/core.xml')]),
             'docProps/core.xml': b'<core>unchanged global metadata</core>',
             'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="300" r:id="first"/><p:sldId id="301" r:id="second"/></p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/></p:presentation>'.encode(),
             'ppt/_rels/presentation.xml.rels': rels([('first', 'slide', 'slides/slide7.xml'), ('second', 'slide', 'slides/slide3.xml')]),
             'ppt/slides/slide7.xml': slide('첫째'), 'ppt/slides/slide3.xml': slide('둘째'),
             'ppt/slides/_rels/slide7.xml.rels': rels([('layout', 'slideLayout', '../slideLayouts/slideLayout1.xml'), ('image', 'image', '../media/shared.png'), ('chart', 'chart', '../charts/chart1.xml'), ('notes', 'notesSlide', '../notesSlides/notesSlide1.xml')]),
             'ppt/slides/_rels/slide3.xml.rels': rels([('layout', 'slideLayout', '../slideLayouts/slideLayout1.xml'), ('image', 'image', '../media/shared.png')]),
             'ppt/slideLayouts/slideLayout1.xml': b'<layout native="true"/>',
             'ppt/slideLayouts/_rels/slideLayout1.xml.rels': rels([('master', 'slideMaster', '../slideMasters/slideMaster1.xml')]),
             'ppt/slideMasters/slideMaster1.xml': b'<master native="true"/>',
             'ppt/slideMasters/_rels/slideMaster1.xml.rels': rels([('layout', 'slideLayout', '../slideLayouts/slideLayout1.xml'), ('theme', 'theme', '../theme/theme1.xml')]),
             'ppt/theme/theme1.xml': b'<theme>font and colors</theme>',
             'ppt/media/shared.png': b'unchanged native image bytes',
             'ppt/charts/chart1.xml': b'<chart native="true"/>',
             'ppt/charts/_rels/chart1.xml.rels': rels([('book', 'package', '../embeddings/book1.xlsx')]),
             'ppt/embeddings/book1.xlsx': b'embedded workbook bytes',
             'ppt/notesSlides/notesSlide1.xml': b'<notes>approved narration</notes>',
             'ppt/notesSlides/_rels/notesSlide1.xml.rels': rels([('slide', 'slide', '../slides/slide7.xml')])}
    write(path, files)
    return files


def write(path, files, compression=ZIP_DEFLATED):
    with ZipFile(path, 'w', compression) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


class NativeReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.source = self.dir / 'source.pptx'
        self.files = fixture(self.source)
        self.sha = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def job(self, pages, sha=None, name='job.json'):
        path = self.dir / name
        path.write_text(json.dumps({'reference': {'path': self.source.name, 'sha256': sha or self.sha}, 'pages': pages}), encoding='utf-8')
        return path

    def clone(self, pages):
        out = self.dir / 'clone.pptx'
        return out, reuse.reuse(self.job(pages), out)

    def test_native_clone_preserves_geometry_table_media_and_source(self):
        out, receipt = self.clone([{'source_page': 1}])
        pkg = scope.Package(out)
        self.assertEqual(len(pkg.slides), 1)
        self.assertEqual(pkg.parts[pkg.slides[0]['part']], self.files['ppt/slides/slide7.xml'])
        for part in ['ppt/media/shared.png', 'ppt/slideLayouts/slideLayout1.xml', 'ppt/slideMasters/slideMaster1.xml']:
            self.assertEqual(pkg.parts[part], self.files[part])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.sha)
        self.assertFalse(receipt['semantic_quality_pass'])
        self.assertTrue(receipt['human_semantic_review_required'])
        self.assertTrue(any(row['contains_table'] for row in receipt['pages'][0]['output_native_objects']))
        self.assertNotIn('showMasterSp', ET.fromstring(pkg.parts[pkg.slides[0]['part']]).attrib)

    def test_logical_order_and_repeated_pages_are_independent(self):
        out, receipt = self.clone([{'source_page': 2}, {'source_page': 1}, {'source_page': 1, 'text_replacements': [{'shape_id': '2', 'before': '첫째', 'after': '다른 말'}]}])
        pkg = scope.Package(out)
        texts = [reuse.native_objects(pkg.parts[row['part']])[0]['text'] for row in pkg.slides]
        self.assertEqual(texts, ['둘째', '첫째', '다른 말'])
        self.assertEqual([row['source_page'] for row in receipt['pages']], [2, 1, 1])

    def test_exact_text_and_native_table_edit_keep_run_properties(self):
        out, _ = self.clone([{'source_page': 1, 'text_replacements': [{'shape_id': '2', 'before': '첫째', 'after': '수정된 문장'}, {'shape_id': '5', 'before': 'A\tB', 'after': 'C\tD'}]}])
        pkg = scope.Package(out)
        root = ET.fromstring(pkg.parts[pkg.slides[0]['part']])
        self.assertEqual(root.find(f'.//{{{A}}}rPr').attrib, {'sz': '1400', 'b': '1'})
        objects = reuse.native_objects(pkg.parts[pkg.slides[0]['part']])
        self.assertEqual([row['text'] for row in objects if row['shape_id'] == '5'], ['C\tD'])

    def test_notes_backref_and_chart_workbook_closure(self):
        out, _ = self.clone([{'source_page': 1}])
        pkg = scope.Package(out)
        slide_part = pkg.slides[0]['part']
        closure = pkg.closure(slide_part)
        self.assertIn('ppt/embeddings/book1.xlsx', closure)
        self.assertEqual(pkg.parts['ppt/embeddings/book1.xlsx'], self.files['ppt/embeddings/book1.xlsx'])
        notes = next(row['target'] for row in pkg.relationships(slide_part) if row['type'].endswith('/notesSlide'))
        self.assertEqual(next(row['target'] for row in pkg.relationships(notes) if row['type'].endswith('/slide')), slide_part)
        self.assertNotIn('ppt/slides/slide7.xml', pkg.parts)
        self.assertNotIn('ppt/slides/slide3.xml', pkg.parts)

    def test_refuses_bad_hash_before_overwrite_and_topology(self):
        cases = [(self.job([{'source_page': 1}], '0' * 64), 'hash'),
                 (self.job([{'source_page': 1, 'text_replacements': [{'shape_id': '2', 'before': 'wrong', 'after': 'x'}]}], name='bad-before.json'), 'before'),
                 (self.job([{'source_page': 1, 'text_replacements': [{'shape_id': '2', 'before': '첫째', 'after': 'x\ny'}]}], name='bad-topology.json'), 'topology')]
        for job, reason in cases:
            with self.subTest(reason=reason):
                output = self.dir / (reason + '.pptx')
                with self.assertRaises(ValueError):
                    reuse.reuse(job, output)
                self.assertFalse(output.exists())
        existing = self.dir / 'existing.pptx'
        existing.write_bytes(b'do not overwrite')
        with self.assertRaises(ValueError):
            reuse.reuse(self.job([{'source_page': 1}], name='valid.json'), existing)
        self.assertEqual(existing.read_bytes(), b'do not overwrite')

    def test_scope_ignores_zip_recompression_but_never_semantic_pass(self):
        other = self.dir / 'other.pptx'
        write(other, self.files, ZIP_STORED)
        result = scope.compare(self.source, other, [])
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['changed_pages'], [])
        self.assertFalse(result['semantic_quality_pass'])

    def test_scope_single_page_edit_and_single_page_part_replacement(self):
        other = self.dir / 'other.pptx'
        files = dict(self.files)
        files['ppt/slides/slide7.xml'] = slide('수정')
        write(other, files)
        result = scope.compare(self.source, other, [1])
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['changed_pages'], [1])
        self.assertEqual(scope.compare(self.source, other, [])['unexpected_pages'], [1])
        # A replacement can use a new part at the declared logical position.
        files['ppt/slides/replacement.xml'] = files.pop('ppt/slides/slide3.xml')
        files['ppt/slides/_rels/replacement.xml.rels'] = files.pop('ppt/slides/_rels/slide3.xml.rels')
        files['ppt/_rels/presentation.xml.rels'] = files['ppt/_rels/presentation.xml.rels'].replace(b'slides/slide3.xml', b'slides/replacement.xml')
        files['[Content_Types].xml'] = files['[Content_Types].xml'].replace(b'/ppt/slides/slide3.xml', b'/ppt/slides/replacement.xml')
        write(other, files)
        self.assertTrue(scope.compare(self.source, other, [1, 2])['passed'])

    def test_scope_shared_media_affects_every_owner_page(self):
        other = self.dir / 'other.pptx'
        files = dict(self.files, **{'ppt/media/shared.png': b'changed media'})
        write(other, files)
        result = scope.compare(self.source, other, [1])
        self.assertFalse(result['passed'])
        self.assertEqual(result['changed_pages'], [1, 2])
        self.assertEqual(result['unexpected_pages'], [2])

    def test_scope_shared_theme_and_relationship_changes(self):
        other = self.dir / 'other.pptx'
        for part, data in [('ppt/theme/theme1.xml', b'<theme>changed</theme>'), ('ppt/slideMasters/_rels/slideMaster1.xml.rels', self.files['ppt/slideMasters/_rels/slideMaster1.xml.rels'].replace(b'Id="theme"', b'Id="newtheme"'))]:
            with self.subTest(part=part):
                files = dict(self.files)
                files[part] = data
                write(other, files)
                result = scope.compare(self.source, other, [1])
                self.assertEqual(result['unexpected_pages'], [2])
                self.assertFalse(result['passed'])

    def test_scope_detects_order_size_count_and_unknown_globals(self):
        other = self.dir / 'other.pptx'
        for mode in ['order', 'size', 'count', 'global']:
            with self.subTest(mode=mode):
                files = dict(self.files)
                root = ET.fromstring(files['ppt/presentation.xml'])
                if mode == 'order':
                    listing = root.find(f'{{{P}}}sldIdLst')
                    first = listing[0]
                    listing.remove(first)
                    listing.append(first)
                elif mode == 'size':
                    root.find(f'{{{P}}}sldSz').set('cx', '1')
                elif mode == 'count':
                    listing = root.find(f'{{{P}}}sldIdLst')
                    listing.remove(listing[-1])
                else:
                    files['docProps/core.xml'] = b'<core>undeclared global edit</core>'
                files['ppt/presentation.xml'] = ET.tostring(root)
                write(other, files)
                result = scope.compare(self.source, other, [1, 2])
                self.assertFalse(result['passed'], result)
                if mode == 'global':
                    self.assertIn('docProps/core.xml', result['unknown_global_changes'])
                elif mode == 'order':
                    self.assertTrue(result['slide_order_changed'])

    def test_scope_content_type_change_propagates_and_bad_zip_fails_closed(self):
        other = self.dir / 'other.pptx'
        files = dict(self.files)
        files['[Content_Types].xml'] = files['[Content_Types].xml'].replace(b'image/png', b'image/other')
        write(other, files)
        result = scope.compare(self.source, other, [1])
        self.assertEqual(result['unexpected_pages'], [2])
        other.write_bytes(b'invalid archive')
        self.assertFalse(scope.compare(self.source, other, [])['passed'])
        self.assertTrue(scope.compare(self.source, other, [])['errors'])

    def test_output_opc_uses_default_namespace_and_unprefixed_children(self):
        out, _ = self.clone([{'source_page': 1}])
        with ZipFile(out) as archive:
            for name in ['[Content_Types].xml'] + [name for name in archive.namelist() if name.endswith('.rels')]:
                document = minidom.parseString(archive.read(name))
                root = document.documentElement
                expected = CT if name == '[Content_Types].xml' else PK
                self.assertEqual(root.namespaceURI, expected)
                self.assertIsNone(root.prefix, name)
                self.assertEqual(root.getAttribute('xmlns'), expected)
                for child in root.childNodes:
                    if child.nodeType == child.ELEMENT_NODE:
                        self.assertIsNone(child.prefix, (name, child.tagName))
                        self.assertEqual(child.namespaceURI, expected)

    def test_mc_ignorable_requires_aliases_survive_changed_parts(self):
        mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
        p14 = 'http://schemas.microsoft.com/office/powerpoint/2010/main'
        a14 = 'http://schemas.microsoft.com/office/drawing/2010/main'
        files = dict(self.files)
        declaration = f'xmlns:mc="{mc}" xmlns:p14="{p14}" xmlns:a14="{a14}" mc:Ignorable="p14 a14"'
        files['ppt/slides/slide7.xml'] = files['ppt/slides/slide7.xml'].replace(b'<p:sld ', ('<p:sld ' + declaration + ' ').encode()).replace(
            b'</p:spTree>', b'<mc:AlternateContent><mc:Choice Requires="a14"><p:sp><p:nvSpPr><p:cNvPr id="90" name="extension fallback"/></p:nvSpPr><p:spPr/></p:sp></mc:Choice><mc:Fallback/></mc:AlternateContent></p:spTree>')
        files['ppt/presentation.xml'] = files['ppt/presentation.xml'].replace(b'<p:presentation ', ('<p:presentation ' + declaration + ' ').encode())
        write(self.source, files)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        job = self.job([{'source_page': 1, 'text_replacements': [{'shape_id': '2', 'before': '첫째', 'after': '보존된 선언'}]}], digest)
        out = self.dir / 'mc-clone.pptx'
        reuse.reuse(job, out)
        pkg = scope.Package(out)
        for part in [pkg.main, pkg.slides[0]['part']]:
            data = pkg.parts[part]
            bindings = dict(pair for _, pair in ET.iterparse(io.BytesIO(data), events=('start-ns',)))
            self.assertEqual(bindings['p14'], p14)
            self.assertEqual(bindings['a14'], a14)
            root = ET.fromstring(data)
            self.assertEqual(root.get('{' + mc + '}Ignorable'), 'p14 a14')
        edited = ET.fromstring(pkg.parts[pkg.slides[0]['part']])
        self.assertEqual(edited.find('.//{' + mc + '}Choice').get('Requires'), 'a14')
        # Refuse an actually undefined QName alias rather than silently emit it.
        root = ET.fromstring(f'<p:sld xmlns:p="{P}" xmlns:mc="{mc}" mc:Ignorable="undefined"/>')
        with self.assertRaises(ValueError):
            reuse._dump(root, f'<p:sld xmlns:p="{P}"/>'.encode(), 'test.xml')

    def test_cli_and_omitted_cross_slide_link_refusal(self):
        out = self.dir / 'cli.pptx'
        job = self.job([{'source_page': 2}])
        run = subprocess.run([sys.executable, str(SCRIPTS / 'reuse-prototype.py'), '--job', str(job), '--output', str(out)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['pages'], 1)
        files = dict(self.files)
        row = ET.fromstring(files['ppt/slides/_rels/slide7.xml.rels'])
        ET.SubElement(row, f'{{{PK}}}Relationship', Id='jump', Type=R + '/slide', Target='slide3.xml')
        files['ppt/slides/_rels/slide7.xml.rels'] = ET.tostring(row)
        write(self.source, files)
        job = self.job([{'source_page': 1}], hashlib.sha256(self.source.read_bytes()).hexdigest(), 'cross.json')
        with self.assertRaises(ValueError):
            reuse.reuse(job, self.dir / 'cross.pptx')


if __name__ == '__main__':
    unittest.main()
