"""Check that add-on registration cannot replace existing skills or duplicate host tools."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


PATH = Path(__file__).resolve().parents[1] / "scripts/Manage-AdvancedTools.py"
SPEC = importlib.util.spec_from_file_location("advanced_tool_manager", PATH)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous_root = manager.ROOT
        manager.ROOT = self.root
        self.source = self.root / "vendor/skills/minimax-pptx-generator"
        self.source.mkdir(parents=True)
        (self.source / "SKILL.md").write_text("diagnostic skill source\n")

    def tearDown(self):
        manager.ROOT = self.previous_root
        self.temp.cleanup()

    def test_default_registration_does_not_duplicate_pdf_or_cli(self):
        manager.register()
        target = self.root / ".agents/skills"
        self.assertEqual({p.name for p in target.iterdir()}, {"pptx-generator"})

    def test_reregister_preserves_content(self):
        manager.register()
        manager.register()
        self.assertEqual((self.root / ".agents/skills/pptx-generator/SKILL.md").read_bytes(),
                         (self.source / "SKILL.md").read_bytes())

    def test_existing_different_skill_is_never_overwritten(self):
        target = self.root / ".agents/skills/pptx-generator"
        target.mkdir(parents=True)
        sentinel = target / "SKILL.md"
        sentinel.write_bytes(b"existing user skill - keep me")
        with self.assertRaises(FileExistsError):
            manager.register()
        self.assertEqual(sentinel.read_bytes(), b"existing user skill - keep me")


if __name__ == "__main__":
    unittest.main()
