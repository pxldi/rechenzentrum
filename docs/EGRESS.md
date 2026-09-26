# Egress isolation

Ingress isolation is everywhere: 34 app kustomizations pull in
`default-deny-ingress` and name who may reach them. Egress is the other half and
is barely started. This file records what has been locked, what each namespace
would need, and how to test a candidate before locking it.

## It is enforced

k3s runs its embedded kube-router NetworkPolicy controller; `nix/modules/k3s.nix`
carries no `--disable-network-policy`. Measured 2026-09-15 from two pods:

| Pod | Policy | `curl http://1.1.1.1` |
| --- | --- | --- |
| `obsidian-sync-0` | ingress only | connects |
| `excalidraw` | `default-deny-egress` + `allow-dns` | rc 7, connection refused |

DNS still resolves under the deny. From the excalidraw pod, a bogus name returns
curl rc 6 (could not resolve) and a real cluster name returns rc 7 (resolved,
then blocked), which separates a working resolver from a blocked one. Run both,
not just the first: a policy that breaks DNS looks identical to one that works
if you only ever test a name that does not exist.

## Locked

Every application namespace except the two at the end of this section.

| Namespace | Beyond DNS | Why |
| --- | --- | --- |
| `chatops` | per pod: the agent gets internet on 443 and its two MCP pods; homelab-mcp gets the API server; tandoor-mcp gets `tandoor` | Three pods with three jobs, see [CHATOPS.md](CHATOPS.md) |
| `claudebox` | internet, API server, `obsidian-sync` | Clones repositories and drives this cluster; it carries a ServiceAccount token and RBAC. Its bridge sidecar mirrors the vault from CouchDB |
| `crowdsec` | per pod: the agent gets the LAPI, the API server on 6443 and internet on 443; the LAPI gets internet on 443 | The agent streams Traefik's log through `pods/log`; both download hub content from the CrowdSec CDN at start. The Central API is off |
| `excalidraw` | nothing | The pilot |
| `fredy` | own namespace, internet | Scrapes property listings |
| `gotify` | nothing | Clients connect inbound and hold the socket |
| `grimmory` | own namespace, internet | MariaDB here; book metadata outside |
| `immich` | own namespace, internet, API server | Server, ML and valkey talk here; geocoding data outside; CNPG |
| `jdownloader` | internet | The point of it |
| `karakeep` | own namespace, internet, Traefik, `ollama` | Meilisearch here, crawls pages, OIDC by public name, tags with a local model |
| `opengym` | internet | The init container clones the exercise media from GitHub; the API sends Web Push |
| `wealthfolio` | internet | Market quotes and exchange rates; the backup job installs sqlite3 |
| `firefly` | own namespace, internet, API server | Postgres here (CNPG), exchange rates outside |
| `media` | own namespace, internet, Traefik, API server, `slskd` | Nine workloads; indexers and metadata; the cantus CNPG cluster |
| `minecraft` | internet | Mojang authentication |
| `monitoring` | internet, cluster, Traefik | Gatus checks public apps on their public names and house-only apps on their Services |
| `nextcloud` | own namespace, internet, Traefik | Postgres and Redis here; app updates; its own public name |
| `obsidian-sync` | nothing | CouchDB, single node, clients connect inbound |
| `ollama` | internet | Pulls models on demand |
| `palworld` | internet | Server list and updates |
| `paperless` | own namespace, internet, Traefik | Postgres, Redis, Gotenberg and Tika here |
| `searxng` | own namespace, internet | Querying upstream engines is the job |
| `slskd` | own namespace, internet | gluetun's tunnel and Soulseek peers |
| `tandoor` | own namespace, internet, API server | Postgres here; recipe import; CNPG |
| `whisper-cpp` | nothing | Transcription happens in the pod; the model is already on the PVC |

### Two namespaces deliberately left alone

**`home-assistant`.** Its pods run with `hostNetwork: true`, and NetworkPolicy
does not apply to a host-network pod, so every component here would be inert.
Its own `networkpolicy.yaml` already says so. It also talks to Zigbee, Thread and
Matter devices all over the LAN, which is exactly what `allow-internet-egress`
excludes, so the rule would be wrong for it even if it did apply.

**`actions-runner`.** It already carries `runners-egress-internet-only`, which is
`allow-internet-egress` plus DNS under another name, and it is the one app here
whose kustomization has no `namespace:`, because it spans `arc-systems` and
`arc-runners`. Nothing to add.

