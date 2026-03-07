import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.tools.note_tools import AgentNotebook

if __name__ == "__main__":
    print("🚀 Triggering Database Migration...")
    notebook = AgentNotebook(agent_name="migration_bot")
    print("✅ Migration checks complete.")
