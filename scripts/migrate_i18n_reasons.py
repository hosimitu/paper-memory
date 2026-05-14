# -*- coding: utf-8 -*-
import sqlite3
import json
import os
from pathlib import Path

def migrate():
    db_path = "paper_memory.db"
    if not os.path.exists(db_path):
        print(f"❌ Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("Starting migration of 'reason' fields to JSON format...")

    # 1. Migrate note_links table
    print("--- Migrating note_links table ---")
    cursor.execute("SELECT source_id, target_id, reason FROM note_links")
    links = cursor.fetchall()
    for link in links:
        reason = link["reason"]
        if reason and not reason.startswith('{'):
            # Convert plain string to JSON dict
            new_reason = json.dumps({"en": reason, "ja": reason}, ensure_ascii=False)
            cursor.execute(
                "UPDATE note_links SET reason = ? WHERE source_id = ? AND target_id = ?",
                (new_reason, link["source_id"], link["target_id"])
            )
    print(f"OK: Migrated {len(links)} links.")

    # 2. Migrate references_table table
    print("--- Migrating references_table table ---")
    cursor.execute("SELECT id, reason FROM references_table")
    refs = cursor.fetchall()
    for ref in refs:
        reason = ref["reason"]
        if reason and not reason.startswith('{'):
            new_reason = json.dumps({"en": reason, "ja": reason}, ensure_ascii=False)
            cursor.execute(
                "UPDATE references_table SET reason = ? WHERE id = ?",
                (new_reason, ref["id"])
            )
    print(f"OK: Migrated {len(refs)} references.")

    # 3. Migrate notes table (evolution_history)
    print("--- Migrating notes table (evolution_history) ---")
    cursor.execute("SELECT id, evolution_history FROM notes")
    notes = cursor.fetchall()
    migrated_notes_count = 0
    for note in notes:
        history_str = note["evolution_history"]
        if not history_str:
            continue
        
        try:
            history = json.loads(history_str)
            changed = False
            for event in history:
                if "reason" in event:
                    reason = event["reason"]
                    if reason and isinstance(reason, str) and not reason.startswith('{'):
                        event["reason"] = {"en": reason, "ja": reason}
                        changed = True
            
            if changed:
                new_history_str = json.dumps(history, ensure_ascii=False)
                cursor.execute(
                    "UPDATE notes SET evolution_history = ? WHERE id = ?",
                    (new_history_str, note["id"])
                )
                migrated_notes_count += 1
        except Exception as e:
            print(f"Warning: Error parsing history for note {note['id']}: {e}")

    print(f"OK: Migrated evolution history for {migrated_notes_count} notes.")

    conn.commit()
    conn.close()
    print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
