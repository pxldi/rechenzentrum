# Exposure inventory

The route table at the end was regenerated from the manifests on 2026-11-27.
Routes do not prove internet reachability; DNS and the router decide that too.

## Since 2026-11-27: Cloudflare Tunnel only

The house lost its own line and router. The cluster now sits behind a router
in repeater mode on a network with no port forwards, so nothing reaches
Traefik's LoadBalancer from the internet. `cloudflare-ddns` was removed on
2026-11-27; the zone holds no A or AAAA record at all, only the tunnel's
proxied CNAMEs and the mail records.

Public through the Cloudflare Tunnel (`infrastructure/networking/cloudflared`):
`cloud.pxldi.de` (Nextcloud), `photos.pxldi.de` (Immich), `keep.pxldi.de`
(Anchor), `todo.pxldi.de` (Planka, behind forward-auth), the five claude.ai
connectors (`*-mcp.pxldi.de`), and `auth.pxldi.de` and `branding.pxldi.de` so
authentik logins work from outside. These are the only routes bound to
Traefik's `tunnel` entrypoint. Every other route is reachable from the LAN
and the tailnet only, until it is bound to `tunnel` and given a hostname in
the tunnel's dashboard config.

Since 2026-11-27 every `websecure` router also carries a source allowlist,
so a port forward to the house would expose nothing even if one came back.
A route bound to both entrypoints is two IngressRoutes, `<name>` on
`websecure` and `<name>-tunnel` on `tunnel`, because an allowlist on the
tunnel router would see a cloudflared pod as the client. Two exceptions are
left for the sessions removing them: Seerr (scaled to 0) and Schall's API
route. Each claude.ai connector has a second IngressRoute on
`tunnel` with the `anthropic-tunnel` allowlist, which reads the client from
`X-Forwarded-For` (`ipStrategy.depth: 1`). That is safe only because of the
Transform Rule below.

Client-sent `X-Forwarded-Host` and `X-Forwarded-Uri` do not change what
forward-auth decides on the tunnel, although `authentik-forward-auth` has
`trustForwardHeader: true` and the entrypoint trusts the pod range. Tested on
2026-11-27 against `todo.pxldi.de` through Cloudflare: with
`X-Forwarded-Host: snacky.pxldi.de` and `X-Forwarded-Uri: /evil`, authentik
still chose Planka's provider and the original path. Only cloudflared reaches
the entrypoint since the Traefik NetworkPolicy.

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

1. `OpenTF Action` skips the rest for `auth.pxldi.de` paths under
   `/api/v3/`, and only for requests carrying the `X-Tofu-Runner-Key` header
   with the key in the `OPENTF_WAF_KEY` repository secret. The authentik
   provider sends it (`terraform/authentik/provider.tf`), so the OpenTofu
   workflow's GitHub runner can reach authentik's API. GitHub's Actions ranges
   are thousands of prefixes, too many for an expression, which is why the
   rule names a key rather than addresses. Until 2026-11-27 it matched any
   path containing `/api/` from any source. Verified that day: a dispatched
   plan on main reached authentik and reported no changes.
2. `claude.ai connectors` skips the rest for Anthropic's range
   (`160.79.104.0/21`) on the five `*-mcp` hosts and on `auth.pxldi.de`
   paths under `/application/o/` (token and discovery).
3. `Not in Country` blocks every source outside AT, DE and CH. A user
   travelling elsewhere is refused at Cloudflare and never reaches the house.

Cloudflare's free plan caps a request body at 100 MB. Immich uploads of
larger files fail through the tunnel and work on the LAN and the tailnet.

The states in the table below:

- **LAN/tailnet + Authentik** — the `internal-only` middleware refuses any source
  address outside the house LAN and the tailnet, and an Authentik login follows.
- **LAN/tailnet** — the `internal-only` middleware alone. The application's own
  login follows.
- **LAN/tailnet/pods** — the `internal-or-cluster` middleware: `internal-only`
  plus the pod range. For routes that pods also call: Gatus checks them through
  Traefik's Service, and apps reach `auth.pxldi.de` or their own name through
  the node whenever CoreDNS gets AdGuard's rewritten answer. A packet from the
  internet keeps its own source address, so the pod range admits nothing from
  outside.
- **tunnel** — the `-tunnel` router: reachable from the internet through
  Cloudflare, behind the zone's firewall rules, protected by the application's
  own login or by forward-auth where the table says so.

Four apps used to carry a `/outpost.goauthentik.io/` sub-route to authentik.
Each named port 9000, which the `authentik-server` Service does not expose (it
maps 80 to 9000), so Traefik rejected them on every reload. Logins worked
anyway: the forward-auth middleware passes the callback to the outpost itself,
as it always did for every app without such a route. They were removed on
2026-09-26.

## Scaled to 0 since 2026-11-27

Radarr, Sonarr and Seerr run at 0 replicas; HolyArrs took over the library,
downloads and requests. Schall is at 0 too; Aurral replaced it and
`schall.pxldi.de` has no pod behind it. Their routes below (`radarr`, `sonarr`, `request`)
still exist with no pod behind them until the apps, routes and authentik apps are
deleted. Prowlarr stays: Aurral searches Usenet through it for SABnzbd, and
the Sources HolyArrs imported from it still search through it.

## Deliberate exceptions

