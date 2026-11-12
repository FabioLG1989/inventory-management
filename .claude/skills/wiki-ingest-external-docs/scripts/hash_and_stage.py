#!/usr/bin/env python3
"""
Compute SHA-256 of a converted markdown file, derive a content-addressed
staging path, prepend the mandatory frontmatter block, and copy the file
to the staging directory idempotently.

Usage:
  hash_and_stage.py --input <file> --staging-dir <dir> --slug <name>
                    --source-uri <uri> --source-type <type>
                    [--dry-run]

Exits 0 on success (including idempotent no-ops).
Exits non-zero on hard failure.
Prints the final staged path on stdout (or [dry-run] prefix when --dry-run).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="Path to converted markdown file")
    parser.add_argument("--staging-dir", required=True, help="Destination staging directory")
    parser.add_argument("--slug", required=True, help="Base slug for the output filename")
    parser.add_argument("--source-uri", required=True, help="Original source URI or path")
    parser.add_argument("--source-type", required=True, help="Source type: pdf, html, notion, etc.")
    parser.add_argument("--dry-run", action="store_true", help="Print path without writing")
    return parser.parse_args()


def slugify(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name[:80]


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_frontmatter(source_uri: str, source_type: str, sha256: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        "---\n"
        f"source_uri: {json.dumps(source_uri)}\n"
        f"source_type: {source_type}\n"
        f"ingested_at: {now}\n"
        f"last_verified: {now}\n"
        f"content_sha256: {sha256}\n"
        "authoritativeness: vendor-doc\n"
        "source_of_truth: false\n"
        "subject: []\n"
        "describes_service: null\n"
        "describes_files: []\n"
        "---\n\n"
    )


def has_frontmatter(content: str) -> bool:
    return content.startswith("---\n")


def strip_existing_frontmatter(content: str) -> str:
    if not has_frontmatter(content):
        return content
    end = content.find("\n---\n", 4)
    if end == -1:
        return content
    return content[end + 5:]


def main():
    args = parse_args()

    if not os.path.isfile(args.input):
        print(f"[error] Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    raw_sha256 = sha256_of_file(args.input)
    short_sha = raw_sha256[:8]
    slug = slugify(args.slug)
    filename = f"{short_sha}-{slug}.md"
    staged_path = os.path.join(args.staging_dir, filename)

    if args.dry_run:
        print(f"[dry-run] Would stage: {staged_path}")
        sys.exit(0)

    with open(args.input, "r", encoding="utf-8") as f:
        body = f.read()

    body_stripped = strip_existing_frontmatter(body)
    frontmatter = build_frontmatter(args.source_uri, args.source_type, raw_sha256)
    final_content = frontmatter + body_stripped

    os.makedirs(args.staging_dir, exist_ok=True)

    if os.path.isfile(staged_path):
        existing_sha = sha256_of_file(staged_path)
        if existing_sha == hashlib.sha256(final_content.encode()).hexdigest():
            print(f"Already staged (content unchanged): {staged_path}")
            sys.exit(0)

    tmp_fd, tmp_path = tempfile.mkstemp(dir=args.staging_dir, suffix=".md.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(final_content)
        os.replace(tmp_path, staged_path)
    except Exception:
        os.unlink(tmp_path)
        raise

    print(staged_path)


if __name__ == "__main__":
    main()
