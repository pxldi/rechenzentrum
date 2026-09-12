# Homelab / GitOps Masterplan

> Ziel: Das bestehende Homelab schrittweise in ein sauberes, öffentliches, sicheres und modular aufgebautes GitOps-Setup überführen, ohne unnötig alles neu zu bauen. Gleichzeitig soll die Plattform mehr Kubernetes-/Flux-Funktionen nutzen und später einen persönlichen AI-/ChatOps-Agenten integrieren.

---

## 1. Zielbild

Das Homelab soll langfristig folgende Eigenschaften haben:

- **Public GitOps Monorepo** für die Cluster-Konfiguration.
- **Separate Repositories für selbst entwickelte Software** wie Cantus.
- **Keine Git-Submodules** für Apps oder Deployments.
- **Flux als zentrale GitOps-Schicht**.
- **Kustomize stärker nutzen**, inklusive Components, wo sie echten Mehrwert bieten.
- **Security by default**:
  - Default-Deny NetworkPolicies
  - möglichst wenig öffentlich exponierte Services
  - Rate Limiting und Security Controls am Edge
  - minimale ServiceAccounts/RBAC-Rechte
  - keine unverschlüsselten Secrets im Git
- **Robuste Deployments**:
  - alte Instanz bleibt verfügbar, bis die neue Instanz wirklich ready ist
  - Readiness-/Startup-Probes
  - kontrollierte Rolling Updates
- **Automatisierung**:
  - Image Updates
  - CI-Validierung
  - Drift Detection
  - Health Checks
  - Backup-/Restore-Workflows
- **Später AI-/ChatOps-Agent** über Telegram:
  - ZeroClaw als dünne Agent-Schicht
  - Tandoor-MCP
  - Homelab-MCP
  - dieselben MCP-Tools auch für Claude Code nutzbar

---

# Phase 0 – Vorbereitung des neuen Public Repositories

## Neues Repository

Das bisherige private Repository bleibt als Archiv erhalten.

Für den Public Release:

1. Neues GitHub-Repository anlegen.
2. Nur den aktuellen gewünschten Zustand übernehmen.
3. **Keine alte Commit-History übernehmen.**
4. Vor dem ersten Push den aktuellen Tree mit `gitleaks` oder vergleichbarem Tool scannen.
5. Gefundene echte Secrets immer **rotieren**, nicht nur aus Git entfernen.
6. `.gitignore`, SOPS-Regeln und Secret-Konventionen prüfen.
7. Flux anschließend auf die neue Repository-URL umstellen.

### Warum neues Repository?

Damit:

- historische Secrets nicht versehentlich veröffentlicht werden,
- alte Experimente und Repository-Strukturen nicht öffentlich mitgeschleppt werden,
- ein sauberer neuer GitOps-Root entsteht.

---

# Phase 1 – Repository-Struktur aufräumen

## Grundprinzip

Ein **GitOps-Monorepo für den Cluster**, separate Repositories für Software.

Beispiel:

```text
rechenzentrum/
├── clusters/
│   └── home/
│       ├── flux-system/
│       ├── infrastructure/
│       └── apps/
│
├── infrastructure/
│   ├── networking/
│   ├── storage/
│   ├── databases/
│   ├── observability/
│   ├── security/
│   └── controllers/
│
├── apps/
│   ├── media/
│   ├── productivity/
│   ├── home/
│   ├── ai/
│   └── ...
│
├── components/
│   ├── network-policy/
│   ├── deployment-hardening/
│   ├── monitoring/
│   └── ...
│
├── policies/
├── scripts/
├── Taskfile.yml
├── AGENTS.md
└── README.md
```

Das ist nur ein Zielbild; vorhandene Strukturen müssen nicht zwanghaft komplett umgebaut werden.

## Keine Submodules

Nicht verwenden für:

- Cantus
- Tandoor
- externe Helm-Charts
- selbst geschriebene MCP-Server

Die GitOps-Repo enthält nur den gewünschten Deployment-Zustand.

Software selbst lebt in eigenen Repositories.

---

# Phase 2 – CI und Repository-Schutz

Da das Repository öffentlich wird:

- GitHub-hosted Actions Runner verwenden.
- Den bisherigen internen/self-hosted Runner aus diesem Workflow entfernen.
- Public Pull Requests niemals auf interner Homelab-Infrastruktur ausführen.

## Branch Protection

Für `main`:

- Pull Request erforderlich.
- CI muss erfolgreich sein.
- Kein direkter Push auf `main`.
- Optional: mindestens eine Approval-Regel.
- Optional: linear history / squash merge.

## CI-Validierung

Bei jedem PR mindestens:

