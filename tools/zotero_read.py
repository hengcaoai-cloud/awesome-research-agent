#!/usr/bin/env python3
"""Read-only access to a local Zotero library.

Reads papers, your annotations (highlights), notes, tags and collections
straight from zotero.sqlite. Opens the DB in immutable read-only mode so it
works even while Zotero is running and holding a write lock, and never
modifies anything.

Usage:
    zotero_read.py collections                     # list collections + counts
    zotero_read.py list [--collection NAME] [--limit N] [--since YYYY-MM-DD]
    zotero_read.py item KEY                         # full dump of one item
    zotero_read.py search "query"                   # title/abstract/creator match
    zotero_read.py annotations KEY                  # annotations for one item
    zotero_read.py stats

All commands print JSON (item/list/search/annotations) or text (stats).
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from html.parser import HTMLParser

ZOTERO_DIR = os.path.expanduser(os.environ.get("ZOTERO_DIR", "~/Zotero"))
DB_PATH = os.path.join(ZOTERO_DIR, "zotero.sqlite")
STORAGE = os.path.join(ZOTERO_DIR, "storage")


def connect():
    if not os.path.exists(DB_PATH):
        sys.exit(f"zotero.sqlite not found at {DB_PATH} (set ZOTERO_DIR)")
    # immutable=1 -> read even while Zotero holds the lock; never writes.
    uri = f"file:{DB_PATH}?immutable=1"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


class _Strip(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, d):
        self.parts.append(d)


def strip_html(s):
    if not s:
        return ""
    p = _Strip()
    p.feed(s)
    text = "".join(p.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def item_fields(con, item_id):
    rows = con.execute(
        """
        SELECT f.fieldName AS name, idv.value AS value
        FROM itemData d
        JOIN fields f ON d.fieldID = f.fieldID
        JOIN itemDataValues idv ON d.valueID = idv.valueID
        WHERE d.itemID = ?
        """,
        (item_id,),
    ).fetchall()
    return {r["name"]: r["value"] for r in rows}


def item_creators(con, item_id):
    rows = con.execute(
        """
        SELECT c.firstName AS first, c.lastName AS last, ct.creatorType AS type
        FROM itemCreators ic
        JOIN creators c ON ic.creatorID = c.creatorID
        JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
        WHERE ic.itemID = ?
        ORDER BY ic.orderIndex
        """,
        (item_id,),
    ).fetchall()
    out = []
    for r in rows:
        name = " ".join(x for x in (r["first"], r["last"]) if x)
        out.append({"name": name, "type": r["type"]})
    return out


def item_tags(con, item_id):
    rows = con.execute(
        """
        SELECT t.name FROM itemTags it
        JOIN tags t ON it.tagID = t.tagID
        WHERE it.itemID = ? ORDER BY t.name
        """,
        (item_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def item_collections(con, item_id):
    rows = con.execute(
        """
        SELECT c.collectionName AS name FROM collectionItems ci
        JOIN collections c ON ci.collectionID = c.collectionID
        WHERE ci.itemID = ? ORDER BY c.collectionName
        """,
        (item_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def item_attachments(con, item_id):
    """Return (attachmentItemID, key, contentType, abspath) for child attachments."""
    rows = con.execute(
        """
        SELECT i.itemID AS id, i.key AS key, ia.contentType AS ct, ia.path AS path
        FROM itemAttachments ia
        JOIN items i ON ia.itemID = i.itemID
        WHERE ia.parentItemID = ?
        """,
        (item_id,),
    ).fetchall()
    out = []
    for r in rows:
        path = r["path"]
        abspath = None
        if path and path.startswith("storage:"):
            abspath = os.path.join(STORAGE, r["key"], path[len("storage:"):])
        elif path:
            abspath = path
        out.append(
            {"id": r["id"], "key": r["key"], "contentType": r["ct"], "path": abspath}
        )
    return out


def item_annotations(con, item_id):
    """Your highlights/notes inside the paper's PDF attachment(s)."""
    atts = item_attachments(con, item_id)
    att_ids = [a["id"] for a in atts]
    if not att_ids:
        return []
    q = ",".join("?" * len(att_ids))
    rows = con.execute(
        f"""
        SELECT type, text, comment, color, pageLabel, sortIndex
        FROM itemAnnotations
        WHERE parentItemID IN ({q})
        ORDER BY sortIndex
        """,
        att_ids,
    ).fetchall()
    types = {1: "highlight", 2: "note", 3: "image", 4: "ink", 5: "underline"}
    out = []
    for r in rows:
        out.append(
            {
                "type": types.get(r["type"], str(r["type"])),
                "text": r["text"],
                "comment": r["comment"],
                "color": r["color"],
                "page": r["pageLabel"],
            }
        )
    return out


def item_notes(con, item_id):
    rows = con.execute(
        """
        SELECT n.note FROM itemNotes n
        JOIN items i ON n.itemID = i.itemID
        WHERE n.parentItemID = ? AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        """,
        (item_id,),
    ).fetchall()
    return [strip_html(r["note"]) for r in rows if r["note"]]


