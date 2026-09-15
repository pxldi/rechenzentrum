# Exposure inventory

Generated from the live cluster on 2026-09-13, after the internal-only rollout.
Routes do not prove internet reachability; DNS and the router decide that too.

Three states:

- **LAN/tailnet + Authentik** — the `internal-only` middleware refuses any source
  address outside the house LAN and the tailnet, and an Authentik login follows.
  Unreachable from the internet.
- **Authentik** — reachable from the internet, gated by an Authentik login.
- **public** — reachable from the internet, protected only by whatever the
  application itself enforces.

The `/outpost.goauthentik.io/` sub-routes carry no middleware on purpose: the
Authentik outpost needs them to complete a login, and they serve nothing else.

## Deliberate exceptions

- **Karakeep** (`links.pxldi.de`) stays Authentik-only. It is shared with someone
  who has an account but no device on the tailnet.
- **Cantus's API route** (`cantus.pxldi.de` with a Bearer header) stays public so
  a client that cannot follow a login redirect works away from home. Cantus
  validates the token and answers 401 to anything it did not mint. No proxy key
  applies there, so identity headers on those requests are never believed.

## Known issues

- **The apex depends on one AdGuard rewrite.** It is the only name still proxied
  by Cloudflare in public DNS; every subdomain points straight at the house. So
  an apex request that is not rewritten locally arrives wearing Cloudflare's
  address, and `internal-only` refuses it, from the LAN too. That is what made
  the homepage answer 403 to everyone from 2026-09-13 to 09-15: the AdGuard
  rewrite covering `*.pxldi.de` does not match the bare apex. The apex rewrite
  was added on 2026-09-15 and the allowlist restored. If the homepage starts
  answering 403 again, check that rewrite before anything else.
- **`wear.pxldi.de` returns Authentik's 404 page.** The request passes the
  allowlist and reaches forward-auth, and Authentik has no application bound to
  that host. Unrelated to the allowlist, which answers 403 when it rejects.

## Routes

| Namespace | Route | State | Middlewares |
| --- | --- | --- | --- |
| authentik | `auth.pxldi.de` | public | none |
| n8n | `automation.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| n8n | `automation.pxldi.de PathPrefix(`/outpost.goauthentik.io/`)` | public | none |
| grimmory | `books.pxldi.de` | public | none |
| branding | `branding.pxldi.de` | public | none |
| media | `cantus.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth,cantus-proxy-key |
| media | `cantus.pxldi.de PathPrefix(`/api/`) && HeaderRegexp(`Authorization`, `^Beare` | public | none |
| media | `cantus.pxldi.de PathPrefix(`/outpost.goauthentik.io/`)` | public | none |
| nextcloud | `cloud.pxldi.de` | public | nextcloud-headers |
| nextcloud | `cloud.pxldi.de (Path(`/.well-known/carddav`) \|\| Path(`/.well-known/caldav` | public | nextcloud-wellknown-dav |
| nextcloud | `cloud.pxldi.de PathPrefix(`/remote.php/dav`)` | public | nextcloud-headers,nextcloud-dav-no-compress |
| multica | `code.pxldi.de` | public | none |
| multica | `code.pxldi.de (PathPrefix(`/api`) \|\| PathPrefix(`/ws`) \|\| PathPrefix(`` | public | none |
| multica | `code.pxldi.de (PathPrefix(`/auth/callback`) \|\| PathPrefix(`/auth/hg-sso/` | public | none |
| jdownloader | `download.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| excalidraw | `draw.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| sure | `finance.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| sparkyfitness | `fit.pxldi.de` | public | none |
| glance | `glance.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| gotify | `gotify.pxldi.de` | public | none |
| observability | `grafana.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| observability | `grafana.pxldi.de PathPrefix(`/outpost.goauthentik.io/`)` | public | none |
| home-assistant | `home.pxldi.de` | public | none |
| fredy | `immo.pxldi.de` | public | none |
| media | `jellyfin.pxldi.de` | public | none |
| overleaf | `latex.pxldi.de` | public | none |
| karakeep | `links.pxldi.de` | public | none |
| media | `music.pxldi.de` | public | none |
| obsidian-sync | `obsidian.pxldi.de` | public | none |
| paperless | `paperless.pxldi.de` | public | none |
| immich | `photos.pxldi.de` | public | none |
| media | `prowlarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| homepage | `pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `radarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| tandoor | `recipes.pxldi.de` | public | none |
| media | `request.pxldi.de` | public | none |
| media | `sabnzbd.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| searxng | `search.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| slskd | `slskd.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `sonarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| ryot | `track.pxldi.de` | public | none |
| traefik | `traefik.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel-admin.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel.pxldi.de` | public | none |
| adventurelog | `travel.pxldi.de (PathPrefix(`/media`) \|\| PathPrefix(`/static`) \|\| PathPr` | public | add-trailing-slash,adventurelog-headers |
| monitoring | `uptime.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| monitoring | `uptime.pxldi.de PathPrefix(`/outpost.goauthentik.io/`)` | public | none |
| velero | `velero.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| velero | `velero.pxldi.de PathPrefix(`/outpost.goauthentik.io/`)` | public | none |
| wardrowbe | `wear.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| wardrowbe | `wear.pxldi.de PathPrefix(`/api/v1`)` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| wardrowbe | `wear.pxldi.de PathPrefix(`/outpost.goauthentik.io/`)` | public | none |
