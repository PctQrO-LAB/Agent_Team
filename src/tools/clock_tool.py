import datetime
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock


class ClockTool:
    def get_current_datetime(self) -> ToolResponse:
        """
        获取当前的北京时间 (UTC+8)。
        Returns:
            ToolResponse: 格式化后的时间字符串，例如 "2023-12-29 18:30:00 (Friday)"
        """
        # 1. 定义北京时区 (UTC+8)
        tz_cn = datetime.timezone(datetime.timedelta(hours=8))

        # 2. 获取带时区的时间
        now = datetime.datetime.now(tz_cn)

        # 3. 格式化输出
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_str = weekdays[now.weekday()]

        time_str = now.strftime(f"%Y-%m-%d %H:%M:%S ({weekday_str})")

        return ToolResponse(content=[TextBlock(type="text", text=time_str)])