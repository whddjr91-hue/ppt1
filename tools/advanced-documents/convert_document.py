"""Local-only text analysis adapter. Never edits source documents or infers layout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


class LegacyDocumentRequired(ValueError):
    pass


def convert_document(source: Path) -> dict:
    source = source.expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("Input must be a local regular file")
    suffix = source.suffix.lower()
    if suffix in {".hwp", ".hwpx"}:
        raise LegacyDocumentRequired(
            "HWP/HWPX must use the existing Hangul document pipeline. "
            "MarkItDown is not a replacement for deletion marks, comments, "
            "speaker attribution or screen/narration classification."
        )
    if suffix not in {".pdf", ".pptx", ".docx", ".txt", ".md"}:
        raise ValueError("Supported local inputs: PDF, PPTX, DOCX, TXT, MD")
    from markitdown import MarkItDown

    # No URLs, remote providers, LLM clients, or third-party conversion plugins.
    result = MarkItDown(enable_plugins=False).convert_local(str(source))
    return {
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "engine": "markitdown-local",
        "markdown": result.markdown,
        "role": "text preprocessing only",
        "layout_or_revision_semantics_verified": False,
        "required_followup": [
            "Compare extracted text with source",
            "Use native PPTX/XML and page renders for layout and sync review",
            "Do not infer deleted text, speaker, case status or narration from Markdown",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="New JSON output; source is never modified")
    args = parser.parse_args()
    try:
        result = convert_document(args.source)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output.expanduser().resolve()
        if target == args.source.expanduser().resolve():
            parser.exit(2, "Output cannot overwrite input\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
