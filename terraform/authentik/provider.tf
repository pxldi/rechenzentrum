terraform {
  required_version = ">= 1.8.0"

  required_providers {
    authentik = {
      source = "goauthentik/authentik"
      # The provider is released per authentik server version. Hold it on the
      # server's minor series (kubernetes/infrastructure/authentik) and move
      # both in the same PR.
      version = "~> 2026.8.0"
    }
  }

  backend "s3" {
    bucket = "rechenzentrum-tf-state"
    key    = "authentik/terraform.tfstate"
    region = "auto"

    # Backblaze B2 S3-compatible endpoint
    # Set via env: AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    # Must send a checksum: the bucket has Object Lock, and S3 rejects a
    # PutObject carrying lock parameters with no Content-MD5 or
    # x-amz-checksum-* header. Same fix as velero's checksumAlgorithm (#991).
    skip_s3_checksum = false
  }
}

provider "authentik" {
  # Set via env: AUTHENTIK_URL, AUTHENTIK_TOKEN
  #
  # GitHub's runners sit outside the countries Cloudflare lets through. The
  # zone's `OpenTF Action` rule skips that block only for /api/v3/ on
  # auth.pxldi.de and only when this header carries the shared key, so the
  # rule no longer opens the API path to every source (docs/EXPOSURE.md).
  headers = var.waf_skip_key == "" ? {} : { "X-Tofu-Runner-Key" = var.waf_skip_key }
}
