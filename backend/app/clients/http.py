from __future__ import annotations

import asyncio
import json as json_module
import logging
import ssl
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx


logger = logging.getLogger(__name__)


class PublicAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class RetryableHTTPClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._parsed_base = urlparse(self.base_url)
        self._headers = dict(headers or {})
        self.max_attempts = max_attempts
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers=self._headers,
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, *, json: Any = None) -> Any:
        return await self._request("POST", path, json=json)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self._client.request(method, path, **kwargs)
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.6 * (2**attempt)
                    if attempt < self.max_attempts - 1:
                        await asyncio.sleep(delay)
                        continue
                if response.status_code >= 400:
                    payload = _safe_json(response)
                    raise PublicAPIError(
                        f"{method} {self.base_url}{path} returned HTTP {response.status_code}",
                        status_code=response.status_code,
                        payload=payload,
                    )
                return _safe_json(response)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, PublicAPIError) as exc:
                last_error = exc
                if _looks_like_dns_failure(exc) and self._parsed_base.hostname:
                    try:
                        return await self._request_via_doh(method, path, **kwargs)
                    except Exception as doh_exc:  # noqa: BLE001
                        last_error = doh_exc
                if isinstance(exc, PublicAPIError) and exc.status_code and exc.status_code < 500 and exc.status_code != 429:
                    break
                if attempt < self.max_attempts - 1:
                    await asyncio.sleep(0.6 * (2**attempt))
                    continue
        raise PublicAPIError(str(last_error or "request failed")) from last_error

    async def _request_via_doh(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._parsed_base.scheme != "https" or not self._parsed_base.hostname:
            raise PublicAPIError("DNS fallback supports HTTPS hosts only")
        host = self._parsed_base.hostname
        ip = await _resolve_a_record(host)
        target = path
        params = kwargs.get("params")
        if params:
            separator = "&" if "?" in target else "?"
            target += separator + urlencode(params, doseq=True)
        body = b""
        headers = {
            "Host": host,
            "User-Agent": self._headers.get("User-Agent", "WeatherEdgeflow/0.1"),
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if "json" in kwargs and kwargs["json"] is not None:
            body = json_module.dumps(kwargs["json"]).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))

        ssl_context = ssl.create_default_context()
        reader, writer = await asyncio.open_connection(ip, 443, ssl=ssl_context, server_hostname=host)
        request_lines = [f"{method} {target} HTTP/1.1", *[f"{key}: {value}" for key, value in headers.items()], "", ""]
        writer.write("\r\n".join(request_lines).encode("ascii") + body)
        await writer.drain()
        raw = await reader.read()
        writer.close()
        await writer.wait_closed()
        status_code, response_headers, response_body = _parse_http_response(raw)
        if status_code >= 400:
            raise PublicAPIError(
                f"{method} {self.base_url}{path} returned HTTP {status_code}",
                status_code=status_code,
                payload=response_body[:500].decode("utf-8", errors="replace"),
            )
        try:
            return json_module.loads(response_body.decode("utf-8"))
        except ValueError as exc:
            raise PublicAPIError("Malformed JSON response", status_code=status_code, payload=response_body[:500]) from exc


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise PublicAPIError("Malformed JSON response", status_code=response.status_code, payload=response.text[:500]) from exc


def _looks_like_dns_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return "getaddrinfo failed" in text or "could not resolve" in text or "name or service not known" in text


async def _resolve_a_record(host: str) -> str:
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get("https://dns.google/resolve", params={"name": host, "type": "A"})
        response.raise_for_status()
        payload = response.json()
    answers = payload.get("Answer") if isinstance(payload, dict) else None
    if not isinstance(answers, list):
        raise PublicAPIError(f"DNS-over-HTTPS did not return A records for {host}")
    for answer in answers:
        if isinstance(answer, dict) and answer.get("type") == 1 and answer.get("data"):
            return str(answer["data"])
    raise PublicAPIError(f"DNS-over-HTTPS did not return usable A records for {host}")


def _parse_http_response(raw: bytes) -> tuple[int, dict[str, str], bytes]:
    header_raw, _, body = raw.partition(b"\r\n\r\n")
    header_text = header_raw.decode("iso-8859-1")
    lines = header_text.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/"):
        raise PublicAPIError("Invalid HTTP response from DNS fallback")
    parts = lines[0].split(" ", 2)
    status_code = int(parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = _decode_chunked(body)
    return status_code, headers, body


def _decode_chunked(body: bytes) -> bytes:
    output = bytearray()
    cursor = 0
    while cursor < len(body):
        line_end = body.find(b"\r\n", cursor)
        if line_end == -1:
            break
        size_line = body[cursor:line_end].split(b";", 1)[0]
        size = int(size_line.decode("ascii"), 16)
        cursor = line_end + 2
        if size == 0:
            break
        output.extend(body[cursor : cursor + size])
        cursor += size + 2
    return bytes(output)
