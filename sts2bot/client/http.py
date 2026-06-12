"""HTTP client for the STS2MCP mod API (localhost only)."""

from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from sts2bot.client.actions import Action
from sts2bot.client.models import GameState, parse_state

DEFAULT_BASE_URL = "http://127.0.0.1:15526"


class Sts2ConnectionError(Exception):
    """Mod API unreachable — game not running, mod not loaded, or mid-load."""


class ActionResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    message: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def detail(self) -> str:
        return self.message or self.error or self.status


class Sts2Client:
    """Thin synchronous wrapper over the mod's REST endpoints.

    Retries connection-level failures briefly (the API drops during scene loads);
    game-logic errors come back as ActionResult(status="error") and are NOT retried —
    they're the policy layer's problem.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        connect_retries: int = 3,
        retry_wait: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.connect_retries = connect_retries
        self.retry_wait = retry_wait

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Sts2Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- plumbing

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.connect_retries + 1):
            try:
                resp = self._client.request(method, path, **kwargs)
                resp.raise_for_status()
                return resp
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                last_exc = e
                if attempt < self.connect_retries:
                    time.sleep(self.retry_wait)
            except httpx.HTTPStatusError as e:
                # 4xx/5xx with a JSON body is still a meaningful API answer; surface it.
                if e.response.headers.get("content-type", "").startswith("application/json"):
                    return e.response
                last_exc = e
                break
        raise Sts2ConnectionError(
            f"{method} {path} failed after {self.connect_retries + 1} attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------- state & actions

    def get_state_raw(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/singleplayer").json()

    def get_state(self) -> GameState:
        return parse_state(self.get_state_raw())

    def act(self, action: Action) -> ActionResult:
        resp = self._request("POST", "/api/v1/singleplayer", json=action.payload())
        return ActionResult.model_validate(resp.json())

    # ------------------------------------------------------------- profiles & data

    def list_profiles(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/profiles").json()

    def switch_profile(self, profile_id: int) -> ActionResult:
        resp = self._request(
            "POST", "/api/v1/profiles", json={"action": "switch", "profile_id": profile_id}
        )
        return ActionResult.model_validate(resp.json())

    def get_profile(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/profile").json()

    def get_compendium(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/compendium").json()

    def wiki(self, query: str, item_type: str = "all", limit: int = 10) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/wiki",
            params={"query": query, "item_type": item_type, "limit": limit},
        ).json()
