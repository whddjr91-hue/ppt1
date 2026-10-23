"""Manage only the additive tool bundle. Never invokes legacy workspace initialization."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run([str(v) for v in args], check=True, **kwargs)


def document_python():
    directory = ROOT / ".local/advanced-documents-venv"
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def register(pdf_fallback=False, playwright_fallback=False):
    entries = {
        "pptx-generator": "vendor/skills/minimax-pptx-generator",
    }
    if playwright_fallback:
        entries["playwright"] = "vendor/skills/openai-playwright"
    if pdf_fallback:
        entries["openai-pdf"] = "vendor/skills/openai-pdf"
    destination = ROOT / ".agents/skills"
    destination.mkdir(parents=True, exist_ok=True)
    result = []
    for name, relative in entries.items():
        source = ROOT / relative
        if not (source / "SKILL.md").is_file():
            raise FileNotFoundError(source / "SKILL.md")
        target = destination / name
        if target.exists() or target.is_symlink():
            if target.is_symlink() and target.resolve() == source.resolve():
                state = "existing matching registration preserved"
            elif target.is_dir() and not target.is_symlink():
                source_files = {p.relative_to(source): p for p in source.rglob("*") if p.is_file()}
                target_files = {p.relative_to(target): p for p in target.rglob("*") if p.is_file()}
                if set(source_files) != set(target_files) or any(
                    source_files[p].read_bytes() != target_files[p].read_bytes() for p in source_files
                ):
                    raise FileExistsError(f"Different existing registration preserved: {target}")
                state = "existing matching local copy preserved"
            else:
                raise FileExistsError(f"Registration already exists; preserved without overwrite: {target}")
        else:
            try:
                target.symlink_to(os.path.relpath(source, destination), target_is_directory=True)
                state = "registered via local link"
            except OSError:
                # Windows without symlink permission: new copy only, never overwrite.
                shutil.copytree(source, target)
                state = "registered via new local copy"
        result.append({"name": name, "path": str(target), "status": state})
    return result


def install_documents():
    executable = document_python()
    if not executable.is_file():
        directory = executable.parent.parent
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(directory)
    lock = ROOT / "tools/advanced-documents/requirements.lock"
    uv = shutil.which("uv")
    if uv:
        run([uv, "pip", "install", "--python", executable, "--require-hashes", "-r", lock])
    else:
        run([executable, "-m", "pip", "install", "--require-hashes", "-r", lock])


def install_production():
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("Node.js/npm required; existing runtime is not modified")
    run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        cwd=ROOT / "tools/advanced-production")


def install_browser_cli():
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node:
        raise RuntimeError("Node.js required; existing runtime is not modified")
    probe = subprocess.run([node, str(ROOT / "tools/advanced-browser/playwright-cli.cjs"), "--runtime-info"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        print("Matching existing Playwright runtime reused; no duplicate npm install")
        return
    if not npm:
        raise RuntimeError("npm required only to install a missing pinned local runtime")
    run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        cwd=ROOT / "tools/advanced-browser")
    run([node, ROOT / "tools/advanced-browser/playwright-cli.cjs", "--runtime-info"])


def check():
    lock = json.loads((ROOT / "advanced-tools.lock.json").read_text(encoding="utf-8"))
    checks = []
    for entry in lock["vendored_files"]:
        path = ROOT / entry["path"]
        exists = path.is_file()
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
        checks.append({"path": entry["path"], "exists": exists, "sha256_match": actual == entry["sha256"]})
    preservation = []
    for entry in lock["preserved_existing_files"] + lock["preserved_prompt_prefixes"]:
        path = ROOT / entry["path"]
        data = path.read_bytes() if path.is_file() else b""
        if entry in lock["preserved_prompt_prefixes"]:
            data = data[:entry["bytes"]]
        preservation.append({"path": entry["path"],
                             "original_bytes_preserved": hashlib.sha256(data).hexdigest() == entry["sha256"]})
    runtime = {"documents_python": str(document_python()), "documents_ready": False,
               "production_ready": False, "node": shutil.which("node"),
               "pdftoppm": shutil.which("pdftoppm"), "soffice": shutil.which("soffice"),
               "browser_status": "Run the browser smoke separately; CLI presence is not browser availability"}
    if document_python().is_file():
        p = subprocess.run([str(document_python()), "-c",
            "import importlib.metadata as m; from markitdown import MarkItDown; print(m.version('markitdown'))"],
            capture_output=True, text=True)
        runtime["documents_ready"] = p.returncode == 0 and p.stdout.strip() == "0.1.9"
        runtime["markitdown_version"] = p.stdout.strip()
    if runtime["node"]:
        p = subprocess.run([runtime["node"], "--input-type=module", "-e",
            "await import('pptxgenjs');await import('mermaid');console.log('ready')"],
            cwd=ROOT / "tools/advanced-production", capture_output=True, text=True)
        runtime["production_ready"] = p.returncode == 0
        p = subprocess.run([runtime["node"], str(ROOT / "tools/advanced-browser/playwright-cli.cjs"), "--runtime-info"],
                           capture_output=True, text=True)
        runtime["browser_cli_runtime_ready"] = p.returncode == 0
    passed = all(v["sha256_match"] for v in checks) and all(v["original_bytes_preserved"] for v in preservation)
    result = {"vendored_integrity_pass": passed, "files": checks, "runtime": runtime,
              "existing_file_preservation": preservation,
              "legacy_initialization_invoked": False,
              "legacy_skill_files_modified": False,
              "registration_note": "Local registration is separate from reloading a host skill catalog"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if passed and runtime["documents_ready"] and runtime["production_ready"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "register", "install"])
    parser.add_argument("--documents", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--browser-cli", action="store_true",
                        help="Reuse a matching CLI runtime, or install only the pinned local CLI package")
    parser.add_argument("--pdf-fallback", action="store_true",
                        help="Register upstream PDF only when the host has no suitable built-in PDF skill")
    parser.add_argument("--playwright-fallback", action="store_true",
                        help="Register upstream CLI skill only when no equivalent host CLI skill exists")
    args = parser.parse_args()
    if args.action == "install":
        if not (args.documents or args.production or args.browser_cli):
            parser.error("Choose --documents, --production and/or --browser-cli; no implicit reinstall")
        if args.documents:
            install_documents()
        if args.production:
            install_production()
        if args.browser_cli:
            install_browser_cli()
    elif args.action == "register":
        print(json.dumps(register(args.pdf_fallback, args.playwright_fallback), ensure_ascii=False, indent=2))
    else:
        return check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
