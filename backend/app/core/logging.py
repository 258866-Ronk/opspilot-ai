"""
日志配置模块
为什么需要：企业项目不能靠 print 调试，需要统一格式、分级、可落盘的日志。
这里配置一个简单的结构化日志，后面 Langfuse 追踪会在此基础上做。
"""
import logging
import sys


def setup_logging(debug: bool = True):
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # 降低第三方库噪音
    for noisy in ("httpx", "httpcore", "sqlalchemy.engine", "aiosqlite", "passlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return root


logger = logging.getLogger("opspilot")
