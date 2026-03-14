import sqlite3
import os

DB_PATH = "data/shared/agent_database.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database not found, skip migration.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Alter shots: shot -> uid
        cursor.execute("ALTER TABLE shots RENAME COLUMN shot TO uid;")
    except Exception as e:
        print(f"Shots error: {e}")
        
    try:
        # Alter scenes: scene -> uid
        cursor.execute("ALTER TABLE scenes RENAME COLUMN scene TO uid;")
    except Exception as e:
        print(f"Scenes error: {e}")

    try:
        # Alter design_assets: name -> uid
        cursor.execute("ALTER TABLE design_assets RENAME COLUMN name TO uid;")
    except Exception as e:
        print(f"design_assets error: {e}")

    try:
        # Alter beat_list: beat_num -> uid
        cursor.execute("ALTER TABLE beat_list RENAME COLUMN beat_num TO uid;")
    except Exception as e:
        print(f"beat_list error: {e}")

    conn.commit()
    conn.close()
    print("Migration finished!")

if __name__ == "__main__":
    migrate()