- YAML validieren
- Kustomize Builds ausführen
- Kubernetes-Manifeste validieren
- Flux-Konfiguration prüfen
- Policy Checks ausführen
- keine entschlüsselten Secrets zulassen

Beispielhafte Pipeline:

```text
lint
  ↓
kustomize build
  ↓
kubernetes schema validation
  ↓
policy validation
  ↓
flux validation
```

---

# Phase 3 – Einheitliche Konventionen

Nicht alles abstrahieren, aber Konsistenz erhöhen.

## Einheitliche Dateinamen

Beispielsweise:

```text
namespace.yaml
repository.yaml
release.yaml
deployment.yaml
service.yaml
ingress.yaml
networkpolicy.yaml
secret.sops.yaml
kustomization.yaml
```

## Einheitliche Labels

Mindestens:

```yaml
app.kubernetes.io/name
app.kubernetes.io/instance
app.kubernetes.io/component
app.kubernetes.io/part-of
app.kubernetes.io/managed-by
```

Damit werden später:

- Monitoring
- Policies
- Debugging
- MCP-Abfragen

deutlich einfacher.

---

# Phase 4 – Kustomize stärker nutzen

Kustomize soll bewusst stärker genutzt werden.

Nicht jede Kleinigkeit abstrahieren, aber wiederkehrende Sicherheits- und Betriebsbausteine eignen sich sehr gut als Components.

## Sinnvolle Components

### `default-deny-network-policy`

Setzt in einem Namespace grundsätzlich:

- deny ingress
- deny egress

Danach werden explizit erlaubte Verbindungen ergänzt.

### `deployment-hardening`

Kann gemeinsame Einstellungen enthalten:

```yaml
securityContext:
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault
```

und optional:

```yaml
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop:
    - ALL
```

Nicht blind auf jede Anwendung anwenden; einige Images benötigen Ausnahmen.

### `monitoring`

Wiederkehrende Ressourcen wie:

- ServiceMonitor
- PodMonitor
- Standardlabels

### `safe-rollout`

Gemeinsame Deployment-Defaults für selbst kontrollierte Apps:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1

minReadySeconds: 10
```

---

# Phase 5 – Sichere Deployments / keine unnötige Downtime

Für Deployments, bei denen mindestens eine Instanz verfügbar bleiben soll:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1

minReadySeconds: 10
```

Dazu eine echte `readinessProbe`.

Beispiel:

```yaml
readinessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 2
  periodSeconds: 5
  failureThreshold: 3
```

Falls der Start länger dauert zusätzlich:

```yaml
startupProbe:
  httpGet:
    path: /health
    port: http
  periodSeconds: 5
  failureThreshold: 30
```

## Ziel

Der alte Pod wird erst entfernt, wenn der neue Pod:

1. gestartet ist,
2. seine Readiness Probe besteht,
3. für `minReadySeconds` stabil ready war.

Eine neue Version, die sofort crashloopt, soll den funktionierenden Pod nicht unnötig verdrängen.

---

# Phase 6 – Flux stärker ausnutzen

## Dependencies

Flux-Kustomizations über `dependsOn` in logischer Reihenfolge aufbauen.

Beispiel:

```text
controllers
    ↓
storage / databases / networking
    ↓
shared infrastructure
    ↓
applications
```

Beispiel:

```yaml
spec:
  dependsOn:
    - name: cloudnative-pg
```

## Health Checks / Wait

Nicht nur Reihenfolge definieren, sondern auf echte Betriebsbereitschaft warten.

Flux soll beispielsweise nicht Tandoor deployen, bevor die konkrete Tandoor-Datenbankinstanz bereit ist. Ein bereiter CNPG-Operator allein reicht nicht.

## Drift Detection

Bei HelmReleases Drift Detection aktivieren, wo sinnvoll.

Ziel:

> Git ist die Source of Truth.

Manuelle Änderungen im Cluster sollen erkannt und wieder auf den Git-Zustand zurückgeführt werden.

---

# Phase 7 – Kubernetes Policies mit CEL

Native Kubernetes **ValidatingAdmissionPolicy** verwenden, wo sinnvoll.

Damit können ohne zusätzlichen Policy-Controller Regeln direkt im Cluster definiert werden.

Beispiele:

## Kein `:latest`

Container Images müssen eine explizite Version verwenden.

## Privileged Pods verhindern

Nur explizit erlaubte Namespaces oder Workloads dürfen privilegiert laufen.

## Host-Mounts begrenzen

`hostPath` nur dort erlauben, wo wirklich notwendig.

## Security Context erzwingen

Für geeignete Namespaces:

