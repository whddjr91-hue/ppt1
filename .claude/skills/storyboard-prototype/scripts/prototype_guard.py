"""Check prototype/scene/review evidence contracts; never auto-grade teaching quality."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(value, label):
    require(isinstance(value, str) and len(value.strip()) >= 2, f"Missing {label}")
    return value.strip()


def normalized(value):
    return re.sub(r"\s+", "", re.sub(r"#[0-9０-９]+", "", value))


def source(entry, base, label):
    require(isinstance(entry, dict), f"Missing {label}")
    path = Path(text(entry.get("path"), label + ".path"))
    path = path if path.is_absolute() else base / path
    require(path.is_file(), f"Source unavailable: {label}: {path}")
    require(re.fullmatch(r"[a-f0-9]{64}", entry.get("sha256", "")), f"Missing bound hash: {label}")
    require(sha(path) == entry["sha256"], f"Source changed: {label}")
    return path


def preflight(binding_path, scenes_path):
    binding_path = Path(binding_path).resolve()
    base = binding_path.parent
    b, plan = read_json(binding_path), read_json(scenes_path)
    require(b.get("schema_version") == 1, "Unsupported binding")
    require(b.get("institution") in ["KIRD", "KEDI"], "Specify institution separately")
    require(b.get("design_authority") == "prototype_storyboard", "Prototype must be design authority")
    p = source(b.get("prototype_storyboard"), base, "prototype_storyboard")
    require(p.suffix.lower() == ".pptx", "Bind native storyboard prototype")
    source(b.get("prototype_manuscript"), base, "prototype_manuscript")
    source(b.get("manuscript"), base, "current project manuscript")
    mt = source(b.get("manuscript_text"), base, "current project manuscript text")
    require(b["manuscript_text"].get("derived_from_sha256") == b["manuscript"]["sha256"], "Text not linked to current project manuscript")
    manuscript_text = normalized(mt.read_text(encoding="utf-8"))
    profile = b.get("observed_profile", {})
    with zipfile.ZipFile(p) as z:
        ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
        presentation = ET.fromstring(z.read("ppt/presentation.xml"))
        size = presentation.find("p:sldSz", ns)
        canvas = [int(size.get(k)) / 914400 for k in ["cx", "cy"]]
        pages = len(presentation.findall("p:sldIdLst/p:sldId", ns))
        fonts = set()
        for n in z.namelist():
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", n):
                for e in ET.fromstring(z.read(n)).iter():
                    if e.get("typeface"):
                        fonts.add(e.get("typeface"))
    require(len(profile.get("canvas_inches", [])) == 2 and all(abs(a - c) < .001 for a, c in zip(canvas, profile["canvas_inches"])), "Profile canvas differs from prototype")
    require(profile.get("screen_font") in fonts, "Screen font not found in prototype")
    region = profile.get("video_region", {})
    require(all(isinstance(region.get(k), (int, float)) for k in ["x", "y", "w", "h"]), "Measure prototype video region")
    require(region["w"] > 0 and region["h"] > 0 and region["x"] >= 0 and region["y"] >= 0 and region["x"] + region["w"] <= canvas[0] + .001 and region["y"] + region["h"] <= canvas[1] + .001, "Invalid video region")
    reviewed = b.get("prototype_pages_reviewed", [])
    require(reviewed and all(isinstance(n, int) and 1 <= n <= pages for n in reviewed), "Record actual prototype pages inspected")
    text(b.get("prototype_analysis"), "prototype analysis")
    scenes = plan.get("scenes", []) if isinstance(plan, dict) else plan
    require(isinstance(scenes, list) and scenes, "Scene plan is empty")
    page_ids = set()
    roles = {"case", "explanation", "diagram", "emphasis", "section", "quiz", "closing"}
    relation_types = {"context", "sequence", "contrast", "cause_effect", "hierarchy", "condition", "emphasis"}
    for s in scenes:
        page = s.get("page")
        require(isinstance(page, int) and page > 0 and page not in page_ids, "Duplicate/invalid scene page")
        page_ids.add(page)
        prefix = f"page{page}"
        require(s.get("role") in roles, prefix + ": classify scene role")
        excerpt = text(s.get("source_excerpt"), prefix + ": source excerpt")
        narration = text(s.get("narration"), prefix + ": narration")
        approved = s.get("approved_change_id") in b.get("approved_change_ids", [])
        require(normalized(excerpt) in manuscript_text, prefix + ": excerpt not in current manuscript")
        require(normalized(excerpt) == normalized(narration) or approved, prefix + ": narration changed without approved change")
        text(s.get("core_message"), prefix + ": learning message")
        meaning = s.get("meaning", {})
        for k in ["subject", "action", "conditions", "judgment"]:
            require((isinstance(meaning.get(k), str) and len(meaning[k].strip()) >= 2) or (meaning.get(k) is None and isinstance(meaning.get(k + "_not_applicable_reason"), str) and len(meaning[k + "_not_applicable_reason"].strip()) >= 4), prefix + ": missing meaning/justified absence: " + k)
        refs = s.get("prototype_pages", [])
        require(refs and all(n in reviewed for n in refs), prefix + ": prototype role reference not inspected")
        nodes = s.get("nodes", [])
        ids = [n.get("id") for n in nodes]
        require(nodes and all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), prefix + ": label actual screen objects")
        for node in nodes:
            text(node.get("text"), prefix + ": screen label")
        relation = s.get("relation", {})
        require(relation.get("kind") in relation_types, prefix + ": specify meaningful relation")
        text(relation.get("rationale"), prefix + ": relation rationale")
        for e in relation.get("edges", []):
            require(e.get("from") in ids and e.get("to") in ids, prefix + ": relation target missing")
            text(e.get("meaning"), prefix + ": relation meaning")
        cues = s.get("sync", [])
        require(cues and [c.get("n") for c in cues] == list(range(1, len(cues) + 1)), prefix + ": sync must start #1 and be consecutive")
        for c in cues:
            quote = text(c.get("narration_quote"), prefix + ": sync quote")
            require(normalized(quote) in normalized(narration), prefix + ": sync quote not in narration")
            require(c.get("visual_targets") and all(i in ids for i in c["visual_targets"]), prefix + ": sync target missing")
        visual = s.get("visual", {})
        require(visual.get("editable_text_and_diagrams") is True, prefix + ": declare native editability")
        if s["role"] == "case":
            require(visual.get("full_video_region") is True, prefix + ": case must use full video region")
            require(visual.get("kind") == "situation_scene" or approved, prefix + ": document-only case requires user-approved exception")
        text(visual.get("hierarchy_rationale"), prefix + ": prototype hierarchy")
        for a in s.get("assets", []):
            source(a, base, prefix + ": asset")
            for key in ["provider", "source_type", "rights_status", "visible_credit"]:
                text(a.get(key), prefix + ": asset " + key)
            require(a.get("url") or a.get("original_source_sha256") or a.get("creation_record"), prefix + ": missing provenance")
    return {"contract_pass": True, "prototype_sha256": b["prototype_storyboard"]["sha256"], "pages": sorted(page_ids), "human_semantic_review_required": True, "educational_quality_automatically_verified": False}


def review(binding_path, scenes_path, review_path):
    result = preflight(binding_path, scenes_path)
    r = read_json(review_path)
    base = Path(review_path).resolve().parent
    source(r.get("artifact"), base, "reviewed artifact")
    artifact_sha = r["artifact"]["sha256"]
    require(r.get("workflow_roles") == [3, 2, 5, 3, 2, 1], "Required workflow roles missing/out of order")
    require(r.get("prototype_sha256") == result["prototype_sha256"], "Review uses different prototype")
    for role in [2, 1]:
        reviewers = [v for v in r.get("reviews", []) if v.get("role") == role]
        require(reviewers, f"Missing role{role} direct review")
        reviewer = reviewers[-1]
        require(reviewer.get("artifact_sha256") == artifact_sha, f"role{role}: different artifact")
        evidence = {v.get("page"): v for v in reviewer.get("page_reviews", [])}
        require(set(result["pages"]) <= set(evidence), f"role{role}: unreviewed pages")
        for page in result["pages"]:
            e = evidence[page]
            source(e.get("render"), base, f"role{role}/page{page} render")
            require(e["render"].get("derived_from_sha256") == artifact_sha, "Render is not linked to reviewed artifact")
            binding = read_json(binding_path)
            require(e.get("prototype_pages") and all(n in binding["prototype_pages_reviewed"] for n in e["prototype_pages"]), "Record compared inspected prototype pages")
            for key in ["manuscript_facts", "learning_meaning", "prototype_visual", "sources_sync_editability"]:
                judgement = e.get(key, {})
                require(judgement.get("status") == "passed", f"role{role}/page{page}: {key} not passed")
                observation = text(judgement.get("observation"), "direct observation")
                require(len(observation) >= 12, "Use concrete observation, not PASS/checked")
    return {**result, "manual_review_records_present": True, "educational_quality_automatically_verified": False, "artifact_sha256": artifact_sha, "user_acceptance_verified": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["preflight", "review"])
    p.add_argument("--binding", required=True)
    p.add_argument("--scenes", required=True)
    p.add_argument("--review")
    a = p.parse_args()
    try:
        require(a.action != "review" or a.review, "--review required")
        r = preflight(a.binding, a.scenes) if a.action == "preflight" else review(a.binding, a.scenes, a.review)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError, ValueError, zipfile.BadZipFile, ET.ParseError, KeyError, TypeError) as e:
        print(json.dumps({"contract_pass": False, "error": str(e), "educational_quality_automatically_verified": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
