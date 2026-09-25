# =============================================================================
# OIDC Applications
#
# Apps that speak OpenID Connect themselves, rather than sitting behind the
# forward-auth proxy in forward-auth-apps.tf. Use this when the app has its own
# user model and its own API clients: forward-auth gates the whole hostname,
# which means a browser extension or a mobile app holding a bearer token gets an
# authentik redirect it cannot follow.
#
# Everything here is managed.
# =============================================================================

# --- Karakeep ---
#
# Karakeep's own login form is disabled (DISABLE_PASSWORD_AUTH), so this
# provider is the only thing that will issue it a session and no password is
# ever presented to Karakeep.
#
# That collapses two login surfaces into one. It does NOT yet mean the surviving
# one is hardened: as deployed, authentik has no MFA validation stage bound to
# default-authentication-flow, no reputation policy, and no rate limit at the
# Traefik layer -- webauthn.tf is entirely commented out. So today this is one
# unthrottled password form instead of two, which is the right shape and an
# unfinished job.
resource "authentik_provider_oauth2" "karakeep" {
  name      = "karakeep"
  client_id = "lwMBkkGObTNW7kYNLOOFYFL9ji7ReujXiCp4bjnQ"
  # Set explicitly rather than letting authentik generate one, because the same
  # value has to reach the app through SOPS. Supplied by the workflow from the
  # KARAKEEP_OIDC_CLIENT_SECRET repository secret; it is never in this file.
  client_secret = var.karakeep_oidc_client_secret

  authorization_flow  = data.authentik_flow.default-authorization-flow.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id
  authentication_flow = data.authentik_flow.default-authentication-flow.id

  # Karakeep is handed one URL, OAUTH_WELLKNOWN_URL, and derives every endpoint
  # from the document it finds there. That document is per-application, so this
  # must stay per_provider rather than the global issuer.
  #
  # Without a signing key authentik falls back to signing id_tokens with HS256
  # using the client secret, and advertises only HS256 in its discovery
  # document. next-auth does not read that: openid-client keeps its default
  # id_token_signed_response_alg of RS256 and rejects the token with
  #
  #   unexpected JWT alg received, expected RS256, got: HS256
  #
  # after a completely successful authorization. Karakeep can be told otherwise
  # with OAUTH_ID_TOKEN_SIGNED_RESPONSE_ALG, but fixing the algorithm here is
  # the better half of the pair. This certificate is created and rotated by
  # authentik itself for exactly this purpose (authentik/crypto/apps.py, managed
  # goauthentik.io/crypto/jwt-managed).
  signing_key = data.authentik_certificate_key_pair.jwt.id

  # Left at authentik's default of hashed_user_id rather than user_email. `sub`
  # is what Karakeep stores as the account's provider id, so tying it to an
  # email address means changing an address orphans the account.
  issuer_mode                = "per_provider"
  include_claims_in_id_token = true

  # Must be set explicitly. The attribute is `optional + computed`, so leaving
  # it out does not inherit the value the admin UI would pick -- terraform sends
  # nothing and the API stores an empty list, which makes authentik reject the
  # authorize request with "Invalid grant_type for provider" and bounce the
  # browser straight back to the login page.
  grant_types = ["authorization_code", "refresh_token"]

  # next-auth builds the callback from the provider id, and Karakeep registers
  # its OIDC provider as `custom` (apps/web/server/auth.ts). Hence the path.
  # redirect_uri_type is what authentik already stores. Leaving it out made every
  # plan want to rewrite both URIs, because the provider sends the object without
  # it and reads it back set.
  allowed_redirect_uris = [
    {
      matching_mode     = "strict"
      redirect_uri_type = "authorization"
      url               = "https://links.${var.domain}/api/auth/callback/custom"
    },
  ]

  property_mappings = [
    for m in data.authentik_property_mapping_provider_scope.oidc : m.id
  ]
}

data "authentik_property_mapping_provider_scope" "oidc" {
  for_each   = toset(["openid", "email", "profile"])
  scope_name = each.value
}

