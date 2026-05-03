from agentscope.formatter._gemini_formatter import GeminiChatFormatter
from agentscope.model import GeminiChatModel
from agentscope.message import Msg, TextBlock, ImageBlock, AudioBlock, VideoBlock, ToolUseBlock, ToolResultBlock, URLSource
from agentscope.formatter._gemini_formatter import _format_gemini_media_block, logger
import copy

def _clean_schema_recursive(obj):
    """递归清理 JSON Schema 中的不支持字段"""
    if isinstance(obj, dict):
        # 1. 移除不支持的键
        keys_to_remove = ["additional_properties", "title", "additionalProperties"]
        for k in keys_to_remove:
            if k in obj:
                del obj[k]
        
        # 2. 递归清理所有值
        for key, value in obj.items():
            _clean_schema_recursive(value)
            
    elif isinstance(obj, list):
        # 3. 递归清理列表中的每一项
        for item in obj:
            _clean_schema_recursive(item)
            
    return obj

async def _patched_gemini_format(self, msgs: list[Msg]) -> list[dict]:
    """Format message objects into Gemini API required format."""
    self.assert_list_of_msgs(msgs)

    messages: list = []
    i = 0
    while i < len(msgs):
        msg = msgs[i]
        parts = []

        for block in msg.get_content_blocks():
            typ = block.get("type")
            if typ == "text":
                parts.append(
                    {
                        "text": block.get("text"),
                    },
                )

            elif typ == "tool_use":
                # PATCH: Add dummy thought_signature for Gemini 3 Compatibility
                parts.append(
                    {
                        "thought_signature": "context_engineering_is_the_way_to_go",
                        "function_call": {
                            "id": block["id"],
                            "name": block["name"],
                            "args": block["input"],
                        },
                    },
                )

            elif typ == "tool_result":
                (
                    textual_output,
                    multimodal_data,
                ) = self.convert_tool_result_to_string(block["output"])

                # First add the tool result message in DashScope API format
                messages.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "function_response": {
                                    "id": block["id"],
                                    "name": block["name"],
                                    "response": {
                                        "output": textual_output,
                                    },
                                },
                            },
                        ],
                    },
                )

                promoted_blocks: list = []
                for url, multimodal_block in multimodal_data:
                    if (
                        multimodal_block["type"] == "image"
                        and self.promote_tool_result_images
                    ):
                        promoted_blocks.extend(
                            [
                                TextBlock(
                                    type="text",
                                    text=f"\n- The image from '{url}': ",
                                ),
                                ImageBlock(
                                    type="image",
                                    source=URLSource(
                                        type="url",
                                        url=url,
                                    ),
                                ),
                            ],
                        )

                if promoted_blocks:
                    # Insert promoted blocks as new user message(s)
                    promoted_blocks = [
                        TextBlock(
                            type="text",
                            text="<system-info>The following are "
                            "the image contents from the tool "
                            f"result of '{block['name']}':",
                        ),
                        *promoted_blocks,
                        TextBlock(
                            type="text",
                            text="</system-info>",
                        ),
                    ]

                    msgs.insert(
                        i + 1,
                        Msg(
                            name="user",
                            content=promoted_blocks,
                            role="user",
                        ),
                    )

            elif typ in ["image", "audio", "video"]:
                parts.append(
                    _format_gemini_media_block(
                        block,  # type: ignore[arg-type]
                    ),
                )

            else:
                logger.warning(
                    "Unsupported block type: %s in the message, skipped. ",
                    typ,
                )

        role = "model" if msg.role == "assistant" else "user"

        if parts:
            messages.append(
                {
                    "role": role,
                    "parts": parts,
                },
            )

        # Move to next message (including inserted messages, which will
        # be processed in subsequent iterations)
        i += 1

    return messages

def apply_patches():
    # 1. Image Extension Patch
    if "jpg" not in GeminiChatFormatter.supported_extensions["image"]:
        print("🔧 Patching GeminiChatFormatter to support 'jpg' extension...")
        GeminiChatFormatter.supported_extensions["image"].append("jpg")
        print("✅ Patch applied.")
    else:
        print("ℹ️ GeminiChatFormatter already supports 'jpg'.")

    # 2. Thought Signature Patch for Gemini 3
    print("🔧 Patching GeminiChatFormatter to support 'thought_signature'...")
    GeminiChatFormatter._format = _patched_gemini_format
    
    # 3. Tool Schema Patch
    print("🔧 Patching GeminiChatModel to clean Tool Schema...")
    
    _original_model_format_tools = GeminiChatModel._format_tools_json_schemas

    def _patched_model_format_tools(self, schemas):
        # 调用原始方法生成 format 后的 tools结构
        # 原始方法返回: [{"function_declarations": [...]}]
        tools_config_list = _original_model_format_tools(self, schemas)
        
        # 清理
        _clean_schema_recursive(tools_config_list)
        logger.info(f"PATCH: Cleaned schema for {len(schemas)} tools.")
        return tools_config_list

    GeminiChatModel._format_tools_json_schemas = _patched_model_format_tools
    print("✅ Patch applied (Clean Schema).")

if __name__ == "__main__":
    apply_patches()
