
import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

# 1. Apply Patch
from src.core.patch import apply_patches
apply_patches()

from agentscope.model import GeminiChatModel
from src.tools.note_tools import AgentNotebook

def test_schema_cleaning():
    print("🧪 Testing Schema Cleaning...")
    
    # Initialize Model (Mock API Key)
    model = GeminiChatModel(model_name="gemini-pro", api_key="test_key")
    
    # Get Tools
    note_tool = AgentNotebook(agent_name="TestAgent")
    # specific complex tool
    save_beat_list = note_tool.save_beat_list
    
    tools = [
        {"type": "function", "function": save_beat_list} # AgentScope might wrap it differently but let's emulate what Model sees
    ]
    
    # AgentScope Toolkit wrapping emulation
    # Actually, model._format_tools_json_schemas expects list of dicts (JSON Schema of tools)
    
    # Let's use AgentScope's Toolkit to generate the schema first
    from agentscope.tool import Toolkit
    toolkit = Toolkit()
    toolkit.register_tool_function(note_tool.save_beat_list)
    
    # Toolkit.tools returns a list of schema dicts
    tool_schemas = toolkit.get_json_schemas()
    
    print(f"📦 Tool Schemas Type: {type(tool_schemas)}")
    # print(f"📦 Tool Schemas Content: {tool_schemas}")

    if not tool_schemas:
        print("❌ Error: No tools registered in schema!")
        return

    # Call the patched method
    formatted = model._format_tools_json_schemas(tool_schemas)
    
    print("\n🧹 Cleaned Schema Result:")
    formatted_json = json.dumps(formatted, indent=2)
    print(formatted_json)
    
    if "additional_properties" in formatted_json or "additionalProperties" in formatted_json:
        print("\n❌ Test FAILED: 'additional_properties' still found!")
    else:
        print("\n✅ Test PASSED: Schema is clean.")

if __name__ == "__main__":
    test_schema_cleaning()
