"""A token check in front of an MCP server that has none of its own.

The servers in this image check claude.ai's bearer tokens themselves (see
oauth.py). An app built elsewhere, such as Snacky, serves MCP for the chat
bot without any login, and only a NetworkPolicy keeps others out. This gate
lets claude.ai reach such a server without changing it: it is an OAuth
resource server like the others, and it forwards every request that carries
a valid token to UPSTREAM_URL, without the token.

  UPSTREAM_URL        the MCP endpoint to forward to, inside the cluster:
                      http://<service>.<namespace>.svc.cluster.local:8000/mcp
  OAUTH_*             as in oauth.py; OAUTH_ISSUER is required here, because
                      a gate without a token check is an open proxy
"""