resource "authentik_application" "karakeep" {
  name = "Karakeep"
  # The slug is load-bearing: it is what makes the discovery URL that
  # OAUTH_WELLKNOWN_URL in the app's config.env points at.
  slug              = "karakeep"
  protocol_provider = authentik_provider_oauth2.karakeep.id
  meta_launch_url   = "https://links.${var.domain}"
  meta_description  = "Bookmarks & Web Archive"
  meta_icon         = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/karakeep.png"
  open_in_new_tab   = true
}

# Karakeep provisions an account for anyone who completes the OIDC flow. It has
# to: DISABLE_SIGNUPS refuses every first OAuth login rather than just unknown
# ones, so turning it on with the password form off locks the instance
# permanently (see the app's config.env).
#
# So the membership check lives here. Only members of this group can reach the
# application at all, and a login that authentik refuses never reaches Karakeep
# to be provisioned.
resource "authentik_group" "karakeep_users" {
  name         = "karakeep-users"
  is_superuser = false
}

resource "authentik_policy_binding" "karakeep_users" {
  target = authentik_application.karakeep.uuid
  group  = authentik_group.karakeep_users.id
  order  = 0
}

# --- Vault MCP, for claude.ai ---
#
# The OAuth client that a claude.ai custom connector uses to reach the vault
# MCP server (kubernetes/apps/chatops/vault). claude.ai does the authorization
# code flow with PKCE from Anthropic's servers and hands the access token to
# the MCP server, which verifies it against this provider's JWKS
# (images/homelab-mcp/src/oauth.py). The server therefore needs no secret, and
# the client is public: the id below is not a credential, the login and the
# group binding are.
resource "authentik_provider_oauth2" "vault_mcp" {
  name        = "vault-mcp"
  client_id   = "E2NX2npEUxw6ZTCRfGpCpA5iZmtsfabEXWcfngTz"
  client_type = "public"

  authorization_flow  = data.authentik_flow.default-authorization-flow.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id
  authentication_flow = data.authentik_flow.default-authentication-flow.id

  # The MCP server checks iss against this provider's own issuer, so the
  # discovery document has to be the per-application one, same as Karakeep.
  # RS256 because the server verifies offline with the public key; HS256
  # would need the client secret a public client does not have.
  issuer_mode = "per_provider"
  signing_key = data.authentik_certificate_key_pair.jwt.id

  # claude.ai refreshes a token up to five minutes before it expires; with
  # authentik's default of five minutes every request would refresh.
  access_token_validity  = "hours=1"
  refresh_token_validity = "days=30"

  grant_types = ["authorization_code", "refresh_token"]

  # The one callback for claude.ai web, Desktop, mobile and Cowork.
  allowed_redirect_uris = [
    {
      matching_mode     = "strict"
      redirect_uri_type = "authorization"
      url               = "https://claude.ai/api/mcp/auth_callback"
    },
  ]

  # offline_access is what makes authentik issue a refresh token at all
  # (since 2024.2); claude.ai asks for it when the discovery document lists it.
  property_mappings = concat(
    [for m in data.authentik_property_mapping_provider_scope.oidc : m.id],
    [data.authentik_property_mapping_provider_scope.offline_access.id],
  )
}

data "authentik_property_mapping_provider_scope" "offline_access" {
  scope_name = "offline_access"
}

resource "authentik_application" "vault_mcp" {
  name = "Vault MCP"
  # The slug is the issuer: https://auth.<domain>/application/o/vault-mcp/,
  # which is OAUTH_ISSUER on the server and what the MCP server advertises
  # to claude.ai as its authorization server.
  slug              = "vault-mcp"
  protocol_provider = authentik_provider_oauth2.vault_mcp.id
  meta_description  = "The Obsidian vault, for claude.ai"
  meta_icon         = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/obsidian.png"
}

# The vault is one person's notes. A separate group rather than
# rechenzentrum-users, so that the household accounts, which can start this
# flow with the public client id, are refused at the login.
resource "authentik_group" "vault_mcp_users" {
  name         = "vault-mcp-users"
  is_superuser = false
  users        = [data.authentik_user.pxldi.id]
}

resource "authentik_policy_binding" "vault_mcp_users" {
  target = authentik_application.vault_mcp.uuid
  group  = authentik_group.vault_mcp_users.id
  order  = 0
}
