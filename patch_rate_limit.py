with open('src/core/lark_manager.py', 'r') as f:
    content = f.read()

replacement = """        # 增加回复的错误捕获
        try:
            for _ in range(3):
                resp = await asyncio.to_thread(lambda: self.api_client.im.v1.message.create(req))
                if not resp.success():
                    if resp.code == 230020:
                        self.logger.warning(f"⚠️ 飞书频率限制，等待重试...")
                        await asyncio.sleep(2)
                        continue
                    self.logger.error(f"❌ 回复失败: code={resp.code}, msg={resp.msg}")
                    break
                else:
                    break
        except Exception as e:"""

content = content.replace("""        # 增加回复的错误捕获
        try:
            resp = await asyncio.to_thread(lambda: self.api_client.im.v1.message.create(req))
            if not resp.success():
                self.logger.error(f"❌ 回复失败: code={resp.code}, msg={resp.msg}")
        except Exception as e:""", replacement)

with open('src/core/lark_manager.py', 'w') as f:
    f.write(content)
