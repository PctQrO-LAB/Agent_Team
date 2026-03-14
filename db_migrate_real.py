import sqlite3
import os

DB_PATH = "data/shared/agent_shared.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database not found, skip migration.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    tables = [
        ("shots", "shot"),
        ("scenes", "scene"),
        ("design_assets", "name"),
        ("beat_list", "beat_num")
    ]
    for table, col in tables:
        try:
            cursor.execute(f"ALTER TABLE {table} RENAME COLUMN {col} TO uid;")
            print(f"Renamed {col} to uid in {table}")
        except Exception as e:
            print(f"{table} error: {e}")

    conn.commit()
    conn.close()
    print("Migration finished!")

if __name__ == "__main__":
    migrate()
