from app.db.connector import get_conn, DB_PATH

def main():
    try:
        with get_conn() as c:
            rows = c.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table','view') "
                "AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()

        print("✅ Connected to:", DB_PATH)
        if rows:
            print("Tables/Views:")
            for name, typ in rows:
                print(f" - {name} ({typ})")
        else:
            print("⚠️ No user tables/views found in this database.")

    except Exception as e:
        print("❌ Connection failed:", e)

if __name__ == "__main__":
    main()
