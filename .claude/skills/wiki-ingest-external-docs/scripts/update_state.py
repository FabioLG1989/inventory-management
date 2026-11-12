#!/usr/bin/env python3
"""
Read docs/llm-wiki/.ingestion-state.json, append or update an entry for
the given source URI, and write the result atomically.

Usage:
  update_state.py --state-path <path>
                  --source-uri <uri>
                  --content-hash <sha256>
                  --staged-path <path>
                  [--etag <etag>]
                  [--global]

The state file tracks per-source-URI ingestion metadata so future runs can
detect re-ingestion of unchanged content and skip redundant processing.

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
    parser.add_argument("--state-path", required=True, help="Path to .ingestion-state.json")
    parser.add_argument("--source-uri", required=True, help="Original source URI or path")
    parser.add_argument("--content-hash", required=True, help="SHA-256 of staged content")
    parser.add_argument("--staged-path", required=True, help="Final staged file path")
    parser.add_argument("--etag", default=None, help="HTTP ETag for cache-control (optional)")
    parser.add_argument("--global", dest="is_global", action="store_true",
                        help="Operating on the global wiki tree")
    return parser.parse_args()


def main():
    args = parse_args()

    state_path = args.state_path
    state_dir = os.path.dirname(state_path)
    os.makedirs(state_dir, exist_ok=True)

    if os.path.isfile(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            try:
                state = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[error] .ingestion-state.json is malformed: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        state = {"entries": {}}

    if "entries" not in state:
        state["entries"] = {}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing = state["entries"].get(args.source_uri, {})
    state["entries"][args.source_uri] = {
        "staged_path": args.staged_path,
        "content_hash": args.content_hash,
        "last_ingested": existing.get("last_ingested", now),
        "last_verified": now,
        "etag": args.etag,
    }

    if existing.get("content_hash") != args.content_hash:
        state["entries"][args.source_uri]["last_ingested"] = now

    tmp_fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, state_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    scope = "global" if args.is_global else "repo"
    print(f"Ingestion state updated ({scope}): {state_path} ({len(state['entries'])} entries)")


if __name__ == "__main__":
    main()
