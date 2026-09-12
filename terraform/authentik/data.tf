# =============================================================================
# Shared data sources - reference existing authentik objects
# =============================================================================

data "authentik_flow" "default-authorization-flow" {
  slug = "default-provider-authorization-implicit-consent"
}

data "authentik_flow" "default-invalidation-flow" {
  slug = "default-provider-invalidation-flow"
}

data "authentik_flow" "default-authentication-flow" {
  slug = "default-authentication-flow"
}

# The two below are the brand's own flows. Note the invalidation flow is not
# the one above: a brand ends a session with default-invalidation-flow, while an
# OIDC provider uses default-provider-invalidation-flow.
data "authentik_flow" "brand-invalidation-flow" {
  slug = "default-invalidation-flow"
}

data "authentik_flow" "brand-user-settings-flow" {
  slug = "default-user-settings-flow"
}

# Used as the signing_key on OIDC providers; without one authentik signs
# id_tokens with HS256 and clients that expect RS256 reject them.
#
# This is the keypair authentik generates at bootstrap. Newer installs also get
# "authentik Internal JWT Certificate" from managed_jwt_cert, but that reconcile
# only creates a cert when none carries the managed key -- it never renames an
# existing one -- so an instance bootstrapped before that naming keeps this one
# and never grows the other. This cluster is such an instance; looking up the
# JWT name failed at plan time with "No matching groups found".
#
# The data source takes an exact name and cannot list without one, so this
# string is load-bearing. If it ever stops matching, read the name from
# System -> Certificates in the authentik UI.
data "authentik_certificate_key_pair" "jwt" {
  name = "authentik Self-signed Certificate"
}