def base_query(con):
    """All non-deleted, top-level regular items (papers), with type + key + dateAdded."""
    return con.execute(
        """
        SELECT i.itemID AS id, i.key AS key, it.typeName AS type,
               i.dateAdded AS added
        FROM items i
        JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE i.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND it.typeName NOT IN ('attachment','note','annotation')
          AND i.itemID NOT IN (SELECT itemID FROM itemAttachments WHERE parentItemID IS NOT NULL)
          AND i.itemID NOT IN (SELECT itemID FROM itemNotes WHERE parentItemID IS NOT NULL)
        ORDER BY i.dateAdded DESC
        """
    ).fetchall()


def summarize(con, row, full=False):
    iid = row["id"]
    fields = item_fields(con, iid)
    creators = item_creators(con, iid)
    rec = {
        "key": row["key"],
        "type": row["type"],
        "title": fields.get("title", ""),
        "authors": [c["name"] for c in creators if c["type"] in ("author", "contributor")],
        "year": (fields.get("date", "") or "")[:4],
        "date": fields.get("date", ""),
        "dateAdded": row["added"],
        "collections": item_collections(con, iid),
        "tags": item_tags(con, iid),
        "url": fields.get("url", ""),
        "DOI": fields.get("DOI", ""),
    }
    arxiv = fields.get("archiveID") or fields.get("archive") or ""
    m = re.search(r"(\d{4}\.\d{4,5})", (fields.get("url", "") + " " + arxiv))
    if m:
        rec["arxiv"] = m.group(1)
    if full:
        rec["abstract"] = fields.get("abstractNote", "")
        rec["publication"] = fields.get("publicationTitle") or fields.get("conferenceName") or ""
        rec["attachments"] = item_attachments(con, iid)
        rec["annotations"] = item_annotations(con, iid)
        rec["notes"] = item_notes(con, iid)
    else:
        rec["nAnnotations"] = len(item_annotations(con, iid))
        rec["nNotes"] = len(item_notes(con, iid))
    return rec


def cmd_collections(con, args):
    rows = con.execute(
        """
        SELECT c.collectionName AS name, COUNT(ci.itemID) AS n
        FROM collections c
        LEFT JOIN collectionItems ci ON c.collectionID = ci.collectionID
        GROUP BY c.collectionID ORDER BY n DESC
        """
    ).fetchall()
    print(json.dumps([{"name": r["name"], "count": r["n"]} for r in rows],
                     ensure_ascii=False, indent=2))


def cmd_list(con, args):
    rows = base_query(con)
    out = []
    for r in rows:
        rec = summarize(con, r, full=False)
        if args.collection and args.collection not in rec["collections"]:
            continue
        if args.since and (rec["dateAdded"] or "") < args.since:
            continue
        out.append(rec)
        if args.limit and len(out) >= args.limit:
            break
    print(json.dumps(out, ensure_ascii=False, indent=2))


def find_item(con, key):
    row = con.execute(
        """
        SELECT i.itemID AS id, i.key AS key, it.typeName AS type, i.dateAdded AS added
        FROM items i JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
        WHERE i.key = ?
        """,
        (key,),
    ).fetchone()
    return row


def cmd_item(con, args):
    row = find_item(con, args.key)
    if not row:
        sys.exit(f"item {args.key} not found")
    print(json.dumps(summarize(con, row, full=True), ensure_ascii=False, indent=2))


def cmd_annotations(con, args):
    row = find_item(con, args.key)
    if not row:
        sys.exit(f"item {args.key} not found")
    print(json.dumps(item_annotations(con, row["id"]), ensure_ascii=False, indent=2))


def cmd_search(con, args):
    q = args.query.lower()
    rows = base_query(con)
    out = []
    for r in rows:
        rec = summarize(con, r, full=False)
        hay = " ".join([rec["title"], " ".join(rec["authors"]), " ".join(rec["tags"])]).lower()
        fields = item_fields(con, r["id"])
        hay += " " + (fields.get("abstractNote", "") or "").lower()
        if q in hay:
            out.append(rec)
        if args.limit and len(out) >= args.limit:
            break
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_stats(con, args):
    n = con.execute(
        "SELECT COUNT(*) FROM items i WHERE i.itemID NOT IN (SELECT itemID FROM deletedItems)"
    ).fetchone()[0]
    ann = con.execute("SELECT COUNT(*) FROM itemAnnotations").fetchone()[0]
    notes = con.execute(
        "SELECT COUNT(*) FROM itemNotes WHERE parentItemID IS NOT NULL"
    ).fetchone()[0]
    papers = len(base_query(con))
    print(f"papers (top-level): {papers}")
    print(f"all items:          {n}")
    print(f"annotations:        {ann}")
    print(f"notes:              {notes}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collections")
    lp = sub.add_parser("list")
    lp.add_argument("--collection")
    lp.add_argument("--limit", type=int, default=0)
    lp.add_argument("--since")
    ip = sub.add_parser("item")
    ip.add_argument("key")
    ap = sub.add_parser("annotations")
    ap.add_argument("key")
    sp = sub.add_parser("search")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=0)
    sub.add_parser("stats")
    args = p.parse_args()
    con = connect()
    {
        "collections": cmd_collections,
        "list": cmd_list,
        "item": cmd_item,
        "annotations": cmd_annotations,
        "search": cmd_search,
        "stats": cmd_stats,
    }[args.cmd](con, args)


if __name__ == "__main__":
    main()
