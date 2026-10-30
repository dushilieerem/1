import sqlite3

conn = sqlite3.connect("data/invest.db")
conn.row_factory = sqlite3.Row
print([dict(r) for r in conn.execute("SELECT kind, COUNT(*) n FROM news GROUP BY kind")])
for kind in ("announcement", "report"):
    row = conn.execute("SELECT * FROM news WHERE kind=? ORDER BY published_at DESC LIMIT 1", (kind,)).fetchone()
    print(kind, dict(row) if row else None)
