"""State/routing/gate regression tests, not evidence of educational quality."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import test_prototype_policy as fixtures
G = fixtures.G

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S = module("production_state_tests", "tools/advanced-production/scripts/production-state.py")
V = module("production_verify_tests", "tools/advanced-production/scripts/verify-production.py")


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()

    def test_role_scopes_and_complexity_are_explicit(self):
        self.assertEqual(S.route({"task_type":"simple", "changed_pages":[17], "semantic_change":False})["workflow_roles"], [3,1])
        normal = S.route({"task_type":"partial", "changed_pages":[17]})
        self.assertEqual(normal["active_roles"], [1,2,3])
        self.assertEqual(normal["models"]["3"]["reasoning"], "medium")
        rich = S.route({"task_type":"partial", "changed_pages":[17], "design_defects":["clipped label"], "new_assets":True, "complex_judgment":True})
        self.assertEqual(rich["active_roles"], [1,2,3,4,5])
        self.assertEqual(rich["models"]["3"]["reasoning"], "high")
        with self.assertRaises(ValueError): S.route({"task_type":"simple", "changed_pages":[17]})
        with self.assertRaises(ValueError): S.route({"task_type":"unknown"})

    def test_catalog_never_silently_substitutes_a_model(self):
        with self.assertRaises(ValueError): S.route({"task_type":"full"}, catalog={"models":[]})
        catalog = {"models":[{"slug":"gpt-6.1-sol", "supported_reasoning_levels":[{"effort":"medium"}]}]}
        self.assertTrue(S.route({"task_type":"full"},catalog=catalog)["model_catalog_verified"])
        with self.assertRaises(ValueError): S.route({"task_type":"full", "complex_judgment":True},catalog=catalog)

    def test_cache_reuses_and_invalidates_content_rules_and_payload(self):
        src = self.root / "input.txt"; src.write_text("source")
        rule = self.root / "rule.txt"; rule.write_text("rule1")
        calls = []
        def produce(): calls.append(1); return {"paragraphs":["approved narration"]}
        args = ("narration", {"manuscript":src}, produce, self.root / "cache", {"rule":rule})
        first, a = S.cached(*args); second, b = S.cached(*args)
        self.assertFalse(a["cache_hit"]); self.assertTrue(b["cache_hit"]); self.assertEqual(len(calls),1)
        # Corrupted approval payload cannot be adopted merely because the filename matches.
        file = Path(b["path"]); bad = S.read(file); bad["payload"] = {"unapproved":True}; S.atomic_json(file,bad)
        self.assertFalse(S.cached(*args)[1]["cache_hit"])
        rule.write_text("rule2"); self.assertNotEqual(S.cached(*args)[1]["key"], a["key"])
        src.write_text("changed manuscript"); self.assertFalse(S.cached(*args)[1]["cache_hit"])

    def test_paragraph_deletion_and_transitive_pages(self):
        a=[{"id":"P1","text":"a"},{"id":"P2","text":"b"}]
        b=[{"id":"P1","text":"a"}]
        scenes=[{"page":1,"paragraph_ids":["P1"]},{"page":2,"paragraph_ids":["P2"]},{"page":3,"depends_on_pages":[2]}]
        self.assertEqual(S.affected_paragraphs(a,b,scenes)["affected_pages"],[2,3])
        with self.assertRaises(ValueError): S.affected_paragraphs(a+a,b,scenes)

    def test_unmapped_new_paragraph_blocks_partial_reuse(self):
        result=S.affected_paragraphs([{"id":"P1","text":"a"}], [{"id":"P1","text":"a"},{"id":"NEW","text":"new section"}], [{"page":1,"paragraph_ids":["P1"]}])
        self.assertEqual(result["unmapped_changed_paragraph_ids"],["NEW"])
        self.assertFalse(result["partial_reuse_allowed"])

    def test_two_corrections_then_report_and_accepted_lock(self):
        state={}
        for _ in range(2): S.correction(state,"overlapping label","a"*64)
        with self.assertRaises(ValueError): S.correction(state,"overlapping label","a"*64)
        state["accepted"]=True
        with self.assertRaises(ValueError): S.correction(state,"new style idea","a"*64)


class ScopedGuardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PrototypePolicyTests(); self.fixture.setUp()
        self.root = self.fixture.root
        artifact = self.root / "artifact.pptx"; artifact.write_bytes((self.root / "contract-fixture.pptx").read_bytes())
        render = self.root / "render.bin"; render.write_bytes(b"reviewed render")
        self.artifact, self.render = artifact, render
        ah = G.sha(artifact)
        evidence = {"page":1,"prototype_pages":[1],"render":{"path":str(render),"sha256":G.sha(render),"derived_from_sha256":ah}}
        for k in ["manuscript_facts","learning_meaning","prototype_visual","sources_sync_editability"]:
            evidence[k]={"status":"passed","observation":"Contract fixture only: concrete comparison labels were checked."}
        self.review={"artifact":{"path":str(artifact),"sha256":ah},"workflow_roles":[3,2,5,3,2,1],"prototype_sha256":self.fixture.binding["prototype_storyboard"]["sha256"],"reviews":[{"role":r,"artifact_sha256":ah,"page_reviews":[copy.deepcopy(evidence)]}for r in [2,1]]}
        self.rp=self.root/"review.json"
    def tearDown(self):
        self.fixture.tearDown()
    def save(self):
        self.rp.write_text(json.dumps(self.review))
    def operation(self, kind):
        self.save(); baseline=self.root/"baseline.json"; baseline.write_bytes(self.rp.read_bytes())
        op={"task_type":kind,"semantic_change":False,"changed_pages":[1],"output_scope":"excerpt","source_pages":[1],"original":{"path":str(self.artifact),"sha256":G.sha(self.artifact)},"baseline_review":{"path":str(baseline),"sha256":G.sha(baseline)}}
        opfile=self.root/"operation.json"; opfile.write_text(json.dumps(op))
        self.review["operation"]={"path":str(opfile),"sha256":G.sha(opfile)}
        self.review["workflow_roles"] = [3,1] if kind=="simple" else [3,2,1]
        self.save(); return opfile

    def test_partial_contract_accepts_scoped_independent_review(self):
        self.operation("partial")
        out=G.review(self.fixture.bp,self.fixture.sp,self.rp)
        self.assertFalse(out["scope_check"]["whole_deck_preservation_verified"])
        self.assertFalse(out["educational_quality_automatically_verified"])

    def test_simple_no_semantics_needs_baseline_and_role1(self):
        self.operation("simple"); self.review["reviews"]=[self.review["reviews"][-1]]; self.save()
        self.assertTrue(G.review(self.fixture.bp,self.fixture.sp,self.rp)["manual_review_records_present"])
        self.review["reviews"]=[]; self.save()
        with self.assertRaises(G.ContractError): G.review(self.fixture.bp,self.fixture.sp,self.rp)

    def test_stale_baseline_or_manifest_cannot_reuse_review(self):
        opfile=self.operation("partial"); op=G.read_json(opfile); op["original"]["sha256"]="0"*64; opfile.write_text(json.dumps(op))
        with self.assertRaises(G.ContractError): G.review(self.fixture.bp,self.fixture.sp,self.rp)

    def test_invalid_baseline_page_or_missing_observation_blocks(self):
        opfile=self.operation("partial"); baseline=self.root/"baseline.json"
        original=G.read_json(baseline)
        for bad_page,remove_observation in [(999,False),(1,True)]:
            data=copy.deepcopy(original)
            for reviewer in data["reviews"]:
                e=reviewer["page_reviews"][0]; e["page"]=bad_page
                if remove_observation:e["learning_meaning"].pop("observation")
            baseline.write_text(json.dumps(data))
            op=G.read_json(opfile); op["baseline_review"]["sha256"]=G.sha(baseline); opfile.write_text(json.dumps(op))
            self.review["operation"]["sha256"]=G.sha(opfile); self.save()
            with self.assertRaises(G.ContractError): G.review(self.fixture.bp,self.fixture.sp,self.rp)

    def test_no_operation_cannot_skip_full_workflow(self):
        self.review["workflow_roles"]=[3,1]; self.save()
        with self.assertRaises(G.ContractError): G.review(self.fixture.bp,self.fixture.sp,self.rp)

    def job(self, role_samples=True):
        self.fixture.scene["scene_id"]="SC01"
        self.fixture.scene["visual"]["native_targets"]={"counsel":["1"],"research":["2"]}
        self.fixture.save()
        if role_samples:
            self.fixture.binding["prototype_role_samples"]={"diagram":[{"page":1,"render":{"path":str(self.render),"sha256":G.sha(self.render),"derived_from_sha256":self.fixture.binding["prototype_storyboard"]["sha256"]},"observation":"Fixture only: role sample comparison structure and fonts inspected."}]}
            self.fixture.save()
        job={"proto":{"width":10,"height":5.625,"font":{"face":"나눔바른고딕"},"reference":{"path":str(self.root/"contract-fixture.pptx"),"sha256":self.fixture.binding["prototype_storyboard"]["sha256"]}},"scenes":[{"sceneId":"SC01","narration":self.fixture.scene["narration"]}],"prototypePolicy":{"binding":str(self.fixture.bp),"scenes":str(self.fixture.sp),"stage":"pilot"},"templateReuse":{"pages":[{"source_page":1}]}}
        jp=self.root/"job.json"; jp.write_text(json.dumps(job)); return jp,job

    def test_pilot_requires_real_role_samples_and_native_reuse(self):
        jp,job=self.job(False)
        with self.assertRaises(V.G.ContractError): V.validate(jp)
        jp,job=self.job(True); self.assertTrue(V.validate(jp)["passed"])
        job.pop("templateReuse"); jp.write_text(json.dumps(job))
        with self.assertRaises(V.G.ContractError): V.validate(jp)

    def test_mass_production_blocks_missing_or_changed_pilot(self):
        jp,job=self.job(); job["prototypePolicy"]["stage"]="production"; jp.write_text(json.dumps(job))
        with self.assertRaises(V.G.ContractError): V.validate(jp)

        self.review["manuscript_sha256"]=self.fixture.binding["manuscript"]["sha256"]; self.save()
        pilot=self.root/"pilot-scenes.json"; pilot.write_bytes(self.fixture.sp.read_bytes())
        job["prototypePolicy"]["pilot"]={"scenes":{"path":str(pilot),"sha256":G.sha(pilot)},"review":{"path":str(self.rp),"sha256":G.sha(self.rp)}}; jp.write_text(json.dumps(job))
        self.assertTrue(V.validate(jp)["passed"])
        changed=G.read_json(pilot); changed["scenes"][0]["core_message"]="Different storyboard plan"; pilot.write_text(json.dumps(changed))
        with self.assertRaises(V.G.ContractError): V.validate(jp)

    def test_actual_clone_must_contain_approved_narration(self):
        jp,job=self.job()
        receipt=self.root/"clone-receipt.json"
        receipt.write_text(json.dumps({"pages":[{"output_native_objects":[{"shape_id":"9","text":"Old prototype lesson script"}]}]}))
        with self.assertRaises(V.G.ContractError): V.validate_output(jp,receipt)
        receipt.write_text(json.dumps({"pages":[{"output_native_objects":[{"shape_id":"9","text":job["scenes"][0]["narration"]}, *[{"shape_id":str(i+1),"kind":"sp","text":n["text"],"top_level_bounds_emu":{"x":"100","y":"100","cx":"1000","cy":"1000"}} for i,n in enumerate(self.fixture.scene["nodes"])]]}]}))
        self.assertTrue(V.validate_output(jp,receipt)["native_narration_verified"])
        output=G.read_json(receipt)
        output["pages"][0]["output_native_objects"][1]["text"]="Unrelated on-screen lesson"
        receipt.write_text(json.dumps(output))
        with self.assertRaises(V.G.ContractError): V.validate_output(jp,receipt)


if __name__ == "__main__":
    unittest.main()
