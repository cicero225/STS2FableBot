"""Print the run index (quick status table). Usage: python scripts/show_runs.py"""

import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "logs" / "index.sqlite"
conn = sqlite3.connect(db)
rows = conn.execute(
    """SELECT id, character, ascension, floor, victory, decisions, status,
              COALESCE(killed_by, ''), COALESCE(seed, '')
       FROM runs ORDER BY id"""
).fetchall()
conn.close()

print(
    f"{'id':>3} {'character':<15} {'asc':>3} {'floor':>5} {'win':>4} "
    f"{'dec':>5} {'status':<10} {'killed_by':<35} seed"
)
for r in rows:
    win = {None: "?", 0: "L", 1: "W"}.get(r[4], "?")
    print(
        f"{r[0]:>3} {r[1]!s:<15} {r[2]!s:>3} {r[3]!s:>5} {win:>4} "
        f"{r[5]:>5} {r[6]:<10} {r[7]:<35} {r[8]}"
    )
