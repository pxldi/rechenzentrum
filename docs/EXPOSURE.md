# Exposure inventory

Generated from the live cluster on 2026-09-13, after the internal-only rollout.
Routes do not prove internet reachability; DNS and the router decide that too.

## Since 2026-11-27: Cloudflare Tunnel only

The house lost its own line and router. The cluster now sits behind a router
in repeater mode on a network with no port forwards, so nothing reaches
Traefik's LoadBalancer from the internet. `cloudflare-ddns` is scaled to 0.

Public through the Cloudflare Tunnel (`infrastructure/networking/cloudflared`):
`cloud.pxldi.de` (Nextcloud), `photos.pxldi.de` (Immich), `keep.pxldi.de`
(Anchor), `todo.pxldi.de` (Planka, behind forward-auth), the five claude.ai
connectors (`*-mcp.pxldi.de`), and `auth.pxldi.de` and `branding.pxldi.de` so
authentik logins work from outside. These are the only routes bound to
Traefik's `tunnel` entrypoint. Every other route
marked "public" or "Authentik" below is reachable from the LAN and the tailnet
only, until it is bound to `tunnel` and given a hostname in the tunnel's
dashboard config. Each claude.ai connector has a second IngressRoute on
`tunnel` with the `anthropic-tunnel` allowlist, which reads the client from
`X-Forwarded-For` (`ipStrategy.depth: 1`). That is safe only because of the
Transform Rule below.

On the tunnel, authentik's flood guard is keyed on `Cf-Connecting-Ip`
(`auth-rate-limit-tunnel`), because the remote address is a cloudflared pod.
authentik's reputation policy and Traefik's access log (which CrowdSec reads)
take the leftmost `X-Forwarded-For` entry, and Cloudflare appends to one a
client sent. A zone Transform Rule in the `http_request_late_transform` phase
removes the header on every request, and Cloudflare's proxy re-adds it with
the visitor address alone. It lives in the Cloudflare dashboard, not in this
repository. Verified on 2026-11-27: a request sent with a forged
`X-Forwarded-For` was logged under its real address by authentik and Traefik.

Custom firewall rules in the zone decide who reaches the tunnel at all, in
this order (Cloudflare dashboard, Security, WAF, Custom rules):

1. `OpenTF Action` skips the rest for `auth.pxldi.de` paths containing
   `/api/`, so the OpenTofu workflow's GitHub runner can reach authentik's API.
   It applies to any source address.
2. `claude.ai connectors` skips the rest for Anthropic's range
   (`160.79.104.0/21`) on the five `*-mcp` hosts and on `auth.pxldi.de`
   paths under `/application/o/` (token and discovery).
3. `Not in Country` blocks every source outside AT, DE and CH. A user
   travelling elsewhere is refused at Cloudflare and never reaches the house.

Cloudflare's free plan caps a request body at 100 MB. Immich uploads of
larger files fail through the tunnel and work on the LAN and the tailnet.

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

## Scaled to 0 since 2026-11-27

Radarr, Sonarr and Seerr run at 0 replicas; HolyArrs took over the library,
downloads and requests. Their routes below (`radarr`, `sonarr`, `request`)
still exist with no pod behind them until the apps, routes and authentik apps are
deleted. Prowlarr keeps running because the Sources HolyArrs imported from it
still search through it.

## Deliberate exceptions

- **Snacky** (`snacky.pxldi.de`) stays Authentik-only, so a phone off the
  tailnet can reach it. The MCP port has no route.
- **Planka** (`todo.pxldi.de`) is Authentik-only, through the tunnel, for the
  two people on the game projects, and binds the `survivorlike-viewers` group. Planka keeps its own accounts
  behind the gate, because its free edition has no OIDC since 2.2.0.
- **Forgejo** (`git.pxldi.de`) is LAN/tailnet only, with no forward-auth. Git
  clients and Actions runners cannot follow a login redirect, so Forgejo keeps
  its own login behind `internal-only`. Do not open it to the internet while
  runners can execute workflow code.
- **Karakeep** (`links.pxldi.de`) stays Authentik-only, through Karakeep's own
  OIDC login rather than forward-auth: its password form is off, and the browser
  extension and phone apps send bearer tokens to `/api`, which a forward-auth
  redirect would break.
- **Anchor** (`keep.pxldi.de`) is public through the tunnel, gated by
  Anchor's own OIDC login against authentik, the Karakeep shape: the Android
  app sends bearer tokens to `/api`, which forward-auth would break. Password
  sign-in is off in the API (`DISABLE_INTERNAL_AUTH`), and only
  `anchor-users` completes the flow. It is for a user off the tailnet.
