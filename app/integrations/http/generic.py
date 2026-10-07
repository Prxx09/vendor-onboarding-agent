import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError

from app.integrations.bank import BankVerificationResult, RoutingLookupResult
from app.integrations.base import VerificationMode, VerificationResult, VerificationStatus
from app.integrations.circuit_breaker import CircuitBreaker
from app.integrations.registry import CompanyVerificationResult
from app.integrations.sanctions import SanctionsMatch, SanctionsResult
from app.integrations.tax import TaxVerificationResult

_RESULT_TYPES: dict[str, type[VerificationResult]] = {
    "company_registry": CompanyVerificationResult,
    "tax_id": TaxVerificationResult,
    "bank_account": BankVerificationResult,
    "bank_routing": RoutingLookupResult,
    "sanctions": SanctionsResult,
}


class GenericHttpProvider:
    provider_name = "generic_http"
    mode = VerificationMode.LIVE

    def __init__(self, config: dict[str, Any], *, transport: httpx.BaseTransport | None = None,
                 client: httpx.Client | None = None, store_raw: bool = False,
                 circuit_breaker: CircuitBreaker | None = None):
        self.config = config.get("capabilities", config) if isinstance(config, dict) else {}
        self.client = client or httpx.Client(transport=transport)
        self.store_raw = store_raw
        self.circuit_breakers = (
            circuit_breaker if isinstance(circuit_breaker, dict) else
            {name: circuit_breaker for name in _RESULT_TYPES} if circuit_breaker else {}
        )

    def verify_company(self, registration_number: str, legal_name: str, country: str):
        return self._request("company_registry", {
            "registration_number": registration_number, "legal_name": legal_name, "country": country,
        })

    def verify_tax_id(self, tax_id: str, country: str, legal_name: str):
        return self._request("tax_id", {"tax_id": tax_id, "country": country, "legal_name": legal_name})

    def verify_account(self, account_number: str, routing_code: str, account_holder_name: str,
                       bank_name: str | None, country: str, currency: str | None):
        return self._request("bank_account", {
            "account_number": account_number, "routing_code": routing_code,
            "account_holder_name": account_holder_name, "bank_name": bank_name,
            "country": country, "currency": currency,
        })

    def lookup_routing_code(self, routing_code: str):
        return self._request("bank_routing", {"routing_code": routing_code})

    def screen(self, name: str, aliases: list[str], country: str):
        return self._request("sanctions", {"name": name, "aliases": aliases, "country": country})

    def _request(self, capability: str, values: dict[str, Any]):
        result_type = _RESULT_TYPES[capability]
        config = self.config.get(capability)
        if not isinstance(config, dict) or not config:
            return self._result(result_type, capability, VerificationStatus.NOT_CONFIGURED,
                                error="Capability is not configured.")
        auth = config.get("auth", {})
        if not isinstance(auth, dict):
            return self._result(result_type, capability, VerificationStatus.NOT_CONFIGURED,
                                error="Capability authentication configuration is invalid.")
        secret_name = auth.get("secret_env")
        secret = os.getenv(secret_name) if secret_name else None
        username_name = auth.get("username_env")
        username = os.getenv(username_name) if username_name else None
        auth_type = auth.get("type", "none")
        secret_required = auth_type in {"bearer", "api_key_header", "basic"}
        if (secret_required and not secret_name) or (secret_name and not secret) or (username_name and not username):
            return self._result(result_type, capability, VerificationStatus.NOT_CONFIGURED,
                                error="Required authentication environment variable is unset.")

        def operation():
            return self._send(config, capability, values, result_type, auth, secret, username)

        breaker = self.circuit_breakers.get(capability)
        if breaker:
            try:
                if breaker.is_open:
                    return self._result(result_type, capability, VerificationStatus.UNAVAILABLE,
                                        error="Circuit breaker is open.")
                result = operation()
                if result.status == VerificationStatus.UNAVAILABLE:
                    breaker.record_failure()
                else:
                    breaker.record_success()
                return result
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, ValidationError):
                breaker.record_failure()
                return self._result(result_type, capability, VerificationStatus.UNAVAILABLE,
                                    error="Provider request failed.")
        try:
            return operation()
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, ValidationError):
            return self._result(result_type, capability, VerificationStatus.UNAVAILABLE,
                                error="Provider request failed.")

    def _send(self, config, capability, values, result_type, auth, secret, username):
        started = time.perf_counter()
        base_url = config.get("base_url", "")
        path = str(config.get("path", "")).format(**values)
        url = base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = dict(config.get("headers", {}))
        auth_type = auth.get("type", "none")
        auth_tuple = None
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif auth_type == "api_key_header":
            headers[auth.get("header_name", "X-API-Key")] = secret
        elif auth_type == "basic":
            auth_tuple = (username, secret)
        elif auth_type != "none":
            return self._result(result_type, capability, VerificationStatus.NOT_CONFIGURED,
                                error="Unsupported authentication type.")
        body_template = config.get("request_body_template")
        body = _render(body_template, values) if body_template is not None else None
        timeout = float(config.get("timeout", 10))
        retries = max(0, int(config.get("retries", 2)))
        response = None
        for attempt in range(retries + 1):
            try:
                response = self.client.request(
                    config.get("method", "POST").upper(), url, headers=headers,
                    json=body, timeout=timeout, auth=auth_tuple,
                )
                if (response.status_code == 429 or response.status_code >= 500) and attempt < retries:
                    continue
                break
            except httpx.TimeoutException:
                if attempt < retries:
                    continue
                raise
            except httpx.HTTPError:
                raise
        elapsed = round((time.perf_counter() - started) * 1000)
        if response is None:
            return self._result(result_type, capability, VerificationStatus.UNAVAILABLE,
                                latency_ms=elapsed, error="Provider request failed.")
        if response.status_code == 404:
            return self._result(result_type, capability, VerificationStatus.NOT_FOUND,
                                latency_ms=elapsed, error=None)
        if response.status_code == 429 or response.status_code >= 500 or response.is_error:
            return self._result(result_type, capability, VerificationStatus.UNAVAILABLE,
                                latency_ms=elapsed, error=f"Provider returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError:
            return self._result(result_type, capability, VerificationStatus.UNAVAILABLE,
                                latency_ms=elapsed, error="Provider returned malformed JSON.")
        status = self._mapped_status(config, payload)
        status_error = (
            "Provider response status was missing or unmapped."
            if config.get("status_field") and status == VerificationStatus.UNAVAILABLE else None
        )
        mapping = config.get("response_mapping", {})
        normalized = {target: _lookup(payload, source) for target, source in mapping.items()}
        if isinstance(result_type, type) and issubclass(result_type, SanctionsResult):
            normalized["matches"] = [SanctionsMatch.model_validate(item) for item in (normalized.get("matches") or [])]
        kwargs = {
            "capability": capability, "provider_name": config.get("provider_name", self.provider_name),
            "mode": VerificationMode.LIVE, "status": status, "latency_ms": elapsed,
            "error": status_error,
            "details": {"response": payload} if self.store_raw else {}, **normalized,
        }
        return result_type.model_validate(kwargs)

    def _mapped_status(self, config, payload):
        source = config.get("status_field")
        remote = _lookup(payload, source) if source else None
        mapped = config.get("status_mapping", {}).get(str(remote).casefold())
        if mapped:
            return VerificationStatus(mapped)
        if source:
            return VerificationStatus.UNAVAILABLE
        return VerificationStatus.VERIFIED

    @staticmethod
    def _result(result_type, capability, status, *, latency_ms=0, error=None):
        return result_type(
            capability=capability, provider_name=GenericHttpProvider.provider_name,
            mode=VerificationMode.LIVE, status=status,
            checked_at=datetime.now(UTC), latency_ms=latency_ms, error=error,
        )


def _lookup(payload: Any, path: str | None):
    if not path:
        return None
    current = payload
    for part in path.split("."):
        current = current.get(part) if isinstance(current, dict) else None
    return current


def _render(template: Any, values: dict[str, Any]):
    if isinstance(template, dict):
        return {key: _render(value, values) for key, value in template.items()}
    if isinstance(template, list):
        return [_render(value, values) for value in template]
    if isinstance(template, str) and template.startswith("{") and template.endswith("}"):
        return values.get(template[1:-1])
    return template