- `runAsNonRoot`
- `allowPrivilegeEscalation: false`
- keine unnötigen Linux Capabilities

Policy-Rollout zunächst in Audit-/Warn-Form testen, bevor produktive Deployments blockiert werden.

---

# Phase 8 – Namespace- und App-Isolation

## Cantus aus einem allgemeinen Media-Namespace herauslösen

Cantus ist selbst entwickelte Software und sollte einen eigenen Namespace bekommen.

Beispiel:

```text
cantus/
```

Vorteile:

- eigene ResourceQuota
- eigene NetworkPolicies
- eigene RBAC-Regeln
- bessere Debugging-Grenzen
- Claude Code kann exakt auf diesen Namespace beschränkt werden

Das ist besonders wichtig, wenn ein Coding Agent direkt auf Deployments zugreifen darf.

---

# Phase 9 – Netzwerk-Sicherheitsmodell

Dies ist einer der wichtigsten Umbauten.

## Prinzip

Nicht:

> „Die App hat schon Login, also kann sie ins Internet.“

Sondern:

> „Muss diese App überhaupt aus dem Internet erreichbar sein?“

Jeder Service wird einer Exposure-Klasse zugeordnet.

### Klasse A – Internet Public

Muss wirklich öffentlich erreichbar sein.

Beispiele:

- öffentliche Website
- Dienste, die bewusst extern genutzt werden

Schutz:

- TLS
- Rate Limiting
- sichere Header
- Auth, wo sinnvoll
- Default-Deny NetworkPolicy
- möglichst minimale Backend-Kommunikation

### Klasse B – Authenticated Internet

Extern erreichbar, aber nur hinter zusätzlicher Authentifizierung.

Beispiel:

```text
Internet
   ↓
Reverse Proxy / Gateway
   ↓
Authentik / SSO
   ↓
Service
```

### Klasse C – VPN Only

Nur über WireGuard/Tailscale/etc.

Gute Kandidaten:

- Admin-UIs
- Grafana
- Kubernetes Dashboards
- Datenbank-UIs
- interne Entwicklerwerkzeuge
- Claude-Code-Remote-Umgebung

### Klasse D – Cluster Internal

Überhaupt kein externer Zugriff.

Beispiele:

- Datenbanken
- interne APIs
- MCP-Backends
- Message Queues

---

# Phase 10 – NetworkPolicies

Standard für neue Namespaces:

```text
default deny
```

Danach explizite Kommunikation.

Beispiel:

```text
Tandoor
   ↓
Postgres
```

Nur dieser konkrete Traffic wird freigegeben.

Ein kompromittierter Tandoor-Pod soll nicht automatisch:

- Jellyfin erreichen,
- Flux erreichen,
- Kubernetes APIs erreichen,
- andere Datenbanken durchsuchen.

## DNS beachten

Bei Default-Deny-Egress muss DNS explizit erlaubt werden.

---

# Phase 11 – Edge / Gateway / Rate Limiting

Mittelfristig Gateway API prüfen und ggf. als Nachfolger bzw. Ergänzung des bestehenden Ingress-Ansatzes einführen.

Nicht alles sofort migrieren.

## Für öffentlich exponierte Apps

Je nach Gateway/Proxy:

- Rate Limiting
- Request Body Limits
- Timeouts
- Connection Limits
- Security Headers
- optional IP-basierte Regeln
- Authentik/Forward Auth

## Wichtig

Rate Limiting nicht global blind gleich konfigurieren.

Beispielsweise:

```text
Login/API Endpoint      → relativ streng
große Media Downloads   → andere Limits
Websocket Anwendungen   → eigene Regeln
```

---

# Phase 12 – Resource Management

Für relevante Workloads:

```yaml
resources:
  requests:
    cpu: ...
    memory: ...
  limits:
    memory: ...
```

CPU-Limits nur bewusst setzen.

Zusätzlich können Namespaces bekommen:

- ResourceQuota
- LimitRange

Damit kann ein fehlerhafter Service nicht den kompletten Cluster leerziehen.

---

# Phase 13 – Backups und Disaster Recovery

Ein Backup ist erst vertrauenswürdig, wenn der Restore getestet wurde.

Für kritische Services dokumentieren:

```text
backup
↓
fresh namespace / clean target
↓
restore
↓
service starts
↓
data verified
```

Mindestens für:

- Datenbanken
- Tandoor
- wichtige Media-Metadaten
- selbst entwickelte Dienste mit persistentem State

Optional regelmäßig automatisierte Restore-Tests.

---

# Phase 14 – Taskfile als Bedienoberfläche

Ein kleines `Taskfile.yml` soll häufige Aktionen vereinheitlichen.