- **Snacky** (`snacky.pxldi.de`) is LAN/tailnet + Authentik. It is not on the
  tunnel, so a phone off the tailnet cannot reach it; binding it to `tunnel`
  would need a `snacky-tunnel` route and a hostname in the tunnel config. The
  MCP port has no route.
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
- **RomM** (`games.pxldi.de`) is LAN/tailnet only, with no forward-auth, the
  same shape: handheld clients send API tokens. Its password login and setup
  wizard are off (`DISABLE_USERPASS_LOGIN`, `DISABLE_SETUP_WIZARD`), so its
  OIDC login against authentik is the only way in. `romm-admins` log in as
  admins and `romm-users` as users; anyone else is refused by authentik's
  binding and again by RomM.
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
  stay public on the tunnel. The login page is what every other gate redirects to, and it
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

- **Names without a tunnel hostname have no public record.** Inside the house
  they resolve only through AdGuard's `*.pxldi.de` rewrite, and CoreDNS asks
  AdGuard or Quad9 at random, so a pod resolving one of them fails whenever
  Quad9 answers. The apex has no record either since the homepage was
  removed.

## Routes

| Namespace | Route | State | Middlewares |
| --- | --- | --- | --- |
| media | `aurral.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| authentik | `auth.pxldi.de` | LAN/tailnet/pods | internal-or-cluster,auth-rate-limit |
| authentik | `auth.pxldi.de` | tunnel | auth-rate-limit-tunnel |
| grimmory | `books.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| branding | `branding.pxldi.de` | LAN/tailnet | internal-only |
| branding | `branding.pxldi.de` | tunnel | none |
| chatops | `calendar-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | Anthropic range and house | anthropic-and-house |
| chatops | `calendar-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | tunnel, Anthropic range only | anthropic-tunnel |
| nextcloud | `cloud.pxldi.de` `(Path(`/.well-known/carddav`) \|\| Path(`/.well-known/caldav`)` | LAN/tailnet/pods | internal-or-cluster,nextcloud-wellknown-dav |
| nextcloud | `cloud.pxldi.de` `PathPrefix(`/remote.php/dav`)` | LAN/tailnet/pods | internal-or-cluster,nextcloud-headers,nextcloud-dav-no-compress |
| nextcloud | `cloud.pxldi.de` | LAN/tailnet/pods | internal-or-cluster,nextcloud-headers |
| nextcloud | `cloud.pxldi.de` `(Path(`/.well-known/carddav`) \|\| Path(`/.well-known/caldav`)` | tunnel | nextcloud-wellknown-dav |
| nextcloud | `cloud.pxldi.de` `PathPrefix(`/remote.php/dav`)` | tunnel | nextcloud-headers,nextcloud-dav-no-compress |
| nextcloud | `cloud.pxldi.de` | tunnel | nextcloud-headers |
| forgejo | `git.pxldi.de` | LAN/tailnet | internal-only |
| romm | `games.pxldi.de` | LAN/tailnet | internal-only |
| gotify | `gotify.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| observability | `grafana.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| opengym | `gym.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| home-assistant | `home.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| fredy | `immo.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `jellyfin.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| anchor | `keep.pxldi.de` | LAN/tailnet | internal-only |
| anchor | `keep.pxldi.de` | tunnel | none |
| karakeep | `links.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| audiobookshelf | `listen.pxldi.de` | LAN/tailnet | internal-only |
| media | `music.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| obsidian-sync | `obsidian.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| chatops | `opengym-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | Anthropic range and house | anthropic-and-house |
| chatops | `opengym-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | tunnel, Anthropic range only | anthropic-tunnel |
| paperless | `paperless.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| immich | `photos.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| immich | `photos.pxldi.de` | tunnel | none |
| media | `prowlarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `radarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| tandoor | `recipes.pxldi.de` | LAN/tailnet/pods | internal-or-cluster |
| media | `request.pxldi.de` | LAN/tailnet (no allowlist) | none |
| media | `sabnzbd.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `schall.pxldi.de` `PathPrefix(`/api/`) && HeaderRegexp(`Authorization`, `^Beare` | LAN/tailnet (no allowlist) | none |
| media | `schall.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth,cantus-proxy-key |
| slskd | `slskd.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| chatops | `snacky-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | Anthropic range and house | anthropic-and-house |
| chatops | `snacky-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | tunnel, Anthropic range only | anthropic-tunnel |
| snacky | `snacky.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `sonarr.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| chatops | `tandoor-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | Anthropic range and house | anthropic-and-house |
| chatops | `tandoor-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | tunnel, Anthropic range only | anthropic-tunnel |
| planka | `todo.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| planka | `todo.pxldi.de` | tunnel + Authentik | authentik-forward-auth |
| traefik | `traefik.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel-admin.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel.pxldi.de` `(PathPrefix(`/media`) \|\| PathPrefix(`/static`) \|\| PathPrefix` | LAN/tailnet | internal-only,add-trailing-slash,adventurelog-headers |
| adventurelog | `travel.pxldi.de` | LAN/tailnet | internal-only |
| monitoring | `uptime.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| chatops | `vault-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | Anthropic range and house | anthropic-and-house |
| chatops | `vault-mcp.pxldi.de` `(PathPrefix(`/mcp`) \|\| PathPrefix(`/.well-known/`))` | tunnel, Anthropic range only | anthropic-tunnel |
| velero | `velero.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| media | `watch.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| wealthfolio | `wealth.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
