"""Add prototype policy registrations/bindings without reinitializing the workspace."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def register(workspace):
    destinations = Path(workspace).resolve() / ".agents/skills"
    destinations.mkdir(parents=True, exist_ok=True)
    entries = {"storyboard-prototype": ROOT / ".claude/skills/storyboard-prototype",
               "pptx-generator": ROOT / "vendor/skills/minimax-pptx-generator",
               "ppt-master": ROOT / ".claude/skills/ppt-master"}
    result = []
    # Validate required bundles before writing any link.
    for name, source in entries.items():
        if not (source / "SKILL.md").is_file():
            raise FileNotFoundError(source / "SKILL.md")
    legacy = entries["ppt-master"]
    for rel in ["scripts/attribution_guard.py", "workflows/routing.md", "workflows/edit-native-pptx.md", "scripts/pptx_to_svg.py", "scripts/pptx_delivery_check.py"]:
        if not (legacy / rel).is_file():
            raise FileNotFoundError(legacy / rel)
    for name, source in entries.items():
        target = destinations / name
        if target.exists() or target.is_symlink():
            if target.resolve() == source.resolve():
                state = "existing matching link preserved"
            elif target.is_dir() and all((target / p.relative_to(source)).is_file() and (target / p.relative_to(source)).read_bytes() == p.read_bytes() for p in source.rglob("*") if p.is_file()):
                state = "existing matching copy preserved"
            else:
                raise FileExistsError(f"Different registration preserved without overwrite: {target}")
        else:
            try:
                target.symlink_to(os.path.relpath(source, destinations), target_is_directory=True)
                state = "registered link"
            except OSError:
                shutil.copytree(source, target)
                state = "registered new copy"
        result.append({"name": name, "path": str(target), "state": state})
    return {"registrations": result, "host_catalog_reload_verified": False, "existing_sessions_automatically_reloaded": False}


def bind(a):
    profile = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    def entry(p):
        f = Path(p).resolve()
        if not f.is_file():
            raise FileNotFoundError(f)
        return {"path": str(f), "sha256": digest(f)}
    b = {"schema_version": 1, "institution": a.institution, "design_authority": "prototype_storyboard",
         "prototype_storyboard": entry(a.prototype_pptx), "prototype_manuscript": entry(a.prototype_manuscript),
         "manuscript": entry(a.manuscript), "manuscript_text": entry(a.manuscript_text),
         "observed_profile": profile["observed_profile"], "prototype_pages_reviewed": profile["prototype_pages_reviewed"],
         "prototype_analysis": profile["prototype_analysis"], "approved_change_ids": [], "accepted_generated_outputs": []}
    b["manuscript_text"]["derived_from_sha256"] = b["manuscript"]["sha256"]
    if profile.get("prototype_storyboard_sha256") != b["prototype_storyboard"]["sha256"]:
        raise ValueError("Profile belongs to another prototype; do not substitute a generated deck")
    output = Path(a.output).resolve()
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != b:
            raise FileExistsError(f"Existing binding preserved; choose a new version: {output}")
        return {"binding": str(output), "state": "matching binding preserved"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"binding": str(output), "state": "created", "prototype_sha256": b["prototype_storyboard"]["sha256"]}


def check(workspace):
    workspace = Path(workspace).resolve()
    paths = ["AGENTS.md", "prototype-policy.json", ".claude/skills/storyboard-prototype/SKILL.md",
             ".claude/skills/storyboard-prototype/scripts/prototype_guard.py"]
    checks = {p: (ROOT / p).is_file() for p in paths}
    roles = {}
    for n in range(1, 6):
        candidates = list((ROOT / "prompts").glob(f"{n}세션_*.md"))
        roles[str(n)] = len(candidates) == 1 and "storyboard-prototype/SKILL.md" in candidates[0].read_text(encoding="utf-8")
    registrations = {n: (workspace / ".agents/skills" / n / "SKILL.md").is_file() for n in ["storyboard-prototype", "pptx-generator", "ppt-master"]}
    return {"project_files": checks, "role_loading_links": roles, "registrations": registrations,
            "passed": all(checks.values()) and all(roles.values()) and all(registrations.values()),
            "host_catalog_reload_verified": False, "prototype_binding_exists": (workspace / ".local/prototype-binding.json").is_file()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["register", "bind", "check"])
    p.add_argument("--workspace-root", default=str(ROOT))
    p.add_argument("--institution", choices=["KIRD", "KEDI"])
    for name in ["profile", "prototype-pptx", "prototype-manuscript", "manuscript", "manuscript-text"]:
        p.add_argument("--" + name)
    p.add_argument("--output", default=str(ROOT / ".local/prototype-binding.json"))
    a = p.parse_args()
    try:
        if a.action == "bind" and not all([a.institution, a.profile, a.prototype_pptx, a.prototype_manuscript, a.manuscript, a.manuscript_text]):
            p.error("bind requires institution/profile/prototype pair/current manuscript/text")
        r = register(a.workspace_root) if a.action == "register" else bind(a) if a.action == "bind" else check(a.workspace_root)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("passed", True) else 2
    except (OSError, ValueError) as e:
        print(json.dumps({"passed": False, "error": str(e)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
