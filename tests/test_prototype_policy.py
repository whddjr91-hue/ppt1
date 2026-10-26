"""Contract tests; these do not prove storyboard teaching quality."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prototype_guard", ROOT / ".claude/skills/storyboard-prototype/scripts/prototype_guard.py")
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)


class PrototypePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        proto = self.root / "contract-fixture.pptx"
        with zipfile.ZipFile(proto, "w") as z:
            z.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst><p:sldId id="256"/></p:sldIdLst><p:sldSz cx="9144000" cy="5143500"/></p:presentation>')
            z.writestr("ppt/slides/slide1.xml", '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:latin typeface="나눔바른고딕"/></p:sld>')
        (self.root / "source.txt").write_text("상담 서비스 동의와 연구 활용 동의는 구분해야 합니다.", encoding="utf-8")
        def entry(name):
            return {"path": name, "sha256": G.sha(self.root / name)}
        self.binding = {"schema_version": 1, "institution": "KIRD", "design_authority": "prototype_storyboard",
                        "prototype_storyboard": entry(proto.name), "prototype_manuscript": entry("source.txt"),
                        "manuscript": entry("source.txt"), "manuscript_text": entry("source.txt"),
                        "observed_profile": {"canvas_inches": [10, 5.625], "screen_font": "나눔바른고딕", "video_region": {"x": 1.43, "y": .73, "w": 6.75, "h": 3.76}},
                        "prototype_pages_reviewed": [1], "prototype_analysis": "원고와 화면의 동의 대상 및 구분 의미를 실제 프로토에서 읽고 확인한다.", "approved_change_ids": []}
        self.binding["manuscript_text"]["derived_from_sha256"] = self.binding["manuscript"]["sha256"]
        self.scene = {"page": 1, "scene_id": "SC01", "role": "diagram", "source_excerpt": "상담 서비스 동의와 연구 활용 동의는 구분해야 합니다.", "narration": "상담 서비스 동의와 연구 활용 동의는 구분해야 합니다.", "core_message": "두 동의는 대상이 달라 구분해야 한다.",
                      "meaning": {"subject": "동의 범위", "action": "대상 구분", "conditions": None, "conditions_not_applicable_reason": "조건을 열거하는 장면이 아님", "judgment": "두 동의 구분 필요"}, "prototype_pages": [1],
                      "nodes": [{"id": "counsel", "text": "상담 서비스 동의"}, {"id": "research", "text": "연구 활용 동의"}], "relation": {"kind": "contrast", "rationale": "동의한 목적이 다르므로 두 대상을 구분", "edges": [{"from": "counsel", "to": "research", "meaning": "목적 구분"}]},
                      "sync": [{"n": 1, "narration_quote": "상담 서비스 동의", "visual_targets": ["counsel"]}, {"n": 2, "narration_quote": "연구 활용 동의", "visual_targets": ["research"]}], "visual": {"editable_text_and_diagrams": True, "kind": "comparison", "hierarchy_rationale": "프로토와 같이 대상 라벨 두 개와 구분 판단을 분리"}, "assets": []}
        self.bp, self.sp = self.root / "binding.json", self.root / "scenes.json"
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.bp.write_text(json.dumps(self.binding, ensure_ascii=False), encoding="utf-8")
        self.sp.write_text(json.dumps({"scenes": [self.scene]}, ensure_ascii=False), encoding="utf-8")

    def test_valid_contract_is_not_automatic_quality_pass(self):
        r = G.preflight(self.bp, self.sp)
        self.assertTrue(r["contract_pass"])
        self.assertTrue(r["human_semantic_review_required"])
        self.assertFalse(r["educational_quality_automatically_verified"])

    def test_missing_or_changed_reference_blocks(self):
        self.binding["prototype_storyboard"]["sha256"] = "0" * 64
        self.save()
        with self.assertRaises(G.ContractError): G.preflight(self.bp, self.sp)

    def test_manuscript_from_different_project_blocks(self):
        self.scene["source_excerpt"] = "국내8개 연구기관이 재현 실험에 참여했다."
        self.save()
        with self.assertRaises(G.ContractError): G.preflight(self.bp, self.sp)

    def test_bare_word_without_meaning_fields_blocks(self):
        self.scene["meaning"] = {"subject": "8개 기관"}
        self.save()
        with self.assertRaises(G.ContractError): G.preflight(self.bp, self.sp)

    def test_sync_zero_or_unknown_target_blocks(self):
        for cue in [{"n": 0, "narration_quote": "상담 서비스 동의", "visual_targets": ["counsel"]}, {"n": 1, "narration_quote": "상담 서비스 동의", "visual_targets": ["missing"]}]:
            self.scene["sync"] = [cue]; self.save()
            with self.assertRaises(G.ContractError): G.preflight(self.bp, self.sp)

    def test_document_only_case_blocks_without_user_exception(self):
        self.scene["role"] = "case"; self.scene["visual"].update(full_video_region=True, kind="document_only")
        self.save()
        with self.assertRaises(G.ContractError): G.preflight(self.bp, self.sp)

    def test_unrelated_font_or_canvas_blocks(self):
        self.binding["observed_profile"]["screen_font"] = "Unrelated Font"
        self.save()
        with self.assertRaises(G.ContractError): G.preflight(self.bp, self.sp)

    def test_final_review_needs_both_human_roles_and_matching_render(self):
        artifact = self.root / "artifact.bin"; artifact.write_bytes(b"test artifact")
        render = self.root / "render.bin"; render.write_bytes(b"test render evidence")
        ah = G.sha(artifact)
        e = {"page": 1, "prototype_pages": [1], "render": {"path": str(render), "sha256": G.sha(render), "derived_from_sha256": ah}}
        for k in ["manuscript_facts", "learning_meaning", "prototype_visual", "sources_sync_editability"]:
            e[k] = {"status": "passed", "observation": "Test record only: reviewed the concrete labels and comparison meaning."}
        r = {"artifact": {"path": str(artifact), "sha256": ah}, "workflow_roles": [3,2,5,3,2,1], "prototype_sha256": self.binding["prototype_storyboard"]["sha256"], "reviews": [{"role": 2, "artifact_sha256": ah, "page_reviews": [e]}]}
        rp = self.root / "review.json"; rp.write_text(json.dumps(r))
        with self.assertRaises(G.ContractError): G.review(self.bp, self.sp, rp)
        r["reviews"].append({"role": 1, "artifact_sha256": ah, "page_reviews": [copy.deepcopy(e)]})
        rp.write_text(json.dumps(r)); self.assertTrue(G.review(self.bp, self.sp, rp)["manual_review_records_present"])
        r["reviews"][1]["page_reviews"][0]["render"]["derived_from_sha256"] = "0" * 64
        rp.write_text(json.dumps(r))
        with self.assertRaises(G.ContractError): G.review(self.bp, self.sp, rp)


if __name__ == "__main__":
    unittest.main()
