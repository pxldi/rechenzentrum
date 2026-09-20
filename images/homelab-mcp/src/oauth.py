"""Bearer tokens for a server that claude.ai reaches over the internet.

The servers in this image run without any authentication of their own; the
NetworkPolicy beside each Deployment is what keeps everyone but ZeroClaw out.
A claude.ai custom connector reaches its server from Anthropic's network, so
that server has to check who is calling. It does so the way the MCP
authorization spec asks: the server is an OAuth resource server, Authentik is
the authorization server, and every request to /mcp carries an access token
that Authentik issued for this server's client id.

Four variables switch it on. With OAUTH_ISSUER unset a server runs exactly as
before.

  OAUTH_ISSUER        the provider's issuer URL, with its trailing slash:
                      https://auth.<domain>/application/o/<slug>/
  OAUTH_AUDIENCE      the provider's client id; a token's aud has to be it
  OAUTH_RESOURCE_URL  this server as the connector sees it: https://<host>/mcp
  OAUTH_JWKS_URL      where the signing keys are fetched; defaults to
                      <issuer>jwks/. Set it to the in-cluster Service URL so
                      the fetch never leaves the cluster.

Tokens are verified offline against the provider's key set, so the server
holds no client secret and the client is a public one with PKCE. The SDK
serves the protected-resource metadata at
/.well-known/oauth-protected-resource/mcp and answers 401 with a pointer to
it, which is how the connector finds Authentik.
"""

import logging
import os

import anyio
import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

log = logging.getLogger(__name__)


class JwksTokenVerifier:
    """A TokenVerifier for RS256 JWTs signed with a key from a JWKS URL."""

    def __init__(self, jwks_url: str, issuer: str, audience: str) -> None:
        self._issuer = issuer
        self._audience = audience
        # The key set is cached for five minutes (the client's default), and a
        # key id the cache does not know triggers a refetch, so a key rotation
        # in Authentik needs no restart here.
        self._jwks = jwt.PyJWKClient(jwks_url, cache_keys=True)

    def _decode(self, token: str) -> dict:
        key = self._jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self._audience,
            issuer=self._issuer,
            options={"require": ["exp", "iss", "aud"]},
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        # PyJWKClient fetches with urllib, synchronously; keep it off the loop.
        try:
            claims = await anyio.to_thread.run_sync(self._decode, token)
        except jwt.PyJWTError as e:
            log.info("rejected bearer token: %s", e)
            return None
        scope = claims.get("scope")
        scopes = scope.split() if isinstance(scope, str) else list(claims.get("scp") or [])
        return AccessToken(
            token=token,
            client_id=self._audience,
            scopes=scopes,
            expires_at=claims.get("exp"),
            subject=claims.get("sub"),
            claims=claims,
        )


def server_kwargs() -> dict:
    """The MCPServer keyword arguments that turn the token check on, or {}."""
    issuer = os.environ.get("OAUTH_ISSUER", "").strip()
    if not issuer:
        return {}
    audience = os.environ["OAUTH_AUDIENCE"]
    resource = os.environ["OAUTH_RESOURCE_URL"]
    jwks_url = os.environ.get("OAUTH_JWKS_URL") or issuer.rstrip("/") + "/jwks/"
    return {
        "token_verifier": JwksTokenVerifier(jwks_url, issuer, audience),
        # Authentik puts the client id in aud, not the resource URL, so the
        # SDK's resource check stays off; the audience check in _decode is
        # what binds a token to this server.
        "auth": AuthSettings(issuer_url=issuer, resource_server_url=resource, validate_token_resource=False),
    }