## The components

| Component | What it permits |
| --- | --- |
| `default-deny-egress` | Nothing. `podSelector: {}`, so it covers every pod in the namespace |
| `allow-dns` | CoreDNS, UDP and TCP 53 |
| `allow-intra-namespace-egress` | Any pod in the same namespace. The egress twin of the ingress-only `allow-intra-namespace` |
| `allow-internet-egress` | `0.0.0.0/0` except the pod and service networks, every RFC1918 range, the tailnet and link-local |
| `allow-egress-to-ingress` | The Traefik pod on 8443. For an app that calls another service here by its public hostname |
| `allow-egress-to-apiserver` | The node on 6443, for CNPG instance pods only. The one component here that does not use an empty pod selector |
| `allow-egress-to-cluster` | Every pod in every namespace. Only for the namespaces that legitimately talk to all of them |

`allow-internet-egress` is a compromise worth being explicit about. NetworkPolicy
has no notion of a hostname, so "only this one geocoder" cannot be written here.
What the rule does buy is that a compromised pod cannot reach another namespace's
database, the node's kubelet or API server, the router, or anything else on the
LAN or the tailnet. The application's own internet access is unchanged, which is
the part that was never the threat.

## Who calls whom

Egress isolation only breaks things when a namespace initiates a call that the
policies do not name. This is every cross-namespace call in the repository,
swept from the manifests rather than remembered, so a namespace can be checked
against it before it is locked.

| Caller | Reaches | How |
| --- | --- | --- |
| `monitoring` | 10 Services in 6 namespaces | Gatus checks on house-only apps |
| `observability` | `gotify` | alert delivery |
| `karakeep` | `ollama` | `ollama.ollama.svc.cluster.local` |
| `media` (Schall) | `slskd` | an ExternalName alias onto `slskd.slskd.svc.cluster.local` |

Two things follow. A caller needs a `namespaceSelector` rule per target before it
is locked; `allow-internet-egress` does not cover a cluster path, since the
service network is excluded. And `glance` is the exception in the table: it goes
out through Traefik like any browser would, so it needs
`allow-egress-to-ingress` and the internet rule rather than eight
`namespaceSelector` rules. Measured 2026-09-15 in the glance pod,
`jellyfin.pxldi.de` resolved to the public address, which is the same coin flip
described below and the same reason it needs both.

None of this touches the seven namespaces locked so far: none of them appears in
the caller column. Being in the *target* column is harmless, because that is
someone else's ingress and these components only restrict egress.

## A namespace with a CNPG cluster needs one more thing

The instance pod's manager keeps a connection to the Kubernetes API open for its
whole life: it watches its own Cluster resource, publishes status and takes part
in failover. Measured in the tandoor instance pod on 2026-09-15, that was the
*only* outbound socket it held; everything else in `/proc/net/tcp` was the
application connecting in to 5432.

Nothing in the standard set covers it. `allow-internet-egress` excludes the
service network, and no selector can match the API server, because it runs in
the host's network namespace and has no pod. Hence
`allow-egress-to-apiserver`, and here an `ipBlock` is the right tool rather
than the wrong one: a request to the API service address is rewritten to the
node on 6443, so that is what the rule sees whichever address the client used.

Backups are covered by the internet rule. The barman-cloud plugin runs as a
native sidecar *inside* the instance pod, not as a separate deployment, so WAL
and base backups leave from there straight to B2.

This is the one component whose `podSelector` is not empty. It selects pods
carrying `cnpg.io/cluster`, which CNPG stamps on every instance pod, so the
application sharing the namespace does not get the API server too. An empty
selector shipped first and did exactly that, caught by probing the app pod after
the policies landed rather than only the database. Nothing but a database should
reach the API server here, which is the same reasoning behind
`automountServiceAccountToken: false` on every default ServiceAccount.

## When a chart already did it

`sparkyfitness` (removed 2026-09-25) was the case to copy before reaching for the namespace-wide
components. Its chart ships a NetworkPolicy per component: the frontend may
reach the server on 3010 and nothing else, the server may reach postgresql on
5432 and nothing else, both may do DNS, and `networkpolicy.yaml` in the app
directory adds public 443 for the server alone. That is tighter than
`allow-intra-namespace-egress`, which would let the frontend talk straight to
the database.

