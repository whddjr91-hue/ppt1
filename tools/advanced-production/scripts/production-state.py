"""Local scope planning, content-addressed analysis and bounded correction state.

No model/network calls. Cache hits and XML measurements are not visual acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import posixpath

ROOT = Path(__file__).resolve().parents[3]
NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
PK = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def rules():
    # A rule/prompt change invalidates old extraction/review payloads too.
    paths = [ROOT / "prototype-policy.json", ROOT / "AGENTS.md", Path(__file__)]
    paths += sorted((ROOT / "prompts").rglob("*.md"))
    paths += [ROOT / "docs" / n for n in ["작업범위와재사용.md", "제작기준.md", "세션운영.md", "검수보고서기준.md", "고급도구추가.md"]]
    paths += sorted((ROOT / ".claude/skills/storyboard-prototype").rglob("*.json"))
    paths += sorted((ROOT / "tools/advanced-production/scripts").glob("*.py"))
    paths += sorted((ROOT / "tools/advanced-production/src").glob("*.mjs"))
    paths += [ROOT / "tools/advanced-production/scripts/build.mjs"]
    paths += sorted((ROOT / ".claude/skills/storyboard-prototype").rglob("*.py"))
    paths += sorted((ROOT / ".claude/skills/storyboard-prototype").rglob("*.md"))
    return {str(p.relative_to(ROOT)): digest(p) for p in paths if p.is_file()}


def cache_identity(kind, sources, extra_rules=None):
    inputs = {k: {"path": str(Path(v).resolve()), "sha256": digest(v)}
              for k, v in sorted(sources.items())}
    rule_hashes = {**rules(), **{f"extra:{k}": digest(v) for k, v in (extra_rules or {}).items()}}
    identity = {"schema": 1, "kind": kind, "inputs": inputs, "rules": rule_hashes}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return key, identity


def cached(kind, sources, producer, cache_dir=None, extra_rules=None):
    key, identity = cache_identity(kind, sources, extra_rules)
    location = Path(cache_dir or ROOT / ".local/production-cache") / (key + ".json")
    if location.exists():
        try:
            old = read(location)
            payload_hash = hashlib.sha256(json.dumps(old["payload"], sort_keys=True).encode()).hexdigest()
            if old["identity"] == identity and old["payload_sha256"] == payload_hash:
                return old["payload"], {"cache_hit": True, "key": key, "path": str(location)}
        except (ValueError, KeyError, TypeError):
            pass  # Recompute corrupt cache; never silently adopt it.
    payload = producer()
    atomic_json(location, {"identity": identity, "payload": payload,
                           "payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()})
    return payload, {"cache_hit": False, "key": key, "path": str(location)}


def measure_pptx(path):
    """Measure real local OOXML, including the usually missed inherited board frames."""
    def elements(xml):
        root = ET.fromstring(xml)
        result = []
        tree = root.find("p:cSld/p:spTree", NS)
        for e in list(tree)[2:] if tree is not None else []:
            ident = e.find(".//p:cNvPr", NS)
            result.append({"kind": e.tag.rsplit("}", 1)[-1],
                           "id": ident.get("id") if ident is not None else None,
                           "name": ident.get("name") if ident is not None else None,
                           "text": "\n".join(t.text or "" for t in e.findall(".//a:t", NS)),
                           "geometry": [dict(x.attrib) for x in e.iter() if x.tag.rsplit("}", 1)[-1] in ["off", "ext", "chOff", "chExt", "prstGeom"]],
                           "font_runs": [dict(x.attrib) for x in e.iter() if x.tag.rsplit("}", 1)[-1] in ["rPr", "defRPr", "latin", "ea", "cs"]],
                           "colors": [{"kind": x.tag.rsplit("}", 1)[-1], **x.attrib} for x in e.iter() if x.tag.rsplit("}", 1)[-1] in ["schemeClr", "srgbClr", "sysClr"]],
                           "bullets_and_connectors": [{"kind": x.tag.rsplit("}", 1)[-1], **x.attrib} for x in e.iter() if x.tag.rsplit("}", 1)[-1].startswith("bu") or x.tag.rsplit("}", 1)[-1] in ["stCxn", "endCxn", "headEnd", "tailEnd"]]})
        return result
    with ZipFile(path) as z:
        pres = ET.fromstring(z.read("ppt/presentation.xml"))
        rels = ET.fromstring(z.read("ppt/_rels/presentation.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels}
        pages = []
        for n, e in enumerate(pres.findall("p:sldIdLst/p:sldId", NS), 1):
            target = targets[e.get("{" + NS["r"] + "}id")]
            part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("ppt/" + target)
            pages.append({"page": n, "part": part, "objects": elements(z.read(part)), "page_role": None})
        inherited = {name: {"part_sha256": hashlib.sha256(z.read(name)).hexdigest(), "objects": elements(z.read(name))}
                     for name in z.namelist() if name.endswith(".xml") and name.startswith(("ppt/slideLayouts/", "ppt/slideMasters/"))}
        themes = {name: z.read(name).decode("utf-8") for name in z.namelist() if name.startswith("ppt/theme/") and name.endswith(".xml")}
        size = pres.find("p:sldSz", NS)
        return {"source_sha256": digest(path), "size_emu": dict(size.attrib), "pages": pages,
                "inherited_parts": inherited, "theme_xml": themes,
                "visual_quality_verified": False, "human_required": ["page role", "title/body hierarchy", "icon semantics/style", "equivalent-role samples and full-size render", "narration/instructions regions and inherited frames"]}


def route(task, policy=None, catalog=None):
    policy = policy or read(ROOT / "prototype-policy.json")
    kind = task.get("task_type")
    if kind not in policy["task_profiles"]:
        raise ValueError("task_type must be simple, partial or full")
    if kind == "simple" and task.get("semantic_change") is not False:
        raise ValueError("Simple edits require explicit semantic_change=false; otherwise use partial")
    pages = task.get("changed_pages", [])
    if kind != "full" and (not pages or any(type(p) is not int or p < 1 for p in pages)):
        raise ValueError("Changed logical page numbers required")
    roles = list(policy["task_profiles"][kind]["workflow_roles"])
    if kind == "partial" and task.get("design_defects"):
        roles = [3, 2, 5, 3, 2, 1]
    model = policy["model_routing"]["model"]
    efforts = set()
    if catalog:
        models = catalog.get("models", []) if isinstance(catalog, dict) else catalog
        match = next((m for m in models if m.get("slug") == model), None)
        if not match:
            raise ValueError("Configured model absent from the actual local catalog")
        efforts = {e["effort"] for e in match.get("supported_reasoning_levels", [])}
    effort = "high" if task.get("complex_judgment") else "medium"
    if catalog and effort not in efforts:
        raise ValueError("Requested reasoning level unsupported by actual catalog")
    return {"task_type": kind, "workflow_roles": roles,
            "active_roles": sorted(set(roles) | ({4} if task.get("new_assets") else set())),
            "review_pages": sorted(set(pages + task.get("dependent_pages", []))),
            "models": {str(r): {"model": model, "reasoning": effort, "local_tools_first": r in [2, 3, 4, 5]}
                       for r in sorted(set(roles) | ({4} if task.get("new_assets") else set()))},
            "model_catalog_verified": bool(catalog), "actual_backend_model_changed": False,
            "max_auto_corrections": policy["max_auto_corrections"],
            "credit_savings_verified": False}


def affected_paragraphs(before, after, scenes):
    def indexed(items):
        result = {p["id"]: p for p in items}
        if len(result) != len(items):
            raise ValueError("Duplicate stable paragraph ID")
        return result
    a, b = indexed(before), indexed(after)
    changed = {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    mapped = {p for s in scenes for p in s.get("paragraph_ids", [])}
    unmapped = changed - mapped
    pages = {s["page"] for s in scenes if changed.intersection(s.get("paragraph_ids", []))}
    while True:
        expanded = pages | {s["page"] for s in scenes if pages.intersection(s.get("depends_on_pages", []))}
        if pages == expanded:
            break
        pages = expanded
    return {"changed_paragraph_ids": sorted(changed), "affected_pages": sorted(pages),
            "unmapped_changed_paragraph_ids": sorted(unmapped), "partial_reuse_allowed": not unmapped,
            "requires_new_manuscript_binding": bool(changed)}


def correction(state, defect_id, artifact_sha, resolved=False):
    if not defect_id or len(artifact_sha) != 64:
        raise ValueError("Concrete defect ID and input artifact SHA required")
    if state.get("accepted"):
        raise ValueError("Accepted artifact is locked; new user scope requires a new operation")
    if resolved:
        state["resolved"] = sorted(set(state.get("resolved", [])) | {defect_id})
        return state
    if state.get("attempts", 0) >= 2:
        raise ValueError("Two corrections exhausted: report cause to user before further execution")
    state["attempts"] = state.get("attempts", 0) + 1
    state.setdefault("changes", []).append({"defect_id": defect_id, "input_sha256": artifact_sha})
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    a = sub.add_parser("analyze-prototype"); a.add_argument("input"); a.add_argument("--output", required=True); a.add_argument("--cache-dir")
    a = sub.add_parser("cache"); a.add_argument("--kind", required=True); a.add_argument("--sources", required=True, help="JSON name:path map"); a.add_argument("--payload", required=True, help="Existing analysis/approved narration/source ledger JSON"); a.add_argument("--output", required=True); a.add_argument("--cache-dir")
    a = sub.add_parser("plan"); a.add_argument("--task", required=True); a.add_argument("--catalog"); a.add_argument("--output", required=True)
    a = sub.add_parser("diff-manuscript"); a.add_argument("--before", required=True); a.add_argument("--after", required=True); a.add_argument("--scenes", required=True); a.add_argument("--output", required=True)
    a = sub.add_parser("correction"); a.add_argument("--state", required=True); a.add_argument("--defect", required=True); a.add_argument("--artifact", required=True); a.add_argument("--resolved", action="store_true")
    a = sub.add_parser("usage"); a.add_argument("--event", required=True); a.add_argument("--log", required=True)
    args = p.parse_args()
    try:
        if args.action == "analyze-prototype":
            start = time.perf_counter()
            payload, hit = cached("prototype-measurements", {"prototype": args.input}, lambda: measure_pptx(args.input), args.cache_dir)
            result = {**payload, "cache": hit, "local_elapsed_seconds": time.perf_counter() - start}
        elif args.action == "cache":
            sources = read(args.sources)
            # Payload itself is fingerprinted: edited approvals cannot reuse a stale value.
            sources["analysis_payload"] = args.payload
            payload, hit = cached(args.kind, sources, lambda: read(args.payload), args.cache_dir)
            result = {"payload": payload, "cache": hit, "educational_quality_automatically_verified": False}
        elif args.action == "plan":
            result = route(read(args.task), catalog=read(args.catalog) if args.catalog else None)
        elif args.action == "diff-manuscript":
            result = affected_paragraphs(read(args.before), read(args.after), read(args.scenes))
        elif args.action == "correction":
            result = correction(read(args.state) if Path(args.state).exists() else {}, args.defect, digest(args.artifact), args.resolved)
            atomic_json(args.state, result)
        else:
            event = read(args.event)
            actual = event.get("actual_usage")
            if actual is not None:
                proof = event.get("usage_evidence", {})
                if not proof.get("path") or digest(proof["path"]) != proof.get("sha256"):
                    raise ValueError("Actual token/credit numbers require a current provider usage log hash")
            event["actual_usage"] = actual  # Unknown stays null; never infer it from role count.
            log = Path(args.log); log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            result = {"recorded": True, "actual_usage_known": actual is not None}
        if getattr(args, "output", None):
            atomic_json(args.output, result)
        print(json.dumps(result if args.action not in ["analyze-prototype", "cache"] else {"cache": result["cache"], "quality_verified": False}, ensure_ascii=False))
        return 2 if args.action == "diff-manuscript" and not result["partial_reuse_allowed"] else 0
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as e:
        print(json.dumps({"passed": False, "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