Beispiel:

```bash
task validate
task build
task flux:status
task reconcile
task secrets:scan
task policy:test
```

Die gleichen Tasks können lokal und in CI verwendet werden.

Keine riesige eigene Build-Plattform bauen.

---

# Phase 15 – Observability

Bestehendes Monitoring schrittweise konsistenter machen.

Ziele:

- Metrics
- Logs
- Alerts
- Flux Status
- Backup Status
- Deployment Status

Für selbst entwickelte Apps konsistente `/health`- und `/metrics`-Endpoints vorsehen.

Diese Endpoints helfen später ebenfalls dem Homelab-MCP.

---

# Phase 16 – Image Automation

Für geeignete Drittanbieter-Apps kann Flux Image Automation eingesetzt werden.

Pipeline:

```text
new image
   ↓
Flux detects version
   ↓
Git commit updates desired version
   ↓
normal GitOps reconciliation
   ↓
safe rolling deployment
```

Nicht jedes Image automatisch übernehmen.

Je nach Service:

- Patch Releases automatisch
- Minor Releases optional
- Major Releases manuell

Bei selbst entwickelter Software bleibt die CI/CD-Strategie separat im jeweiligen Projekt-Repo.

---

# Phase 17 – ZeroClaw / persönlicher ChatOps-Agent

Erst nachdem die Grundstruktur sauber genug ist.

## Architektur

```text
Telegram
   │
   ▼
ZeroClaw
   │
   ├──────────────► Tandoor MCP
   │
   └──────────────► Homelab MCP
                         ▲
                         │
                    Claude Code
```

ZeroClaw soll **nicht** direkt Cluster-Admin sein.

Es ist:

- Chat Interface
- Agent Loop
- Memory
- Tool Orchestrator

---

# Phase 18 – Tandoor MCP

Kleiner dedizierter Service.

Beispiel-Tools:

```text
search_recipes
get_recipe
create_recipe
update_recipe
list_meal_plan
add_to_meal_plan
```

Nicht einfach uneingeschränkten Shell-/curl-Zugriff an den Agent geben.

Vorteile:

- Agent kennt die API semantisch.
- Validation findet zentral statt.
- API-Token bleibt im MCP-Service.
- Funktionen sind nachvollziehbar und testbar.

## Persönliche Präferenzen

Nicht im MCP selbst hart codieren.

ZeroClaw Memory / User Config enthält beispielsweise:

- vegan
- bevorzugte Zutaten
- Portionsgrößen
- Abneigungen
- typische Kochzeiten

Das MCP stellt die Aktionen bereit; der Agent entscheidet aufgrund des Kontexts.

---

# Phase 19 – Homelab MCP

Das Homelab-MCP wird eine strukturierte Schnittstelle auf den Cluster.

## Stufe 1 – Read Only

Zuerst nur:

```text
list_services
get_service_status
get_deployment_status
get_pod_logs
get_recent_events
get_flux_status
get_backup_status
```

## Stufe 2 – begrenzte Aktionen

Später gezielt:

```text
restart_deployment
trigger_backup
reconcile_flux_resource
```

Keine generische Funktion wie:

```text
run_kubectl(command)
```

für den Telegram-Agenten.

---

# Phase 20 – Claude Code + Homelab MCP

Claude Code darf zusätzlich weiterhin direkt `kubectl` verwenden, wenn das für echtes Debugging sinnvoll ist.

Das MCP ist kein vollständiger Ersatz für Kubernetes CLI.

Es dient als:

- stabile High-Level API
- wiederverwendbare Cluster-Abstraktion
- gemeinsame Schnittstelle für mehrere Agenten

Beispiel:

```text
Claude Code
   ├─ Homelab MCP
   └─ kubectl
```

Für alltägliche Diagnosen:

```text
get_deployment_logs("cantus")
```

Für tiefe Debugging-Arbeit:

```bash
kubectl ...
```

---

# Phase 21 – Agent Security

ZeroClaw erhält:

- keinen Cluster-Admin-Zugriff
- keine generische Shell auf den Kubernetes Nodes
- keine Secrets anderer Anwendungen
- nur MCP-Zugriff

Homelab-MCP erhält einen eigenen ServiceAccount mit exakt definiertem RBAC.

Claude Codes Kubernetes-Zugriff sollte auf die Namespaces beschränkt werden, die es tatsächlich entwickeln/debuggen muss.

Für Cantus beispielsweise:

```text
namespace: cantus
```

statt Zugriff auf einen kompletten Media-Namespace.

---

# Phase 22 – Automatisierung des Agents

Wenn die Basis funktioniert:

