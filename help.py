from __future__ import annotations


def build_help_message() -> str:
    return "\n".join(
        [
            "APYX Monitor commands:",
            "/status - 查看所有监控指标当前值",
            "/thresholds - 查看所有预警阈值",
            "/health - 服务自检：运行时间、成功率、数据新鲜度、错误分布",
            "/strategy - 查看当前监控策略说明",
            "/help - 查看命令帮助",
        ]
    )
