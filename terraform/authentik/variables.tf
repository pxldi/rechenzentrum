variable "domain" {
  description = "Base domain for all applications"
  type        = string
  default     = "pxldi.de"
}

variable "authentik_host" {
  description = "Authentik external URL"
  type        = string
  default     = "https://auth.pxldi.de"
}

variable "karakeep_oidc_client_secret" {
  description = "OIDC client secret shared between the authentik provider and Karakeep's SOPS secret. Set via TF_VAR_karakeep_oidc_client_secret."
  type        = string
  sensitive   = true
}

variable "waf_skip_key" {
  description = "Value of the X-Tofu-Runner-Key header that Cloudflare's OpenTF Action rule requires before it skips the country block. Set via TF_VAR_waf_skip_key from the OPENTF_WAF_KEY secret; empty when run from inside the house."
  type        = string
  sensitive   = true
  default     = ""
}
