#!/usr/bin/env python3
"""Add an arXiv paper to Zotero via the local connector endpoint.

IMPORTANT: Zotero 7's local *API* (/api/...) is read-only — it cannot create
items. Writing goes through the *connector* endpoint (the same one the browser
extension uses), which is enabled by the same Settings -> Advanced ->
"Allow other applications ... to communicate with Zotero" toggle.

The connector first saves into whatever collection is selected in the Zotero UI,
then we call `/updateSession` to route the item into a fixed target collection
(default "Recommend") — so NO manual click in Zotero is needed each time.

Usage:
    zotero_add.py 2606.06832                      # -> Recommend (default)
    zotero_add.py 2606.06832 --collection "VLA"   # -> VLA
    zotero_add.py 2606.06832 --no-collection      # -> whatever is selected in the UI
    zotero_add.py --check
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

CONNECTOR = "http://localhost:23119/connector"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "Inbox")


NEW_TAG = "agent-new"   # every agent-added paper gets this; remove it once you've read it
DEFAULT_COLLECTION = "Recommend"   # papers are auto-routed here, no UI click needed


def connector_up():
    try:
        with urllib.request.urlopen(CONNECTOR + "/ping", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _selected():
    """Full getSelectedCollection payload (name + the targets list)."""
    try:
        req = urllib.request.Request(
            CONNECTOR + "/getSelectedCollection", data=b"{}", method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    except Exception:
        return {}


def selected_collection():
    return _selected().get("name", "?")


def collection_target_id(name):
    """Connector target id (e.g. 'C9') for a collection name, regardless of what is
    selected in the Zotero UI. Lets us route saves to a fixed collection."""
    for t in _selected().get("targets", []):
        if t.get("name") == name:
            return t.get("id")
    return None


def meta_from_stub(arxiv_id):
    """Read metadata from a local Inbox stub (avoids hitting arXiv)."""
    for p in glob.glob(os.path.join(INBOX, "*.md")):
        t = open(p, encoding="utf-8").read()
        if not re.search(rf"^arxiv:\s*{re.escape(arxiv_id)}\s*$", t, re.M):
            continue
        def g(k):
            m = re.search(rf"^{k}:\s*(.*)$", t, re.M)
            return m.group(1).strip() if m else ""
        title = g("title").strip().strip('"')
        authors = []
        am = re.search(r"^authors:\s*\[(.*)\]\s*$", t, re.M)
        if am:
            authors = [a.strip().strip('"') for a in am.group(1).split('", "')]
            authors = [a.strip('"').strip() for a in authors if a.strip()]
        ab = re.search(r"## Abstract\n(.*?)\n\n", t, re.S)
        return {"title": title, "authors": authors,
                "abstract": (ab.group(1).strip() if ab else ""),
                "date": g("published")}
    return None


def fetch_meta(arxiv_id, tries=3):
    stub = meta_from_stub(arxiv_id)
    if stub and stub["title"]:
        return stub
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                root = ET.fromstring(r.read())
            break
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    else:
        sys.exit(f"arXiv fetch failed for {arxiv_id}: {last}")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    e = root.find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        sys.exit(f"arXiv {arxiv_id} not found")
    return {
        "title": " ".join(e.find("a:title", ns).text.split()),
        "abstract": " ".join(e.find("a:summary", ns).text.split()),
        "authors": [a.find("a:name", ns).text for a in e.findall("a:author", ns)],
        "date": e.find("a:published", ns).text[:10],
    }


def creators(names):
    out = []
    for n in names:
        parts = n.split()
        out.append({"creatorType": "author",
                    "firstName": " ".join(parts[:-1]), "lastName": parts[-1] if parts else n})
    return out


UA = "Mozilla/5.0 paper-agent"


def download_pdf(arxiv_id, tries=3):
    """Fetch the actual PDF bytes from arXiv. Returns (url, bytes_or_None)."""
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if data[:5] == b"%PDF-":
                return url, data
            last = f"server did not return a PDF (head={data[:16]!r})"
        except Exception as e:
            last = e
        time.sleep(2 * (i + 1))
    print(f"  warning: could not download PDF ({last}); saving link only", file=sys.stderr)
    return url, None


def save(arxiv_id, meta, collection=None):
    """Create the item, push the downloaded PDF as a stored attachment, and (if a
    collection is given) route it there via updateSession.

    The Zotero connector does NOT fetch attachment URLs on its own when saveItems
    is called outside a browser — it expects the client to upload the file bytes
    via a follow-up /saveAttachment call (linked by sessionID + matching ids).
    So we: (1) saveItems with an id'd PDF attachment, (2) download the PDF,
    (3) POST the bytes to /saveAttachment. Without step 3 you only get a link.
    """
    sess = f"paperagent-{arxiv_id}-{int(time.time())}"
    item_id, att_id = f"item-{arxiv_id}", f"att-{arxiv_id}"
    pdf_url, pdf = download_pdf(arxiv_id)

    item = {
        "id": item_id,
        "itemType": "preprint",
        "title": meta["title"],
        "creators": creators(meta["authors"]),
        "abstractNote": meta["abstract"],
        "repository": "arXiv",
        "archiveID": f"arXiv:{arxiv_id}",
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "date": meta["date"],
        "libraryCatalog": "arXiv.org",
        "tags": [{"tag": NEW_TAG}],
    }
    if pdf:
        item["attachments"] = [{
            "id": att_id, "parentItem": item_id, "title": "Full Text PDF",
            "mimeType": "application/pdf", "url": pdf_url,
        }]

    body = json.dumps({"sessionID": sess, "uri": item["url"], "items": [item]}).encode()
    req = urllib.request.Request(
        CONNECTOR + "/saveItems", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "X-Zotero-Connector-API-Version": "3", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        sys.exit(f"connector save failed {e.code}: {e.read().decode()[:200]}")

    pdf_ok = False
    if pdf:
        hdr = {"id": att_id, "parentItemID": item_id, "url": pdf_url,
               "contentType": "application/pdf", "title": "Full Text PDF",
               "sessionID": sess}
        areq = urllib.request.Request(
            CONNECTOR + "/saveAttachment", data=pdf, method="POST",
            headers={"Content-Type": "application/pdf",
                     "X-Metadata": json.dumps(hdr),
                     "X-Zotero-Connector-API-Version": "3", "User-Agent": UA})
        try:
            with urllib.request.urlopen(areq, timeout=180) as r:
                pdf_ok = r.status in (200, 201)
        except urllib.error.HTTPError as e:
            print(f"  warning: attachment upload failed {e.code}: "
                  f"{e.read().decode()[:200]}", file=sys.stderr)

    # Route the just-saved item into the target collection, regardless of what is
    # selected in the Zotero UI (the connector's "change collection after save").
    routed = None
    if collection:
        tid = collection_target_id(collection)
        if tid:
            body = json.dumps({"sessionID": sess, "target": tid, "tags": ""}).encode()
            req = urllib.request.Request(
                CONNECTOR + "/updateSession", data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "X-Zotero-Connector-API-Version": "3", "User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    if r.status == 200:
                        routed = collection
            except urllib.error.HTTPError as e:
                print(f"  warning: could not route to '{collection}' ({e.code})",
                      file=sys.stderr)
        else:
            print(f"  warning: collection '{collection}' not found; left in selection",
                  file=sys.stderr)
    return status, pdf_ok, routed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arxiv", nargs="?")
    ap.add_argument("--collection", default=DEFAULT_COLLECTION,
                    help=f"collection to auto-route into (default: {DEFAULT_COLLECTION})")
    ap.add_argument("--no-collection", action="store_true",
                    help="don't route; leave in whatever is selected in the Zotero UI")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        print("connector (write): " + ("UP" if connector_up() else "DOWN — enable in Settings→Advanced"))
        return
    if not args.arxiv:
        ap.error("arxiv id required")
    if not connector_up():
        sys.exit("Zotero connector not reachable. Enable Settings -> Advanced -> "
                 "'Allow other applications ... to communicate with Zotero', and run Zotero.")
    collection = None if args.no_collection else args.collection
    aid = re.search(r"(\d{4}\.\d{4,5})", args.arxiv).group(1)
    meta = fetch_meta(aid)
    status, pdf_ok, routed = save(aid, meta, collection)
    print(json.dumps({"saved": aid, "title": meta["title"][:55],
                      "http": status, "pdf": pdf_ok,
                      "collection": routed or selected_collection(),
                      "tag": NEW_TAG}, ensure_ascii=False))


if __name__ == "__main__":
    main()
