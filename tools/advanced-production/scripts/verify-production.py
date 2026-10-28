"""Fail-closed production gate. Local contracts never auto-grade teaching quality."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("guard", ROOT / ".claude/skills/storyboard-prototype/scripts/prototype_guard.py")
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


def validate(job_path):
    job_path = Path(job_path).resolve()
    job = G.read_json(job_path)
    base = job_path.parent
    settings = job.get("prototypePolicy", {})
    def path(name):
        value = settings.get(name)
        G.require(value, "Production requires prototypePolicy." + name)
        return (base / value).resolve()
    binding_path, scenes_path = path("binding"), path("scenes")
    preflight = G.preflight(binding_path, scenes_path)
    binding = G.read_json(binding_path)
    plan = G.read_json(scenes_path)
    scenes = plan if isinstance(plan, list) else plan["scenes"]
    proto = job["proto"]
    reference = G.source(proto.get("reference"), base, "build prototype")
    G.require(G.sha(reference) == preflight["prototype_sha256"], "Build uses another prototype")
    G.require(proto.get("font", {}).get("face") == binding["observed_profile"]["screen_font"], "Build font differs from measured prototype")
    G.require(all(abs(a-b) < .001 for a,b in zip([proto.get("width", 0), proto.get("height", 0)], binding["observed_profile"]["canvas_inches"])), "Build size differs from prototype")
    G.require(len(job["scenes"]) == len(scenes), "Build and bound plan counts differ")
    samples = binding.get("prototype_role_samples", {})
    for built, planned in zip(job["scenes"], scenes):
        G.require(planned.get("scene_id") and built.get("sceneId") == planned["scene_id"], "Build scene identity differs")
        G.require(G.normalized(built["narration"]) == G.normalized(planned["narration"]), "Build narration differs")
        matched = samples.get(planned["role"], [])
        G.require(matched, "Missing actual equivalent-role prototype samples: " + planned["role"])
        for sample in matched:
            G.require(sample["page"] in binding["prototype_pages_reviewed"], "Sample was not inspected")
            G.source(sample.get("render"), binding_path.parent, "actual prototype sample render")
            G.require(sample["render"].get("derived_from_sha256") == preflight["prototype_sha256"], "Sample render belongs to another prototype")
            G.require(len(G.text(sample.get("observation"), "sample observation")) >= 12, "Record actual visual observations")
        G.require(set(planned["prototype_pages"]).intersection(s["page"] for s in matched), "Scene does not use an equivalent-role sample")
        targets = planned.get("visual", {}).get("native_targets", {})
        G.require(all(isinstance(targets.get(n["id"]), list) and targets[n["id"]]
                      and all(isinstance(i, str) for i in targets[n["id"]]) for n in planned["nodes"]),
                  "Map each planned node to actual native shape IDs before producing clones")
    reuse = job.get("templateReuse")
    G.require(reuse and len(reuse.get("pages", [])) == len(scenes), "Production must reuse actual native pages; generic addScene chrome is diagnostic only. Existing native editing path remains available.")
    for reused, scene in zip(reuse["pages"], scenes):
        G.require(reused.get("source_page") in scene["prototype_pages"], "Native page does not match scene's prototype role")
    stage = settings.get("stage", "production")
    G.require(stage in ["pilot", "production"], "Unknown production stage")
    task_type = "full"
    if settings.get("operation"):
        op_file = G.source(settings["operation"], base, "operation")
        op = G.read_json(op_file)
        task_type = op["task_type"]
        G.local_module("production_state", "tools/advanced-production/scripts/production-state.py").route(op)
        G.require(task_type == "full" or op.get("output_scope") == "excerpt", "Full-deck edits must use original native edit path plus scope guard, not a newly cloned deck")
    if stage == "pilot":
        G.require(1 <= len(scenes) <= 3, "Pilot is limited to 1–3 representative pages")
    elif task_type == "full":
        pilot = settings.get("pilot") or {}
        pilot_scenes_path = G.source(pilot.get("scenes"), base, "pilot scenes")
        pilot_review_path = G.source(pilot.get("review"), base, "pilot review")
        pilot_scenes = G.read_json(pilot_scenes_path)
        pilot_scenes = pilot_scenes if isinstance(pilot_scenes, list) else pilot_scenes["scenes"]
        G.require(1 <= len(pilot_scenes) <= 3, "Pilot must be bounded")
        G.require(all(s in scenes for s in pilot_scenes), "Pilot plan changed or not part of this manuscript plan")
        critical = {s["role"] for s in scenes}.intersection({"case", "diagram"})
        G.require(critical <= {s["role"] for s in pilot_scenes}, "Pilot omitted case/diagram quality samples")
        reviewed = G.read_json(pilot_review_path)
        G.require(reviewed.get("manuscript_sha256") == binding["manuscript"]["sha256"], "Pilot used a different manuscript")
        G.review(binding_path, pilot_scenes_path, pilot_review_path)
    return {"passed": True, "stage": stage, "prototype_sha256": preflight["prototype_sha256"],
            "reference_path": str(reference), "educational_quality_automatically_verified": False}


def validate_output(job_path, receipt_path):
    """Do not mistake a good plan for a correctly populated native clone."""
    job, receipt = G.read_json(job_path), G.read_json(receipt_path)
    plan_path = Path(job_path).resolve().parent / job["prototypePolicy"]["scenes"]
    plan = G.read_json(plan_path)
    scenes = plan if isinstance(plan, list) else plan["scenes"]
    pages = receipt.get("pages", [])
    G.require(len(pages) == len(job["scenes"]), "Native output has wrong page count")
    for built, planned, page in zip(job["scenes"], scenes, pages):
        texts = [G.normalized(o["text"]) for o in page["output_native_objects"] if o.get("text")]
        G.require(any(G.normalized(built["narration"]) in t for t in texts), "Approved narration is absent from the actual native output; replace the prototype's old script")
        objects = {o["shape_id"]: o for o in page["output_native_objects"]}
        visual = planned.get("visual", {})
        for node in planned["nodes"]:
            ids = visual.get("native_targets", {}).get(node["id"], [])
            G.require(ids and all(i in objects for i in ids), "Planned screen object is absent from native output")
            targets = [objects[i] for i in ids]
            for obj in targets:
                bounds = obj.get("top_level_bounds_emu") or {}
                G.require(all(k in bounds for k in ["x", "y", "cx", "cy"]), "Native target needs measured screen bounds")
                x,y,w,h = [int(bounds[k]) for k in ["x", "y", "cx", "cy"]]
                G.require(x < job["proto"]["width"] * 914400 and y < job["proto"]["height"] * 914400 and x+w > 0 and y+h > 0,
                          "Screen target points at an off-screen script/instruction box")
            if any(o.get("text") for o in targets):
                screen = G.normalized(" ".join(o.get("text") or "" for o in targets))
                G.require(G.normalized(node["text"]) in screen, "Actual screen label differs from approved node")
            else:
                G.require(all(o["kind"] == "pic" for o in targets), "Unlabelled shapes cannot stand in for a meaningful node")
                G.require(len(G.text(visual.get("image_target_rationale", {}).get(node["id"]), "image target rationale")) >= 12,
                          "Image targets need a concrete subject/action rationale and manual visual review")
    return {"passed": True, "native_narration_verified": True,
            "educational_quality_automatically_verified": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--receipt")
    args = p.parse_args()
    try:
        print(json.dumps(validate_output(args.job, args.receipt) if args.receipt else validate(args.job), ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as e:
        print(json.dumps({"passed": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(2)
