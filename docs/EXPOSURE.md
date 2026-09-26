# Exposure inventory

Generated from the live cluster on 2026-09-13, after the internal-only rollout.
Routes do not prove internet reachability; DNS and the router decide that too.

Three states:

- **LAN/tailnet + Authentik** — the `internal-only` middleware refuses any source
  address outside the house LAN and the tailnet, and an Authentik login follows.
  Unreachable from the internet.
- **LAN/tailnet** — the `internal-only` middleware alone. The application's own
  login follows; used where that login is already Authentik (OIDC) and a second
  forward-auth prompt would only add a redirect.
- **Authentik** — reachable from the internet, gated by an Authentik login.
- **public** — reachable from the internet, protected only by whatever the
  application itself enforces.

Four apps used to carry a `/outpost.goauthentik.io/` sub-route to authentik.
Each named port 9000, which the `authentik-server` Service does not expose (it
maps 80 to 9000), so Traefik rejected them on every reload. Logins worked
anyway: the forward-auth middleware passes the callback to the outpost itself,
as it always did for every app without such a route. They were removed on
2026-09-26.

## Deliberate exceptions

- **Karakeep** (`links.pxldi.de`) stays Authentik-only. It is shared with someone
  who has an account but no device on the tailnet.
- **Schall's API route** (`schall.pxldi.de` with a Bearer header) stays public so
  a client that cannot follow a login redirect works away from home. Schall
  validates the token and answers 401 to anything it did not mint. No proxy key
  applies there, so identity headers on those requests are never believed.

- **The vault MCP server** (`vault-mcp.pxldi.de`, `/mcp` and `/.well-known/`
  only) is public to Anthropic's egress range and the house. claude.ai calls
  it from Anthropic's servers, which cannot follow a login redirect. The
  server answers 401 to anything without an access token Authentik issued
  for its client, so the login still happens, in the browser, once. See
  `docs/CHATOPS.md`.
- **Authentik itself** (`auth.pxldi.de`) and **branding** (`branding.pxldi.de`)
  stay public. The login page is what every other gate redirects to, and it
  loads its logo, wallpaper and fonts from branding; gating either breaks every
  login from outside the house.

## Second pass, 2026-09-18

The 2026-09-13 rollout gated everything that had no login of its own. The
question for what was left is not whether the app has a login but whether
anything off the tailnet, or anyone but the operator, talks to it. Three were
clear and are gated now: **Fredy**, **Overleaf** and **Ryot** are browser-only
and single-user. The rest each have a client that cannot follow a login
redirect or a person without a tailnet device, and stay public until that is
decided per app:

| Route | Off-tailnet consumer |
| --- | --- |
| `cloud.pxldi.de` | Nextcloud phone sync, CalDAV/CardDAV, share links |
| `photos.pxldi.de` | Immich phone backup, shared albums |
| `jellyfin.pxldi.de`, `music.pxldi.de`, `request.pxldi.de` | Media clients on TVs and phones, possibly other people's |
| `home.pxldi.de` | Home Assistant companion app and external integrations |
| `gotify.pxldi.de` | Phones hold a push socket to it |
| `paperless.pxldi.de` | Phone scanner app |
| `recipes.pxldi.de` | Tandoor, shared with the household |
| `books.pxldi.de` | An e-reader cannot join a tailnet |
| `obsidian.pxldi.de`, `travel.pxldi.de` | Phone apps that sync |
| `links.pxldi.de` | Decided above |

The phone on the tailnet is not always connected to it, so "gate it, the phone
is on Tailscale" is not an answer on its own.

## Known issues

- **A chart-generated Ingress shadows the IngressRoute.** Overleaf and n8n are
  app-template charts, and each chart also rendered a plain `Ingress` for the
  same host with no middleware. Traefik gives an `Ingress` router a priority
  equal to its rule length, and the IngressRoutes here are pinned at 10, so the
  bare router won every request and neither `internal-only` nor forward-auth
  ever ran: `automation.pxldi.de` answered 200 to an anonymous request and
  `latex.pxldi.de` went straight to Overleaf's own login. Both chart ingresses
  were switched off on 2026-09-18. This inventory lists IngressRoutes; check
  `kubectl get ingress -A` too, because the table cannot see a shadow.

- **The apex depends on one AdGuard rewrite.** It is the only name still proxied
  by Cloudflare in public DNS; every subdomain points straight at the house. So
  an apex request that is not rewritten locally arrives wearing Cloudflare's
  address, and `internal-only` refuses it, from the LAN too. That is what made
  the homepage answer 403 to everyone from 2026-09-13 to 09-15: the AdGuard
  rewrite covering `*.pxldi.de` does not match the bare apex. The apex rewrite
  was added on 2026-09-15 and the allowlist restored. If the homepage starts
  answering 403 again, check that rewrite before anything else.

## Routes

| Namespace | Route | State | Middlewares |
| --- | --- | --- | --- |
| authentik | `auth.pxldi.de` | public | none |
| grimmory | `books.pxldi.de` | public | none |
| branding | `branding.pxldi.de` | public | none |
| media | `schall.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth,cantus-proxy-key |
| media | `schall.pxldi.de PathPrefix(`/api/`) && HeaderRegexp(`Authorization`, `^Beare` | public | none |
| nextcloud | `cloud.pxldi.de` | public | nextcloud-headers |
| nextcloud | `cloud.pxldi.de (Path(`/.well-known/carddav`) \|\| Path(`/.well-known/caldav` | public | nextcloud-wellknown-dav |
| nextcloud | `cloud.pxldi.de PathPrefix(`/remote.php/dav`)` | public | nextcloud-headers,nextcloud-dav-no-compress |
| jdownloader | `download.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| excalidraw | `draw.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| gotify | `gotify.pxldi.de` | public | none |
| observability | `grafana.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| home-assistant | `home.pxldi.de` | public | none |
| fredy | `immo.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `jellyfin.pxldi.de` | public | none |
| karakeep | `links.pxldi.de` | public | none |
| opengym | `gym.pxldi.de` | public | none |
| firefly | `finance.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| firefly | `finance-import.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| firefly | `money.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `music.pxldi.de` | public | none |
| obsidian-sync | `obsidian.pxldi.de` | public | none |
| paperless | `paperless.pxldi.de` | public | none |
| immich | `photos.pxldi.de` | public | none |
| media | `prowlarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `radarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| tandoor | `recipes.pxldi.de` | public | none |
| media | `request.pxldi.de` | public | none |
| media | `sabnzbd.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| searxng | `search.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| slskd | `slskd.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `sonarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| traefik | `traefik.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel-admin.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel.pxldi.de` | public | none |
| adventurelog | `travel.pxldi.de (PathPrefix(`/media`) \|\| PathPrefix(`/static`) \|\| PathPr` | public | add-trailing-slash,adventurelog-headers |
| monitoring | `uptime.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| velero | `velero.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
