import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from flask import Flask, abort, request
import lark_oapi as lark
from lark_oapi.adapter.flask import parse_req, parse_resp
from lark_oapi.core.exception import EventException
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from src.core.message_adapters.n8n_adapter import extract_n8n_message
from src.core.message_adapters.lark_adapter import extract_message_from_p2

logger = logging.getLogger("WebhookServer")


@dataclass
class WebhookEndpointConfig:
    manager: Any  # LarkManager instance
    verification_token: Optional[str] = None
    encrypt_key: Optional[str] = None
    handler: Optional[Any] = None  # lark EventDispatcherHandler
    event_loop: Optional[asyncio.AbstractEventLoop] = None  # 主事件循环，用于线程安全派发


def _build_handler(config: WebhookEndpointConfig) -> Any:
    # 统一用官方 SDK 处理校验/解密，Encrypt Key 可为空
    builder = lark.EventDispatcherHandler.builder(
        config.encrypt_key or "",
        config.verification_token or "",
        lark.LogLevel.INFO,
    )

    # 注册 v2.0 消息事件，解析后转发给对应 manager
    def on_im_message(data: P2ImMessageReceiveV1):
        extracted = extract_message_from_p2(data, config.manager, config.manager.bot_name)
        if extracted and config.manager.message_handler:
            msg_content, sender_id, chat_id = extracted
            try:
                dispatch_coro = config.manager.message_handler(msg_content, sender_id, chat_id)
                target_loop = config.event_loop

                # 优先投递到主事件循环，确保不阻塞 webhook 返回，避免飞书重复投递
                if target_loop and target_loop.is_running():
                    asyncio.run_coroutine_threadsafe(dispatch_coro, target_loop)
                else:
                    # 兜底：启用独立线程运行协程，防止阻塞当前请求线程
                    def _runner():
                        try:
                            asyncio.run(dispatch_coro)
                        except Exception as exc:
                            logger.error(f"❌ Background dispatch failed: {exc}", exc_info=True)

                    threading.Thread(target=_runner, daemon=True, name=f"{config.manager.bot_name}-dispatch").start()
            except Exception as exc:
                logger.error(f"❌ Failed to dispatch message via SDK handler: {exc}", exc_info=True)

    builder.register_p2_im_message_receive_v1(on_im_message)

    return builder.build()


def build_webhook_app(endpoint_map: Dict[str, WebhookEndpointConfig]) -> Flask:
    """构建 Flask Webhook 应用，使用飞书 SDK 完成校验与分发"""
    app = Flask(__name__)

    # 为每个 endpoint 创建独立 handler（支持不同 Token/Encrypt Key）
    for cfg in endpoint_map.values():
        cfg.handler = _build_handler(cfg)

    @app.post("/<endpoint>")
    def handle_event(endpoint: str):
        logger.info(f"📨 Webhook received: /{endpoint}")

        if endpoint not in endpoint_map:
            logger.warning(f"❌ Unknown endpoint: {endpoint}")
            abort(404, description="Unknown endpoint")

        cfg = endpoint_map[endpoint]

        payload = request.get_json(silent=True) or {}
        if not payload:
            # 兼容非 JSON 请求（如 form 或 raw body）
            if request.form:
                payload = request.form.to_dict()
            else:
                raw_body = request.get_data(as_text=True) or ""
                try:
                    payload = json.loads(raw_body) if raw_body.strip().startswith("{") else {}
                except Exception:
                    payload = {}
                    
        # --- 拦截并打印 n8n 原始信息 ---
        logger.info(f"🔍 [Intercept] Raw payload received at /{endpoint} : {json.dumps(payload, ensure_ascii=False)}")
                    
        is_n8n = str(payload.get("source", "")).lower() == "n8n"
        if not is_n8n:
            if ("event" not in payload and "schema" not in payload and
                    any(k in payload for k in ["text", "prompt", "image_url", "image_urls"])):
                is_n8n = True

        if is_n8n:
            msg_content, sender_id, chat_id = extract_n8n_message(payload)

            if cfg.manager.message_handler:
                try:
                    dispatch_coro = cfg.manager.message_handler(msg_content, sender_id, chat_id)
                    target_loop = cfg.event_loop

                    if target_loop and target_loop.is_running():
                        asyncio.run_coroutine_threadsafe(dispatch_coro, target_loop)
                    else:
                        def _runner():
                            try:
                                asyncio.run(dispatch_coro)
                            except Exception as exc:
                                logger.error(f"❌ Background dispatch failed: {exc}", exc_info=True)

                        threading.Thread(target=_runner, daemon=True, name=f"{cfg.manager.bot_name}-dispatch").start()
                except Exception as exc:
                    logger.error(f"❌ Failed to dispatch n8n message: {exc}", exc_info=True)

            return {"ok": True, "chat_id": chat_id}

        # 优先处理 URL 校验，直接回传 challenge，避免 SDK 分支差异
        payload = request.get_json(silent=True) or {}
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge", "")
            token = payload.get("token")
            if cfg.verification_token and token != cfg.verification_token:
                logger.error("❌ Invalid verification token for url_verification")
                abort(403, description="Invalid verification token")
            logger.info(f"✅ URL verification challenge: {challenge}")
            return {"challenge": challenge}

        resp = None
        try:
            resp = cfg.handler.do(parse_req())
        except EventException as exc:
            logger.error(f"❌ Handler failed: {exc}", exc_info=True)
            abort(400, description="Handler failed")
        except Exception as exc:  # SDK 负责 Token 校验和 challenge 响应
            logger.error(f"❌ Handler failed: {exc}", exc_info=True)
            abort(400, description="Handler failed")

        # SDK 已注册 im.message.receive_v1，避免重复派发；其他事件目前无需手动兜底
        return parse_resp(resp) if resp is not None else ("", 200)

    return app


def start_webhook_server(app: Flask, host: str, port: int):
    import threading
    import time

    def run():
        # Flask 内置 server，适合开发/内部环境
        app.run(host=host, port=port, threaded=True)

    thread = threading.Thread(target=run, daemon=True, name="WebhookServer")
    thread.start()

    # 等待服务启动
    time.sleep(2)
    logger.info(f"✅ Webhook server started on {host}:{port}")

    return app, thread
