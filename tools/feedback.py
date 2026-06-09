#!/usr/bin/env python3
"""Record triage feedback so the fetcher adapts to your taste over time.

  keep <id>  -> positive signal (also a future S2 seed); optionally add to Zotero
  drop <id>  -> negative signal (suppresses similar S2 recommendations); removes
                the Inbox stub

<id> is an arXiv id (e.g. 2606.06832) or an S2 paper id. Feedback is appended to
Inbox/.feedback.jsonl and consumed by tools/fetch.py on the next run.

Usage:
    feedback.py keep 2606.06832 [--zotero] [--collection "VLA"]
    feedback.py drop 2606.07089
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Inbox")
FEEDBACK = os.path.join(INBOX, ".feedback.jsonl")
ADDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zotero_add.py")


def is_arxiv(s):
    return bool(re.fullmatch(r"\d{4}\.\d{4,5}", s))


def find_stub(ident):
    for p in glob.glob(os.path.join(INBOX, "*.md")):
        head = open(p, encoding="utf-8").read(500)
        if ident in head:
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("verdict", choices=["keep", "drop"])
    ap.add_argument("id")
    ap.add_argument("--zotero", action="store_true", help="(keep) add to Zotero")
    ap.add_argument("--collection")
    args = ap.parse_args()

    rec = {"id": args.id, "verdict": args.verdict, "ts": dt.datetime.now().isoformat()}
    if is_arxiv(args.id):
        rec["arxiv"] = args.id
    os.makedirs(INBOX, exist_ok=True)
    with open(FEEDBACK, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if args.verdict == "drop":
        stub = find_stub(args.id)
        if stub:
            os.remove(stub)
            print(f"dropped, removed {os.path.relpath(stub, ROOT)}")
        else:
            print("dropped (no stub found)")
        return

    # keep
    msg = f"kept {args.id}"
    if args.zotero and is_arxiv(args.id):
        cmd = [sys.executable, ADDER, args.id]
        if args.collection:
            cmd += ["--collection", args.collection]
        out = subprocess.run(cmd, capture_output=True, text=True)
        msg += " | " + (out.stdout.strip() or out.stderr.strip())
    print(msg)


if __name__ == "__main__":
    main()