So the namespace gets `default-deny-egress` and `allow-dns` and nothing else.
Policies are additive, so the chart's allows survive and the one real gap
closes: the database carried an ingress-only policy, which left its egress
unrestricted.

Check for this before locking any namespace whose app comes from a chart. Adding
the standard set on top of a per-component model makes it weaker, not stronger.

## Before locking a namespace

1. **Read the pod's own connections, while it is busy.** `kubectl -n <ns> exec <pod> -- sh -c 'cat
   /proc/net/tcp /proc/net/tcp6'` and keep the rows in state `01`
   (ESTABLISHED). Column 2 is local, column 3 is remote; a remote with an
   ephemeral port is an inbound connection and does not need an egress rule.
   An idle app tells you nothing: adventurelog's Django backend held no socket
   at all between requests, because it opens a database connection per request
   and closes it again. Plenty of images also carry neither `curl` nor a shell,
   so this is a hint, never the whole answer.
2. **Read its configuration for destinations it reaches only sometimes.** A
   database URL, an SMTP host, an OIDC issuer, an update check, a metadata
   provider. Those do not show up in a snapshot of sockets.
3. **Add the policies and the allowances in the same PR.** `default-deny-egress`
   uses `podSelector: {}`, so it applies to every pod in the namespace at once.
4. **Verify after it lands.** Pod Ready with no new restart, no new error lines
   in `kubectl logs --since=5m`, a real request through Traefik returning what it
   returned before, and the DNS pair above.

## Four things that make this harder than it looks

- **`allow-intra-namespace` is `policyTypes: [Ingress]` only.** It lets pods in a
  namespace accept each other's traffic; it does not let them *initiate* to each
  other. Any namespace with an app and its own database needs an egress twin
  before `default-deny-egress` goes on, or the app loses its database.
- **A NetworkPolicy does reach Helm-rendered pods.** The caveat in
  `components/README.md` is about patches: a component cannot patch a pod
  template that helm-controller renders later. A NetworkPolicy is not a patch,
  it is a namespaced object with a pod selector, so it applies to whatever ends
  up in the namespace. That makes HelmRelease namespaces lockable and also means
  the blast radius is the whole namespace.
- **A pod calling a `pxldi.de` name does not take a cluster path, and does not
  get a stable answer.** CoreDNS forwards to two upstreams: AdGuard, which
  rewrites these names to the node, and Quad9, which answers with the public
  record. Measured in the ryot pod on 2026-09-15: ten lookups in a row returned
  the public address, and a few minutes later the same name returned the node's.
  Both reach the same Traefik, one directly and one back out through the router,
  and either can be the cached answer when the application looks. No
  `allow-internet-egress` covers the public address, which leaves as a public
  address and is only turned around at the router. `allow-egress-to-ingress`
  covers the other answer, and has to name the Traefik pod rather than the node,
  for the DNAT reason below. An app doing this needs both, or it fails
  intermittently. Apps sitting behind
  `authentik-forward-auth` are not affected, because Traefik does the
  authentication and the app never talks to Authentik itself.
- **An egress policy matches the destination after DNAT.** A packet a pod sends
  to a Service address, or to the node on 443, has already been rewritten to the
  receiving pod and its *container* port by the time kube-router evaluates it.
  So a rule naming a Service address, a node address, or the port the Service
  publishes matches nothing. Measured on 2026-09-15: a pod carrying
  `ipBlock: <node>/32` on port 443 still could not reach the node, and could not
  reach Traefik's ClusterIP or the Traefik pod on 443 either, while the same pod
  reached the public address fine, because that one leaves as a public address
  and is only turned around at the router. Write selectors and the container's
  port. This is also why `allow-dns` works: it selects the CoreDNS pods, and a
  query sent to the kube-dns Service address arrives as the pod behind it.
- **Adding these components rolls nothing.** They add NetworkPolicy objects
  and touch no pod template, so a stateful app does not restart and a
  crashlooping-pod trap cannot bite. The failure mode is the opposite one: the
  app keeps running and quietly cannot reach something.

## What is left

Nothing to add. Every application namespace is covered, and the two exceptions
above are exceptions on their merits rather than a backlog.

What remains is narrowing. `monitoring` holds `allow-egress-to-cluster`,
which does not isolate it from other namespaces, because probing other
namespaces is what it is for. It has no stable target list and probably never
will. The homepage dashboard and n8n held the same rule until they were removed
on 2026-09-25.
