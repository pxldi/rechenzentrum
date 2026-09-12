# =============================================================================
# WebAuthn / YubiKey 2FA Setup
# =============================================================================

# Stage for users to enroll their YubiKey / security key
#resource "authentik_stage_authenticator_webauthn" "yubikey-setup" {
#  name                     = "yubikey-webauthn-setup"
#  friendly_name            = "Security Key (YubiKey)"
#  user_verification         = "required"
#  resident_key_requirement  = "preferred"
#  authenticator_attachment  = "cross-platform"
#  configure_flow            = data.authentik_flow.default-authentication-flow.id
#}

# Ensure the default authentication flow's MFA validation stage
# includes WebAuthn as an allowed device class.
#
# NOTE: This references the default authenticator validation stage.
# If you've customized your authentication flow, adjust the name accordingly.
# You may need to import the existing stage first:
#   tofu import authentik_stage_authenticator_validate.mfa <stage-uuid>
#
# resource "authentik_stage_authenticator_validate" "mfa" {
#   name           = "default-authentication-mfa-validation"
#   device_classes = ["webauthn", "totp", "static"]
# }
#