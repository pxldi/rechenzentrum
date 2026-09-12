# Exposure inventory

Generated from the GitOps baseline. This records routes, not proof of actual
internet reachability: DNS, router forwarding and VPN routing must be checked.
An app login alone does not make an administrative service suitable for public
access. Mixed-route apps may deliberately bypass forward auth for API clients.

No existing route has been removed or put behind VPN in this migration.
The operator must identify services needing internet access before that change.
Grafana, Traefik dashboard, Velero UI and developer interfaces are initial VPN
candidates. Internal database/API/MCP services should stay class D.

| Namespace | Route | Match | Middleware | Observed class |
| --- | --- | --- | --- | --- |
| adventurelog | adventurelog | Host(`travel.pxldi.de`) | none | A / app auth |
| adventurelog | adventurelog | Host(`travel.pxldi.de`) && (PathPrefix(`/media`) \|\| PathPrefix(`/static`) \|\| PathPrefix(`/accounts`) \|\| PathPrefix(`/csrf`) \|\| PathPrefix(`/admin`)) | add-trailing-slash, adventurelog-headers | A / app auth |
| adventurelog | adventurelog-django-admin | Host(`travel-admin.pxldi.de`) | authentik-forward-auth | B candidate |
| authentik | authentik | Host(`auth.pxldi.de`) | none | A / app auth |
| branding | branding | Host(`branding.pxldi.de`) | none | A / app auth |
| excalidraw | excalidraw | Host(`draw.pxldi.de`) | authentik-forward-auth | B candidate |
| fredy | fredy | Host(`immo.pxldi.de`) | none | A / app auth |
| glance | glance | Host(`glance.pxldi.de`) | authentik-forward-auth | B candidate |
| gotify | gotify | Host(`gotify.pxldi.de`) | none | A / app auth |
| grimmory | grimmory | Host(`books.pxldi.de`) | none | A / app auth |
| home-assistant | home-assistant | Host(`home.pxldi.de`) | none | A / app auth |
| homepage | homepage | Host(`pxldi.de`) | authentik-forward-auth | B candidate |
| immich | immich | Host(`photos.pxldi.de`) | none | A / app auth |
| jdownloader | jdownloader | Host(`download.pxldi.de`) | authentik-forward-auth | B candidate |
| karakeep | karakeep | Host(`links.pxldi.de`) | none | A / app auth |
| media | cantus | Host(`cantus.pxldi.de`) | authentik-forward-auth, cantus-proxy-key | B candidate |
| media | cantus | Host(`cantus.pxldi.de`) && PathPrefix(`/api/`) && HeaderRegexp(`Authorization`, `^Bearer `) | none | A / app auth |
| media | cantus | Host(`cantus.pxldi.de`) && PathPrefix(`/outpost.goauthentik.io/`) | none | A / app auth |
| media | jellyfin | Host(`jellyfin.pxldi.de`) | none | A / app auth |
| media | navidrome | Host(`music.pxldi.de`) | none | A / app auth |
| media | prowlarr | Host(`prowlarr.pxldi.de`) | authentik-forward-auth | B candidate |
| media | radarr | Host(`radarr.pxldi.de`) | authentik-forward-auth | B candidate |
| media | sabnzbd | Host(`sabnzbd.pxldi.de`) | authentik-forward-auth | B candidate |
| media | seerr | Host(`request.pxldi.de`) | none | A / app auth |
| media | slskd | Host(`slskd.pxldi.de`) | authentik-forward-auth | B candidate |
| media | sonarr | Host(`sonarr.pxldi.de`) | authentik-forward-auth | B candidate |
| monitoring | uptime-kuma | Host(`uptime.pxldi.de`) | authentik-forward-auth | B candidate |
| monitoring | uptime-kuma | Host(`uptime.pxldi.de`) && PathPrefix(`/outpost.goauthentik.io/`) | none | A / app auth |
| multica | multica | Host(`code.pxldi.de`) | none | A / app auth |
| multica | multica | Host(`code.pxldi.de`) && (PathPrefix(`/api`) \|\| PathPrefix(`/ws`) \|\| PathPrefix(`/uploads`) \|\| PathPrefix(`/auth`)) | none | A / app auth |
| multica | multica | Host(`code.pxldi.de`) && (PathPrefix(`/auth/callback`) \|\| PathPrefix(`/auth/hg-sso/callback`)) | none | A / app auth |
| n8n | n8n | Host(`automation.pxldi.de`) | authentik-forward-auth | B candidate |
| n8n | n8n | Host(`automation.pxldi.de`) && PathPrefix(`/outpost.goauthentik.io/`) | none | A / app auth |
| nextcloud | nextcloud | Host(`cloud.pxldi.de`) | nextcloud-headers | A / app auth |
| nextcloud | nextcloud | Host(`cloud.pxldi.de`) && (Path(`/.well-known/carddav`) \|\| Path(`/.well-known/caldav`)) | nextcloud-wellknown-dav | A / app auth |
| nextcloud | nextcloud | Host(`cloud.pxldi.de`) && PathPrefix(`/remote.php/dav`) | nextcloud-headers, nextcloud-dav-no-compress | A / app auth |
| observability | grafana | Host(`grafana.pxldi.de`) | authentik-forward-auth | B candidate |
| observability | grafana | Host(`grafana.pxldi.de`) && PathPrefix(`/outpost.goauthentik.io/`) | none | A / app auth |
| obsidian-sync | obsidian-sync | Host(`obsidian.pxldi.de`) | none | A / app auth |
| overleaf | overleaf | Host(`latex.pxldi.de`) | none | A / app auth |
| paperless | paperless | Host(`paperless.pxldi.de`) | none | A / app auth |
| ryot | ryot | Host(`track.pxldi.de`) | none | A / app auth |
| searxng | searxng | Host(`search.pxldi.de`) | authentik-forward-auth | B candidate |
| sparkyfitness | sparkyfitness | Host(`fit.pxldi.de`) | none | A / app auth |
| sure | sure | Host(`finance.pxldi.de`) | authentik-forward-auth | B candidate |
| tandoor | tandoor | Host(`recipes.pxldi.de`) | none | A / app auth |
| traefik | dashboard | Host(`traefik.pxldi.de`) | authentik-forward-auth | B candidate |
| velero | velero-ui | Host(`velero.pxldi.de`) | authentik-forward-auth | B candidate |
| velero | velero-ui | Host(`velero.pxldi.de`) && PathPrefix(`/outpost.goauthentik.io/`) | none | A / app auth |
| wardrowbe | wardrowbe | Host(`wear.pxldi.de`) | authentik-forward-auth | B candidate |
| wardrowbe | wardrowbe | Host(`wear.pxldi.de`) && PathPrefix(`/api/v1`) | authentik-forward-auth | B candidate |
| wardrowbe | wardrowbe | Host(`wear.pxldi.de`) && PathPrefix(`/outpost.goauthentik.io/`) | none | A / app auth |
