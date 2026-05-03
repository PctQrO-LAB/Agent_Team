import requests

url = "http://127.0.0.1:5000/scheduler"
payload = {
    "schema": "2.0",
    "header": {"event_id": "test", "token": "test", "create_time": "123", "event_type": "im.message.receive_v1", "tenant_key": "123", "app_id": "cli_123"},
    "event": {
        "message": {"chat_id": "oc_test", "chat_type": "p2p", "content": '{"text":"查询日程"}', "create_time": "123", "message_id": "om_test", "message_type": "text"}
    },
    "sender": {"sender_id": {"open_id": "ou_test", "union_id": "on_test"}, "sender_type": "user"}
}
requests.post(url, json=payload)
print("Sent")
