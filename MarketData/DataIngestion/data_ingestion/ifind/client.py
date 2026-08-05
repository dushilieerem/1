"""iFinD HTTP 鉴权与 JSON 请求封装。"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "https://quantapi.51ifind.com"


class IFindRequestError(RuntimeError):
    """iFinD 请求或返回业务错误。"""


class IFindClient:
    """使用 refresh token 按需获取 access token 的最小 HTTP 客户端。"""

    def __init__(self, refresh_token: str, *, timeout: int = 60) -> None:
        if not refresh_token:
            raise ValueError("iFinD refresh token 不能为空")
        self._refresh_token = refresh_token
        self._timeout = timeout
        self._access_token: str | None = None

    @classmethod
    def from_environment(cls) -> "IFindClient":
        refresh_token = os.environ.get("IFIND_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError("未设置 IFIND_REFRESH_TOKEN 环境变量")
        return cls(refresh_token)

    def post(self, path: str, payload: dict) -> dict:
        if self._access_token is None:
            self._access_token = self._get_access_token()
        response = self._post_json(
            path,
            payload,
            headers={"access_token": self._access_token},
        )
        if response.get("errorcode", 0) != 0:
            raise IFindRequestError(
                f"iFinD 请求失败（{response.get('errorcode')}）：{response.get('errmsg', '未知错误')}"
            )
        return response

    def _get_access_token(self) -> str:
        response = self._post_json(
            "/api/v1/get_access_token",
            {},
            headers={"refresh_token": self._refresh_token},
        )
        try:
            return response["data"]["access_token"]
        except (KeyError, TypeError) as exc:
            raise IFindRequestError("iFinD 未返回有效 access token") from exc

    def _post_json(self, path: str, payload: dict, *, headers: dict[str, str]) -> dict:
        request = Request(
            f"{API_BASE_URL}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise IFindRequestError(f"iFinD HTTP 请求失败：{exc}") from exc
