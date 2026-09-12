# =============================================================================
# Brand
#
# The look of every authentik page: the login flow, the user portal and the
# admin interface. It was configured by hand in the UI, which meant the only
# copy of it lived in the authentik database and nothing reviewed a change to
# it. Bringing it here put it behind the same PR + tofu-authentik path as the
# providers.
#
# The CSS is in brand.css rather than inline so an editor treats it as CSS.
# =============================================================================

# The brand already exists -- authentik creates authentik-default at bootstrap
# and this one has been edited in the UI since. Creating the resource without
# adopting that row would leave two brands claiming the same domain, so the
# import block takes over the existing one on the first apply. It is a no-op on
# every apply after that and can stay.
import {
  to = authentik_brand.default
  id = "8674d8f8-754f-4eb2-9453-4612bf153bb6"
}

resource "authentik_brand" "default" {
  domain  = "authentik-default"
  default = true

  branding_title      = "Rechenzentrum"
  branding_logo       = "https://branding.pxldi.de/icons/wordmark.svg"
  branding_favicon    = "https://branding.pxldi.de/icons/house-mark.svg"
  branding_custom_css = file("${path.module}/brand.css")

  # The fallback background for any flow that does not carry its own. Flow.
  # background_url() returns the flow's own background and only falls back to
  # this, so default-authentication-flow still draws the old PNG from the flow
  # object until that field is cleared; this covers invalidation, user settings
  # and anything added later.
  #
  # The favicon is not a cut of the logo. The wordmark is 5.6:1 and unreadable
  # at 16px, so the tab keeps the house-and-rack symbol.
  branding_default_flow_background = "https://branding.pxldi.de/wallpapers/login-bg.avif"

  flow_authentication = data.authentik_flow.default-authentication-flow.id
  flow_invalidation   = data.authentik_flow.brand-invalidation-flow.id
  flow_user_settings  = data.authentik_flow.brand-user-settings-flow.id

  # Left unset because the live brand has them unset: flow_recovery,
  # flow_unenrollment, flow_device_code, default_application, web_certificate,
  # client_certificates, attributes.
}
