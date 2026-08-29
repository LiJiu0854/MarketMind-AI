"""应用业务异常。"""


class AppError(Exception):
    """可以安全转换为 API 响应的业务异常。"""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