- **Audiobookshelf** (`listen.pxldi.de`) is LAN/tailnet only, with no
  forward-auth: the phone apps send bearer tokens to `/api` and run the OIDC
  flow through the server, which a forward-auth redirect would break. Its own
  OIDC login against authentik is the gate, and only `audiobookshelf-users`
  completes the flow. Audiobookshelf stores its OIDC settings in its database,
  so they are entered once in Settings > Authentication: issuer
  `https://auth.pxldi.de/application/o/audiobookshelf/` (Auto-populate fills
  the endpoints), the client id from `terraform/authentik/oidc-apps.tf`, the
  secret authentik generated for the `audiobookshelf` provider, auto-register
  on, and match existing users by username so the root account links to the
  authentik user of the same name. Mobile redirect URI stays
  `audiobookshelf://oauth`.
- **Schall's API route** (`schall.pxldi.de` with a Bearer header) stays public so
  a client that cannot follow a login redirect works away from home. Schall
  validates the token and answers 401 to anything it did not mint. No proxy key
  applies there, so identity headers on those requests are never believed.

- **The vault MCP server** (`vault-mcp.pxldi.de`, `/mcp` and `/.well-known/`
  only) is public to Anthropic's egress range and the house. claude.ai calls
  it from Anthropic's servers, which cannot follow a login redirect. The
  server answers 401 to anything without an access token Authentik issued
  for its client, so the login still happens, in the browser, once.
- **The recipe, Snacky, calendar and openGym MCP servers**
  (`tandoor-mcp.pxldi.de`, `snacky-mcp.pxldi.de`, `calendar-mcp.pxldi.de` and
  `opengym-mcp.pxldi.de`, `/mcp` and `/.well-known/` only), the same as the
  vault's: Anthropic's range and the house, and a token from each one's own
  Authentik client. Snacky's token check is the gate in front of it.
- **Authentik itself** (`auth.pxldi.de`) and **branding** (`branding.pxldi.de`)
  stay public. The login page is what every other gate redirects to, and it
  loads its logo, wallpaper and fonts from branding; gating either breaks every
  login from outside the house.

## Second pass, 2026-09-18

The 2026-09-13 rollout gated everything that had no login of its own. The
question for what was left is not whether the app has a login but whether
anything off the tailnet talks to it. Three were
clear and are gated now: **Fredy**, **Overleaf** and **Ryot** are browser-only
and single-user. The rest each have a client that cannot follow a login
redirect or a user without a tailnet device, and stay public until that is
decided per app:

| Route | Off-tailnet consumer |
| --- | --- |
| `cloud.pxldi.de` | Nextcloud phone sync, CalDAV/CardDAV, share links |
| `photos.pxldi.de` | Immich phone backup, shared albums |
| `jellyfin.pxldi.de`, `music.pxldi.de`, `request.pxldi.de` | Media clients on TVs and phones |
| `home.pxldi.de` | Home Assistant companion app and external integrations |
| `gotify.pxldi.de` | Phones hold a push socket to it |
| `paperless.pxldi.de` | Phone scanner app |
| `recipes.pxldi.de` | Tandoor, shared |
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
| media | `aurral.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
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
| media | `watch.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `jellyfin.pxldi.de` | public | none |
| karakeep | `links.pxldi.de` | public | none |
| anchor | `keep.pxldi.de` | public (tunnel) | none |
| opengym | `gym.pxldi.de` | public | none |
| wealthfolio | `wealth.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| audiobookshelf | `listen.pxldi.de` | LAN/tailnet + Authentik (OIDC) | internal-only |
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
| snacky | `snacky.pxldi.de` | Authentik | authentik-forward-auth |
| media | `sonarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| forgejo | `git.pxldi.de` | LAN/tailnet | internal-only |
| planka | `todo.pxldi.de` | Authentik | authentik-forward-auth |
| traefik | `traefik.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel-admin.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel.pxldi.de` | public | none |
| adventurelog | `travel.pxldi.de (PathPrefix(`/media`) \|\| PathPrefix(`/static`) \|\| PathPr` | public | add-trailing-slash,adventurelog-headers |
| monitoring | `uptime.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| velero | `velero.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| chatops | `vault-mcp.pxldi.de` (`/mcp`, `/.well-known/` only) | Anthropic range and house | anthropic-and-house |
| chatops | `tandoor-mcp.pxldi.de` (`/mcp`, `/.well-known/` only) | Anthropic range and house | anthropic-and-house |
| chatops | `snacky-mcp.pxldi.de` (`/mcp`, `/.well-known/` only) | Anthropic range and house | anthropic-and-house |
| chatops | `calendar-mcp.pxldi.de` (`/mcp`, `/.well-known/` only) | Anthropic range and house | anthropic-and-house |
| chatops | `opengym-mcp.pxldi.de` (`/mcp`, `/.well-known/` only) | Anthropic range and house | anthropic-and-house |