## Telegram-Kommandos in natürlicher Sprache

Beispiele:

> Wie geht es Cantus?

> Zeig mir die letzten Fehler von Tandoor.

> Starte ein Backup von Immich.

> Speichere dieses Rezept in Tandoor.

> Was kann ich diese Woche mit meinen gespeicherten Rezepten kochen?

## Später proaktive Tasks

Beispiele:

- fehlgeschlagene Backups melden
- CrashLoops melden
- ungewöhnlich hohe Ressourcen melden
- Flux-Reconciliation-Fehler melden

Der Agent sollte nicht bei jedem kleinen Event nerven, sondern nur bei relevanten Problemen.

---

# Empfohlene Reihenfolge als Pull Requests

## PR 1 – Public Repository Bootstrap

- neues Repo
- aktueller Tree
- Secret Scan
- README
- AGENTS.md
- GitHub Hosted CI
- Branch Protection vorbereiten

## PR 2 – Validation / Taskfile

- `Taskfile.yml`
- YAML Validation
- Kustomize Build Tests
- Kubernetes Schema Validation
- Flux Checks

## PR 3 – Struktur und Konventionen

- einheitliche Dateinamen
- Labels
- klare App-/Infrastructure-Grenzen

## PR 4 – Cantus Isolation

- eigener Namespace
- eigene RBAC-Regeln
- NetworkPolicies
- Claude-Code-Zugriff begrenzen

## PR 5 – Kustomize Components

Zuerst:

- Default Deny
- Deployment Hardening
- Safe Rollout

## PR 6 – Deployment Reliability

Für geeignete Services:

- readinessProbe
- startupProbe
- `maxUnavailable: 0`
- `maxSurge: 1`
- `minReadySeconds`

## PR 7 – Flux Improvements

- `dependsOn`
- health checks
- wait semantics
- Helm drift detection

## PR 8 – Network Security

- Exposure-Matrix aller Services
- VPN-only Services identifizieren
- Default-Deny NetworkPolicies
- explizite Allow-Regeln

## PR 9 – Edge Security

- Rate Limiting
- Security Headers
- Auth
- Gateway API Evaluation

## PR 10 – Admission Policies

- kein `latest`
- privileged einschränken
- Security Context Policies
- erst Audit, dann Enforce

## PR 11 – Backup / Restore Tests

- Restore-Dokumentation
- Test-Restore kritischer Services
- Backup Status Monitoring

## PR 12 – Image Automation

- ausgewählte Services
- definierte Update-Regeln
- GitOps-basierte Updates

## PR 13 – ZeroClaw

- eigener Namespace
- Telegram
- persistentes Memory
- minimale Rechte
- noch kein direkter Kubernetes-Zugriff

## PR 14 – Tandoor MCP

- Search/Create/Update
- API Token als Secret
- Integration in ZeroClaw

## PR 15 – Homelab MCP Read Only

- Status
- Logs
- Events
- Flux
- Backup Status

## PR 16 – Claude Code Integration

- Homelab MCP
- namespace-limitiertes kubectl
- Cantus-Workflow

## PR 17 – Safe Homelab Actions

- Deployment Restart
- Backup Trigger
- Flux Reconcile
- strikte Allowlist

---

# Was bewusst **nicht** gemacht werden soll

- Kein unnötiges Multi-Cluster-Framework.
- Keine Git Submodules.
- Kein eigener interner CI Runner nur aus Prinzip.
- Kein Cluster-Admin für den AI-Agenten.
- Keine universelle `kubectl`-Execution über Telegram.
- Keine vollständige Kustomize-Abstraktion jedes einzelnen YAML-Feldes.
- Kein Big-Bang-Rewrite.
- Nicht jeden Service zwanghaft öffentlich erreichbar machen.

---

# Endzustand

```text
GitHub
│
├── rechenzentrum (public GitOps)
│
├── cantus
├── homelab-mcp
├── tandoor-mcp
└── weitere eigene Projekte

                    GitOps
GitHub ─────────────────────────► Flux
                                   │
                                   ▼
                            Kubernetes Cluster
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
     Applications             Infrastructure              AI
         │                         │                         │
      Tandoor                   CNPG                    ZeroClaw
      Cantus                    Storage                    │
      Media                     Network                    ├─ Tandoor MCP
       ...                      Security                   └─ Homelab MCP
                                                               ▲
                                                               │
                                                          Claude Code
```

Das Ziel ist kein maximal komplexes Homelab, sondern ein Setup, das moderne Kubernetes-/GitOps-Funktionen bewusst nutzt, gut abgesichert ist, Spaß zum Experimentieren bietet und trotzdem verständlich bleibt.
