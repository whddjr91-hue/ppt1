import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compare_pptx', ROOT / 'scripts/compare_pptx.py')
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)


def archive(path, slide=b'a', master=b'x'):
    with ZipFile(path, 'w') as z:
        z.writestr('ppt/slides/slide1.xml', slide)
        z.writestr('ppt/slideMasters/slideMaster1.xml', master)


class CompareTests(unittest.TestCase):
    def test_root_presentation_switch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'root-switch.pptx'
            with ZipFile(p, 'w') as z:
                z.writestr('_rels/.rels', '<Relationships><Relationship Type="x/officeDocument" Target="alternate.xml"/></Relationships>')
                z.writestr('alternate.xml', '<presentation/>')
            with self.assertRaises(ValueError): C.page_dependencies(p)

    def test_shared_media_changes_only_its_actual_ordered_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a.pptx', Path(tmp) / 'b.pptx'
            def write(path, image):
                with ZipFile(path, 'w') as z:
                    z.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="b"/><p:sldId id="257" r:id="a"/></p:sldIdLst></p:presentation>')
                    z.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship Id="a" Target="slides/slide1.xml"/><Relationship Id="b" Target="slides/slide9.xml"/></Relationships>')
                    z.writestr('ppt/slides/slide1.xml', '<slide/>')
                    z.writestr('ppt/slides/slide9.xml', '<slide/>')
                    z.writestr('ppt/slides/_rels/slide9.xml.rels', '<Relationships><Relationship Id="pic" Target="../media/image1.png"/></Relationships>')
                    z.writestr('ppt/media/image1.png', image)
            write(a, b'original'); write(b, b'changed')
            result = C.compare(a, b)
            self.assertEqual(result['changed_slide_part_numbers'], [])
            self.assertEqual(result['affected_pages'], [1])
            self.assertEqual(result['unchanged_pages'], [2])

    def test_slide_and_shared_change_are_distinguished(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a.pptx', Path(tmp) / 'b.pptx'
            archive(a); archive(b, slide=b'b')
            result = C.compare(a, b)
            self.assertEqual(result['changed_slide_part_numbers'], [1])
            self.assertFalse(result['requires_global_dependency_review'])
            archive(b, slide=b'b', master=b'y')
            result = C.compare(a, b)
            self.assertTrue(result['requires_global_dependency_review'])
            self.assertIn('ppt/slideMasters/slideMaster1.xml', result['shared_or_other_changed_parts'])


if __name__ == '__main__': unittest.main()
