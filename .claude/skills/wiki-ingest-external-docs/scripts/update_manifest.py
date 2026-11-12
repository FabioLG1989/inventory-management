#!/usr/bin/env python3
"""
Read docs/llm-wiki/raw/external/manifest.json, append or update a single
entry, and write the result atomically.

Usage:
  update_manifest.py --manifest-path <path>
                     --staged-path <path>
                     --source-uri <uri>
                     --source-type <type>
                     --content-sha256 <hex>
                     --subject-keywords <comma-separated>
                     --describes-service <service-id-or-empty>
                     --describes-files <comma-separated-or-empty>
                     --authoritativeness <value>
                     --source-of-truth <true|false>

Exits 0 on success. Exits non-zero on hard failure.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--staged-path", required=True)
    parser.add_argument("--source-uri", required=True)
    parser.add_argument("--source-type", required=True)
    parser.add_argument("--content-sha256", required=True)
    parser.add_argument("--subject-keywords", default="")
    parser.add_argument("--describes-service", default="")
    parser.add_argument("--describes-files", default="")
    parser.add_argument("--authoritativeness", default="vendor-doc")
    parser.add_argument("--source-of-truth", default="false")
    return parser.parse_args()


def parse_csv(value: str) -> list:
    if not value or not value.strip():
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def main():
    args = parse_args()

    manifest_path = args.manifest_path
    manifest_dir = os.path.dirname(manifest_path)
    os.makedirs(manifest_dir, exist_ok=True)

    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[error] manifest.json is malformed: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        manifest = {}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = os.path.basename(args.staged_path)

    source_of_truth = args.source_of_truth.lower() in ("true", "1", "yes")
    describes_service = args.describes_service.strip() or None
    subject_keywords = parse_csv(args.subject_keywords)
    describes_files = parse_csv(args.describes_files)

    entry = {
        "source_uri": args.source_uri,
        "source_type": args.source_type,
        "ingested_at": manifest.get(filename, {}).get("ingested_at", now),
        "last_verified": now,
        "content_sha256": args.content_sha256,
        "subject_keywords": subject_keywords,
        "describes_service": describes_service,
        "describes_files": describes_files,
        "authoritativeness": args.authoritativeness,
        "source_of_truth": source_of_truth,
    }

    manifest[filename] = entry

    tmp_fd, tmp_path = tempfile.mkstemp(dir=manifest_dir, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, manifest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    print(f"Manifest updated: {manifest_path} ({len(manifest)} entries)")


if __name__ == "__main__":
    main()
