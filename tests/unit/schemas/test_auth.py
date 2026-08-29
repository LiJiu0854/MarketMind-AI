"""认证响应数据结构测试。"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import TokenResponse


def test_token_response_has_bearer_contract() -> None:
    """Token 响应必须包含令牌，并默认声明 Bearer 类型。"""
    response = TokenResponse(access_token="signed-token")

    assert response.model_dump() == {
        "access_token": "signed-token",
        "token_type": "bearer",
    }


def test_token_response_rejects_unknown_fields() -> None:
    """认证响应不接受合同之外的字段。"""
    with pytest.raises(ValidationError):
        TokenResponse(  # type: ignore[call-arg]
            access_token="signed-token", password="secret"
        )
