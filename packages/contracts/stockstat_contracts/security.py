from __future__ import annotations

import hashlib
import hmac


def parse_token_rules(values) -> dict[str, frozenset[str]]:
    rules = {}
    for value in values or ():
        token, separator, scopes = value.partition("=")
        if not separator or not token.strip():
            raise ValueError("token rules must use TOKEN=scope1,scope2")
        rules[token.strip()] = frozenset(
            scope.strip() for scope in scopes.split(",") if scope.strip()
        )
    return rules


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        return None
    return token


def token_has_scope(
    authorization: str | None,
    scope: str,
    rules: dict[str, frozenset[str]] | None,
) -> bool:
    if not rules:
        return True
    token = bearer_token(authorization)
    if token is None:
        return False
    for candidate, scopes in rules.items():
        if hmac.compare_digest(token, candidate):
            return scope in scopes or "*" in scopes
    return False


def token_matches(authorization: str | None, expected: str | None) -> bool:
    if expected is None:
        return True
    token = bearer_token(authorization)
    return token is not None and hmac.compare_digest(token, expected)


def token_principal(
    authorization: str | None, rules: dict[str, frozenset[str]] | None
) -> str | None:
    token = bearer_token(authorization)
    if token is None or not rules:
        return None
    for candidate in rules:
        if hmac.compare_digest(token, candidate):
            return "token:" + hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:24]
    return None
