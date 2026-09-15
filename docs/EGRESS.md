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

| Namespace | What it may reach | Evidence |
| --- | --- | --- |
| `excalidraw` | DNS | The pilot, 2026-09-12 |
| `gotify` | DNS | Clients connect inbound and hold the socket; the server initiates nothing. `/proc/net/tcp` in the live pod held one established socket, inbound from a cluster address |
| `obsidian-sync` | DNS | CouchDB, single node, no clustering and no replication target of its own. LiveSync clients connect inbound through Traefik. No established outbound socket in the live pod |

## Before locking a namespace

1. **Read the pod's own connections.** `kubectl -n <ns> exec <pod> -- sh -c 'cat
   /proc/net/tcp /proc/net/tcp6'` and keep the rows in state `01`
   (ESTABLISHED). Column 2 is local, column 3 is remote; a remote with an
   ephemeral port is an inbound connection and does not need an egress rule. Do
   this while the app is doing something, not while it idles.
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
- **A pod calling a `pxldi.de` name does not take a cluster path.** CoreDNS
  forwards to AdGuard, which answers with the node's address, so the request
  goes pod to node to Traefik. A `namespaceSelector` rule for the destination
  namespace will not match it; that needs an `ipBlock` for the node. Apps sitting
  behind `authentik-forward-auth` are not affected, because Traefik does the
  authentication and the app never talks to Authentik itself.
- **Adding these two components rolls nothing.** They add NetworkPolicy objects
  and touch no pod template, so a stateful app does not restart and a
  crashlooping-pod trap cannot bite. The failure mode is the opposite one: the
  app keeps running and quietly cannot reach something.

## Not yet assessed

Every other app namespace. The ones that will need real allowance sets rather
than DNS alone, roughly in order of difficulty: anything with an in-namespace
database (`grimmory`, `adventurelog`, `sure`, `ryot`, `sparky-fitness`,
`overleaf`), anything with a CNPG cluster in its own namespace (`immich`, `n8n`,
`tandoor`, `multica`, `cantus`), anything that fetches from the internet by
design (`karakeep`, `paperless-ngx`, `searxng`, `glance`, `gethomepage`,
`ollama`, `jdownloader`, the `media` namespace), and `slskd`, whose egress
already goes through gluetun's tunnel.

`media` deserves its own warning: one `default-deny-egress` there covers
jellyfin, four *arr apps, sabnzbd and Cantus at once. Split the requirements per
app first.
