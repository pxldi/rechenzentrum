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

- **Snacky** (`snacky.pxldi.de`) stays Authentik-only. Its owner opens it on
  the phone on mobile data, without the tailnet. The MCP port has no route.
- **Karakeep** (`links.pxldi.de`) stays Authentik-only, through Karakeep's own
  OIDC login rather than forward-auth: its password form is off, and the browser
  extension and phone apps send bearer tokens to `/api`, which a forward-auth
  redirect would break. It is shared with someone who has an account but no
  device on the tailnet.
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

## Audit of the public routes, 2026-10-02

Read from the repository at `3a1e313`, not from the live cluster, so it shows
what Flux applies, not what DNS or the router expose. Nothing here changes a
route: every "Proposed" entry waits for the owner's decision, because friends
and family use some of these apps.

What every public route already has: TLS at Traefik, and the CrowdSec bouncer
on the `websecure` entrypoint (since #273). CrowdSec runs only the
`crowdsecurity/traefik` collection, so it bans scanners and known CVE probes
seen in Traefik's access log. It does not read any app's own log, so password
guessing against an app's login is limited only by what that app does itself.
Authentik is the one route with a Traefik rate limit (50/s, burst 100).

"Users" is what the repository and earlier decisions say; anything marked
*ask* is unknown and needs the owner's answer.

| Route | Users | Non-browser clients | Protection today | Proposed |
| --- | --- | --- | --- | --- |
| `auth.pxldi.de` | everyone who logs in | none | Authentik login, MFA per user, rate limit | Leave |
| `branding.pxldi.de` | login page assets | none | static files | Leave |
| `cloud.pxldi.de` | *ask* | desktop and phone sync, CalDAV/CardDAV, public share links | Nextcloud login, its built-in brute-force throttle | Leave public. Enforce TOTP for every account and app passwords for clients; optionally Authentik OIDC (`user_oidc`) for the browser login |
| `photos.pxldi.de` | *ask* | Immich phone backup, shared-album links | Immich login | Leave public. Switch Immich to Authentik OAuth (the phone app supports it) and turn its password login off once every user has moved |
| `jellyfin.pxldi.de` | *ask*, possibly other people | TV and phone players, Quick Connect | Jellyfin login | If only the household: tailnet-only. If others watch: leave public, set Jellyfin's failed-login lockout, add a rate limit on `/Users/AuthenticateByName` |
| `music.pxldi.de` | *ask* | Subsonic clients on `/rest`, share links on `/share` | Navidrome login, its built-in login rate limit | Forward-auth on the web UI, with `/rest` and `/share` bypassed, if every user has an Authentik account; otherwise leave |
| `request.pxldi.de` | *ask* (Jellyfin users) | none, browser only | Seerr login with Jellyfin accounts | Forward-auth if every requester has an Authentik account; otherwise follows Jellyfin's decision |
| `home.pxldi.de` | household | Home Assistant companion app, webhooks | HA login | Leave public. Turn on `ip_ban_enabled` and `login_attempts_threshold` in the `http:` block (both off today) and require MFA for every HA user |
| `gotify.pxldi.de` | owner's phones | phones hold a push socket on `/stream`, senders post to `/message` with app tokens | Gotify login (basic auth), token per client | Leave public, add a Traefik rate limit; gating only the web UI is not worth the path list |
| `paperless.pxldi.de` | *ask* | phone scanner app with a token on `/api/` | Paperless login | Schall pattern: forward-auth on the host, plus a public route for `/api/` that requires an `Authorization` header |
| `recipes.pxldi.de` | household | none, browser and PWA | Tandoor login | Forward-auth (or Tandoor OIDC) if the household has Authentik accounts; otherwise leave |
| `books.pxldi.de` | *ask* | e-reader on OPDS and KOReader sync | Grimmory login | Forward-auth on the web UI with the OPDS and KOReader paths bypassed; the exact paths need checking against Grimmory 3.5 before any change |
| `obsidian.pxldi.de` | owner | Obsidian LiveSync on desktop and phone | CouchDB basic auth, admin-only `_security` per database | Leave sync public. Put CouchDB's admin UI (`/_utils`) and server endpoints (`/_config`, `/_node`) behind `internal-only`, add a rate limit |
| `travel.pxldi.de` | *ask* | none known, browser only | AdventureLog login | Forward-auth if only Authentik users use it; otherwise leave. Separately, its images run the unpinned `beta` tag |
| `links.pxldi.de` | owner and one other person | browser extension, phone apps with bearer tokens | Karakeep OIDC only, password form off | Leave |
| `gym.pxldi.de` | owner | phone at the gym | passkey-only login, invite-only signup, guest mode off | Leave |
| `schall.pxldi.de` `/api/` + Bearer | owner's clients | yes | Schall's own token check | Leave |
| `vault-mcp.pxldi.de` | claude.ai | yes | Anthropic range allowlist and an Authentik-issued token | Leave |

Two non-HTTP LoadBalancers expect a router forward: Palworld (8211/udp, for
friends) and Minecraft (25565/tcp). Minecraft is scaled to zero, so its router
forward, if still set, and its LoadBalancer can go unless the world comes back.

### Questions for the owner

1. Who outside the household uses Jellyfin, Navidrome, Seerr, Nextcloud,
   Immich, Paperless, Grimmory and AdventureLog?
2. Does each of those people have an Authentik account, or would they need one?

Every *ask* row above is decided by those two answers. The changes that do not
depend on them (Home Assistant's ban settings, the CouchDB admin paths, rate
limits on Gotify and Jellyfin's login) are safe to make first.

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
| wealthfolio | `wealth.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
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
| traefik | `traefik.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel-admin.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| adventurelog | `travel.pxldi.de` | public | none |
| adventurelog | `travel.pxldi.de (PathPrefix(`/media`) \|\| PathPrefix(`/static`) \|\| PathPr` | public | add-trailing-slash,adventurelog-headers |
| monitoring | `uptime.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| velero | `velero.pxldi.de` | LAN/tailnet + Authentik | internal-only,authentik-forward-auth |
| chatops | `vault-mcp.pxldi.de` (`/mcp`, `/.well-known/` only) | Anthropic range and house | anthropic-and-house |
