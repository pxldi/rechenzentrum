# =============================================================================
# Authentication flow with a required second factor
#
# Until 2026-09 every login ran authentik's stock default-authentication-flow.
# Its MFA stage has not_configured_action = skip, so an account with no device
# was waved through on a password, and nothing throttled guessing at it from the
# internet. This flow is built entirely here so its stages are in state and in
# review:
#
#   identification -> password -> second factor -> login
#
# The second factor accepts a passkey (WebAuthn) or a TOTP app. An account that
# has neither is sent to set one up before it gets a session, so enforcement
# does not depend on anyone enrolling first. Recovery codes count too, for
# anyone who created them in their user settings.
#
# The stock flow is left in place and unchanged. It is the way back in if this
# one breaks: https://auth.pxldi.de/if/flow/default-authentication-flow/
#
# Phone and desktop sync clients do not run this flow. Nextcloud, Immich,
# Jellyfin and the rest authenticate with their own accounts or app passwords,
# so a second factor here changes nothing for them.
# =============================================================================

resource "authentik_flow" "authentication" {
  name        = "rechenzentrum-authentication"
  title       = "Rechenzentrum"
  slug        = "rechenzentrum-authentication"
  designation = "authentication"
  # Only someone without a session may start a login.
  authentication = "require_unauthenticated"
  background     = "https://branding.pxldi.de/wallpapers/login-bg.avif"
}

resource "authentik_stage_identification" "authentication" {
  name                      = "rechenzentrum-authentication-identification"
  user_fields               = ["username", "email"]
  case_insensitive_matching = true
  # Answer the same way for a name that exists and one that does not, so the
  # form cannot be used to list accounts.
  pretend_user_exists = true
  show_matched_user   = false
}

resource "authentik_stage_password" "authentication" {
  name = "rechenzentrum-authentication-password"
  backends = [
    "authentik.core.auth.InbuiltBackend",
    "authentik.core.auth.TokenBackend",
  ]
  # Ends the flow after five wrong passwords; a new attempt starts over at the
  # username and costs reputation (see below).
  failed_attempts_before_cancel = 5
}

resource "authentik_stage_authenticator_totp" "setup" {
  name          = "rechenzentrum-setup-totp"
  friendly_name = "Authenticator-App (TOTP)"
  digits        = "6"
}

resource "authentik_stage_authenticator_webauthn" "setup" {
  name          = "rechenzentrum-setup-passkey"
  friendly_name = "Passkey"
  # Unset attachment allows both a phone or laptop's built-in authenticator and
  # a hardware key.
  user_verification        = "preferred"
  resident_key_requirement = "preferred"
}

resource "authentik_stage_authenticator_validate" "authentication" {
  name           = "rechenzentrum-authentication-mfa"
  device_classes = ["webauthn", "totp", "static"]
  # "configure" is the enforcement: no device, no session, until one of the
  # stages below has created one.
  not_configured_action = "configure"
  configuration_stages = [
    authentik_stage_authenticator_webauthn.setup.id,
    authentik_stage_authenticator_totp.setup.id,
  ]
  webauthn_user_verification = "preferred"
  # Ask every time. Forward-auth sessions last 24 hours, so this is at most
  # once a day per browser.
  last_auth_threshold = "seconds=0"
}

resource "authentik_stage_user_login" "authentication" {
  name = "rechenzentrum-authentication-login"
  # Same as the stock login stage: the session ends with the browser session.
  session_duration = "seconds=0"
}

resource "authentik_flow_stage_binding" "authentication_identification" {
  target = authentik_flow.authentication.uuid
  stage  = authentik_stage_identification.authentication.id
  order  = 10
}

resource "authentik_flow_stage_binding" "authentication_password" {
  target = authentik_flow.authentication.uuid
  stage  = authentik_stage_password.authentication.id
  order  = 20
}

resource "authentik_flow_stage_binding" "authentication_mfa" {
  target = authentik_flow.authentication.uuid
  stage  = authentik_stage_authenticator_validate.authentication.id
  order  = 30
}

resource "authentik_flow_stage_binding" "authentication_login" {
  target = authentik_flow.authentication.uuid
  stage  = authentik_stage_user_login.authentication.id
  order  = 100
}

# --- Reputation ---
#
# Every failed login lowers the score of the client address; at -5 the flow
# refuses that address until the score recovers (authentik's reputation expiry,
# a day by default). This works because Traefik now sees real client addresses
# (externalTrafficPolicy Local) and authentik trusts Traefik's X-Forwarded-For.
#
# Keyed on the address only. Keying on the username as well would let anyone
# on the internet lock a named account out by failing five logins for it.
resource "authentik_policy_reputation" "authentication" {
  name           = "rechenzentrum-authentication-reputation"
  check_ip       = true
  check_username = false
  threshold      = -5
}

resource "authentik_policy_binding" "authentication_reputation" {
  target = authentik_flow.authentication.uuid
  policy = authentik_policy_reputation.authentication.id
  order  = 0
}
