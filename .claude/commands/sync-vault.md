---
description: Sync Obsidian literature notes and topic MOCs from Zotero
---

Refresh the vault from Zotero. Args (optional, e.g. '--since 2026-06-01'): $ARGUMENTS

1. `python3 tools/lit_note.py sync-all $ARGUMENTS` — regenerates the managed
   (top) half of every literature note from Zotero, preserving each note's
   user-written bottom half.
2. `python3 tools/lit_note.py topics` — rebuilds the Topic MOCs.
3. Report what was created vs updated, and flag any papers in Zotero that have
   highlights but no synthesis yet (good candidates for `/ask <paper>`).
