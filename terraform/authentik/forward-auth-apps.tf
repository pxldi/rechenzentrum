# =============================================================================
# Forward Auth Applications
# Each app gets a proxy provider (forward_single) + application resource
# =============================================================================

locals {
  forward_auth_apps = {
    sonarr = {
      name        = "Sonarr"
      host        = "sonarr.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/sonarr.png"
      description = "TV Series Management"
    }
    radarr = {
      name        = "Radarr"
      host        = "radarr.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/radarr.png"
      description = "Movie Management"
    }
    prowlarr = {
      name        = "Prowlarr"
      host        = "prowlarr.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/prowlarr.png"
      description = "Indexer Management"
    }
    sabnzbd = {
      name        = "SABnzbd"
      host        = "sabnzbd.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/sabnzbd.png"
      description = "Usenet Downloader"
    }
    searxng = {
      name        = "SearXNG"
      host        = "search.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/searxng.png"
      description = "Private Search Engine"
    }
    slskd = {
      name        = "Slskd"
      host        = "slskd.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/slskd.png"
      description = "Soulseek Music Sharing"
    }
    soulsync = {
      name        = "SoulSync"
      host        = "soul.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/soulsync.png"
      description = "Music Discovery / Media Management & Soulseek Downloads"
    }
    schall = {
      name        = "Schall"
      host        = "schall.${var.domain}"
      icon        = ""
      description = "Music Collection Manager"
    }
    jdownloader = {
      name        = "JDownloader"
      host        = "download.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/jdownloader.png"
      description = "Downloader"
    }
    gatus = {
      name        = "Gatus"
      host        = "uptime.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/gatus.png"
      description = "Uptime Checks & Status Page"
    }
    traefik-dashboard = {
      name        = "Traefik Dashboard"
      host        = "traefik.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/traefik.png"
      description = "Reverse Proxy Dashboard"
    }
    velero = {
      name        = "Velero UI"
      host        = "velero.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/velero.png"
      description = "Kubernetes Backup Management"
    }
    adventurelog-admin = {
      name        = "AdventureLog Admin"
      host        = "travel-admin.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/adventurelog.png"
      description = "AdventureLog Django Admin"
    }
    grafana = {
      name        = "Grafana"
      host        = "grafana.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/grafana.png"
      description = "Metrics & Dashboards"
    }
    excalidraw = {
      name        = "Excalidraw"
      host        = "draw.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/excalidraw.png"
      description = "Whiteboard & Diagrams"
    }
    firefly = {
      name        = "Firefly III"
      host        = "finance.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/firefly-iii.png"
      description = "Personal Finance"
    }
    firefly-importer = {
      name        = "Firefly Importer"
      host        = "finance-import.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/firefly-iii.png"
      description = "Bank Import for Firefly III"
    }
    firefly-pico = {
      name        = "Firefly Pico"
      host        = "money.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/firefly-iii.png"
      description = "Finance Dashboard"
    }
    wealthfolio = {
      name        = "Wealthfolio"
      host        = "wealth.${var.domain}"
      icon        = "https://cdn.jsdelivr.net/gh/selfhst/icons@main/png/wealthfolio.png"
      description = "Net Worth & Investments"
    }
    fredy = {
      name        = "Fredy"
      host        = "immo.${var.domain}"
      icon        = ""
      description = "Property listing scraper"
    }
  }
}

# --- Proxy Providers (one per app) ---

resource "authentik_provider_proxy" "forward_auth" {
  for_each = local.forward_auth_apps

  name               = each.key
  mode               = "forward_single"
  external_host      = "https://${each.value.host}"
  authorization_flow = data.authentik_flow.default-authorization-flow.id
  invalidation_flow  = data.authentik_flow.default-invalidation-flow.id

  access_token_validity = "hours=24"
}

# --- Applications (one per app) ---

resource "authentik_application" "forward_auth" {
  for_each = local.forward_auth_apps

  name              = each.value.name
  slug              = each.key
  protocol_provider = authentik_provider_proxy.forward_auth[each.key].id
  meta_launch_url   = "https://${each.value.host}"
  meta_description  = each.value.description
  meta_icon         = each.value.icon != "" ? each.value.icon : null
  open_in_new_tab   = true
}

# --- Who may reach any of this ---
#
# A forward-auth application with no policy binding is open to every account
# authentik has: the outpost checks that you are signed in and, with nothing
# bound, checks nothing else. That was invisible while there was one human
# account. It stops being invisible the moment there is a second one, because
# "has a login" would mean Grafana, the Traefik dashboard and Velero.
#
# So membership is explicit. Every application above asks for this group, and
# the group's members are managed here rather than in the admin interface: a
# name added by hand there is removed on the next apply. Add people in this
# file.
#
data "authentik_user" "pxldi" {
  username = "pxldi"
}

data "authentik_user" "akadmin" {
  username = "akadmin"
}

resource "authentik_group" "rechenzentrum_users" {
  name         = "rechenzentrum-users"
  is_superuser = false
  users = [
    data.authentik_user.pxldi.id,
    data.authentik_user.akadmin.id,
  ]
}

resource "authentik_policy_binding" "forward_auth_users" {
  for_each = local.forward_auth_apps

  target = authentik_application.forward_auth[each.key].uuid
  group  = authentik_group.rechenzentrum_users.id
  order  = 0
}

# --- Outpost: assign all forward auth apps to the embedded outpost ---

data "authentik_outpost" "embedded" {
  name = "authentik Embedded Outpost"
}

import {
  to = authentik_outpost.embedded
  id = "0a0da32a-3676-42be-a05a-5b4d19330828"
}

resource "authentik_outpost" "embedded" {
  name               = "authentik Embedded Outpost"
  type               = "proxy"
  protocol_providers = [for app in authentik_provider_proxy.forward_auth : app.id]
  config = jsonencode({
    authentik_host          = var.authentik_host
    authentik_host_browser  = var.authentik_host
    authentik_host_insecure = false
  })
}
