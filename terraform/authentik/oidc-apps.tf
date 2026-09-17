# =============================================================================
# OIDC Applications
#
# Apps that speak OpenID Connect themselves, rather than sitting behind the
# forward-auth proxy in forward-auth-apps.tf. Use this when the app has its own
# user model and its own API clients: forward-auth gates the whole hostname,
# which means a browser extension or a mobile app holding a bearer token gets an
# authentik redirect it cannot follow.
#
# Everything here is managed, ryot included since 2026-09-02. It was made by
# hand in the UI, which is why it is adopted with import blocks rather than
# created.
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

# --- Ryot ---
#
# Adopted, not created. It was set up by hand in the UI long before this file
# existed, and it was the last application in the instance with no policy
# binding: every account could open it. Everything below matches what was
# already there, read out of the running instance, so the import is a no-op
# apart from the two changes called out.
#
# The import IDs are what the provider stores as the resource ID:
# authentik_provider_oauth2 keeps the numeric pk, authentik_application keeps
# the slug (pkg/provider/resource_application.go sets d.SetId(res.Slug)).
import {
  to = authentik_provider_oauth2.ryot
  id = "28"
}

import {
  to = authentik_application.ryot
  id = "ryot-oidc"
}

resource "authentik_provider_oauth2" "ryot" {
  name      = "Ryot"
  client_id = "ZrUM4jgfvdhfmhFGe1mBLgv6Q7NVrgojGTY4xMvt"
  # The value already in use, carried in through the workflow from the
  # RYOT_OIDC_CLIENT_SECRET repository secret. It is the same string as
  # OIDC_CLIENT_SECRET in the ryot namespace -- checked by hash, not by eye --
  # so adopting the provider does not rotate it out from under the app.
  client_secret = var.ryot_oidc_client_secret

  authorization_flow  = data.authentik_flow.default-authorization-flow.id
  invalidation_flow   = data.authentik_flow.default-invalidation-flow.id
  authentication_flow = data.authentik_flow.default-authentication-flow.id

  # As found: per-provider issuer, hashed_user_id subject, claims in the token,
  # and the self-signed keypair every other provider here signs with.
  issuer_mode                = "per_provider"
  sub_mode                   = "hashed_user_id"
  include_claims_in_id_token = true
  signing_key                = data.authentik_certificate_key_pair.jwt.id

  access_code_validity   = "minutes=1"
  access_token_validity  = "minutes=5"
  refresh_token_validity = "days=30"

  # Change one of two. The UI created this with all seven grant types, so the
  # provider would have issued tokens for the password grant, the implicit
  # flow, client_credentials and the device code flow. ryot uses none of them:
  # it does the redirect and refreshes.
  grant_types = ["authorization_code", "refresh_token"]

  # redirect_uri_type is what authentik already stores. Leaving it out made every
  # plan want to rewrite both URIs, because the provider sends the object without
  # it and reads it back set.
  allowed_redirect_uris = [
    {
      matching_mode     = "strict"
      redirect_uri_type = "authorization"
      url               = "https://track.${var.domain}/api/auth/callback/oidc"
    },
  ]

  property_mappings = [
    for m in data.authentik_property_mapping_provider_scope.oidc : m.id
  ]
}

resource "authentik_application" "ryot" {
  name              = "Ryot"
  slug              = "ryot-oidc"
  protocol_provider = authentik_provider_oauth2.ryot.id
  # Change two of two, and cosmetic: the application had no launch URL, icon or
  # description, so it sat blank in the user's application list.
  meta_launch_url  = "https://track.${var.domain}"
  meta_description = "Media and Fitness Tracking"
  meta_icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/ryot.png"
  open_in_new_tab  = true
}

# The point of the exercise. Ryot is a household app rather than a per-person
# one, so it asks for the same group the forward-auth apps do.
resource "authentik_policy_binding" "ryot_users" {
  target = authentik_application.ryot.uuid
  group  = authentik_group.rechenzentrum_users.id
  order  = 0
}
