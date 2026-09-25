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
