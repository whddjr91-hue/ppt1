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
