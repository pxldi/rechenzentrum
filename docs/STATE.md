# Current State

**Last Updated:** 2026-02-13

---

## 🏗️ Architecture Overview

### Hardware
- **CPU:** AMD Ryzen 5 5600G (6C/12T)
- **RAM:** 32GB DDR4
- **Storage:**
  - 1x 1TB NVMe SSD (OS + critical data)
  - 2x 24TB HDD (media + replicas)

### Software Stack
- **OS:** NixOS
- **Kubernetes:** K3s
- **GitOps:** Flux CD
- **Secrets:** SOPS + age encryption
- **DNS:** Cloudflare
- **Ingress:** Traefik
- **TLS:** cert-manager + Let's Encrypt
- **Storage:** OpenEBS

---

## 📁 Repository Structure
```
rechenzentrum/
├── nix/                           # NixOS configuration
│   ├── flake.nix                  # Flake entry point
│   ├── configuration.nix          # Main config
│   ├── hardware-configuration.nix # Generated hardware config
│   └── modules/                   # Modular configs
│       ├── base.nix               # Users, SSH
│       ├── k3s.nix                # Kubernetes
│       ├── storage.nix            # Disk mounts
│       ├── networking.nix         # Firewall, network
│       └── backup.nix             # Backup configs
│
├── kubernetes/                    # Kubernetes manifests
│   ├── flux-system/               # Flux bootstrap (DO NOT EDIT)
│   ├── infrastructure/            # Infrastructure layer
│   │   ├── sources/               # HelmRepositories
│   │   ├── storage/               # OpenEBS + StorageClasses
│   │   └── networking/            # Traefik, cert-manager, DDNS
│   ├── infrastructure-config/     # Post-install configs
│   │   ├── cert-manager/          # ClusterIssuers
│   │   └── traefik/               # IngressRoutes
│   ├── apps/                      # Applications (future)
│   ├── infrastructure.yaml        # Flux Kustomization
│   ├── infrastructure-config.yaml # Flux Kustomization (depends on infra)
│   └── kustomization.yaml         # Root kustomization
│
├── docs/                          # Documentation
│   └── STATE.md                   # This file
│
├── .sops.yaml                     # SOPS encryption rules
├── renovate.json                  # Automated updates
└── README.md                      # Project overview
```

---

## ✅ Completed Phases

### Phase 1: GitOps Foundation ✅
- [x] NixOS installed with flakes
- [x] K3s Kubernetes cluster
- [x] Flux CD bootstrapped
- [x] SOPS encryption configured
- [x] Git workflow established
- [x] Branch protection enabled

### Phase 2: Storage Layer ✅
- [x] OpenEBS deployed
- [x] Three StorageClasses created:
  - `local-ssd` (default) - NVMe for critical data
  - `local-hdd1` - First 24TB HDD for bulk storage
  - `local-hdd2` - Second 24TB HDD for replicas
- [x] PVC creation tested and verified

### Phase 3: Networking Stack ✅
- [x] Traefik v39 ingress controller
- [x] cert-manager for Let's Encrypt TLS
- [x] Cloudflare DDNS for dynamic IP updates
- [x] Traefik dashboard accessible at https://traefik.pxldi.de
- [x] Basic auth configured and working
- [x] HTTPS certificates auto-provisioning

---

## 🚧 Pending Phases

### Phase 4: Backup Infrastructure ⏳
- [ ] Velero for cluster backups → Backblaze B2
- [ ] Kopia for file-level backups
- [ ] External HDD automation (systemd on NixOS)
- [ ] Telegram notifications

### Phase 5: Applications ⏳
- [ ] Choose and deploy first app
- [ ] Additional apps

### Phase 6: Monitoring (Optional) ⏳
- [ ] Prometheus + Grafana
- [ ] Node exporter
- [ ] K8s metrics

---

## 🌐 Network Configuration

### Domain
- **DNS Provider:** Cloudflare
- **Records:** Wildcard (`*.domain.de`) auto-updated via DDNS
- **Proxied:** No (DNS-only mode for direct connection)

### Port Forwarding
- **80 (HTTP)** → 192.168.0.153:80
- **443 (HTTPS)** → 192.168.0.153:443

### LoadBalancer
- **Type:** K3s ServiceLB (uses node IP)
- **External IP:** 192.168.0.153
- **Service:** `traefik` in `traefik` namespace

---

## 🔄 Git Workflow

### Branch Protection Rules
**Branch:** `main`
- ✅ Restrict deletions
- ✅ Require pull request before merging
- ✅ Required approvals: 0 (solo project)
- ✅ Block force pushes (after initial setup)
- ✅ Allowed merge methods: **Squash only**

### Branch Naming Convention
```
feat/description      - New features
fix/description       - Bug fixes
chore/description     - Maintenance (deps, cleanup)
docs/description      - Documentation
refactor/description  - Code restructuring
```

**Examples:**
- `feat/openebs-storage`
- `fix/traefik-chart-version`
- `chore/update-dependencies`
- `docs/add-architecture-diagram`

### Commit Message Format (Conventional Commits)
```
type(scope): subject

Optional body with details.

Optional footer (breaking changes, issue refs).
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `chore` - Maintenance (no user-facing changes)
- `docs` - Documentation
- `refactor` - Code restructure
- `perf` - Performance improvement
- `test` - Adding tests
- `build` - Build system changes
- `ci` - CI/CD changes

**Scopes:**
- `nix` - NixOS configuration
- `flux` - Flux GitOps
- `storage` - Storage layer (OpenEBS)
- `networking` - Networking (Traefik, cert-manager)
- `traefik` - Traefik specific
- `cert-manager` - cert-manager specific
- `sops` - Secrets management
- `apps` - Applications

**Examples:**
```
feat(storage): add OpenEBS with three storage classes
fix(traefik): update values for chart v39 schema
chore(deps): update Flux to v2.4.0
docs(readme): add installation instructions
refactor(infrastructure): separate config from installation
```

### PR Workflow
1. **Create branch** from `main`
```bash
   git checkout main
   git pull origin main
   git checkout -b feat/new-feature
```

2. **Make commits** (can be messy on branch)
```bash
   git add .
   git commit -m "wip: working on feature"
```

3. **Push branch**
```bash
   git push origin feat/new-feature
```

4. **Create PR** on GitHub
   - Title: Clear description of change
   - Description: What and why

5. **Squash and merge** (enforced by branch rules)
   - All commits squashed into one clean commit on main
   - Descriptive commit message following convention

6. **Delete branch** after merge
```bash
   git checkout main
   git pull origin main
   git branch -d feat/new-feature
```

7. **Repeat** for next feature
 
---

## 📊 Current Deployments

### Infrastructure
| Component | Namespace | Status | Version |
|-----------|-----------|--------|---------|
| Flux | flux-system | ✅ Running | Latest |
| OpenEBS | openebs | ✅ Running | 4.2.0 |
| Traefik | traefik | ✅ Running | 39.0.0 |
| cert-manager | cert-manager | ✅ Running | 1.16.0 |
| Cloudflare DDNS | cloudflare-ddns | ✅ Running | Latest |

### Storage Classes
| Name | Type | Location | Default | Use Case |
|------|------|----------|---------|----------|
| local-ssd | LocalPV | /var/openebs/local/ssd | ✅ Yes | Critical data, databases |
| local-hdd1 | LocalPV | /mnt/hdd1/openebs | No | Bulk media storage |
| local-hdd2 | LocalPV | /mnt/hdd2/openebs | No | Replicas, backups |

### Resource Allocation
**Current usage (~2GB RAM):**
- K3s control plane: 500MB
- Traefik: 200MB
- cert-manager: 100MB
- OpenEBS: 200MB
- Flux: 100MB
- Misc: 900MB

**Available:** ~30GB RAM free for applications

---

## 🛠️ Maintenance Tasks

### Regular
- **Weekly:** Check Flux reconciliation status
```bash
  flux get all
```
- **Monthly:** Review Renovate PRs and update dependencies
- **Quarterly:** Test disaster recovery procedures

### Updates
- **Renovate:** Automatically creates PRs for updates
  - Schedule: Every weekend
  - Auto-merge: Minor and patch versions
  - Manual review: Major versions

### Monitoring
```bash
# Check cluster health
kubectl get nodes
kubectl get pods -A

# Check Flux status
flux get kustomizations
flux get helmreleases -A

# Check certificates
kubectl get certificates -A
kubectl get clusterissuers

# Check storage
kubectl get pvc -A
kubectl get sc
```

---

## 🔧 Common Operations

### Deploy new application
1. Create app directory: `kubernetes/apps/category/appname/`
2. Add manifests (namespace, helmrelease, ingress, etc.)
3. Create kustomization.yaml
4. Update `kubernetes/apps/kustomization.yaml`
5. Commit to branch, create PR, merge

### Update SOPS secret
```bash
# Edit secret (auto-decrypts)
sops kubernetes/path/to/secret.yaml

# Make changes, save - auto re-encrypts
# Commit and push
```

### Force Flux reconciliation
```bash
# Reconcile specific kustomization
flux reconcile kustomization infrastructure --with-source

# Reconcile everything
flux reconcile kustomization flux-system --with-source
```

### Rebuild NixOS
```bash
# On server
sudo nixos-rebuild switch --flake /etc/nixos#rechenzentrum

# Or from repo
cd /root/rechenzentrum
sudo nixos-rebuild switch --flake .#rechenzentrum
```

### Check Traefik routes
```bash
# List IngressRoutes
kubectl get ingressroute -A

# Check Traefik service
kubectl get svc -n traefik

# View Traefik logs
kubectl logs -n traefik -l app.kubernetes.io/name=traefik
```

---

## 📚 Useful Commands

### NixOS
```bash
# Rebuild system
sudo nixos-rebuild switch

# Rollback to previous generation
sudo nixos-rebuild switch --rollback

# List generations
sudo nix-env --list-generations --profile /nix/var/nix/profiles/system

# Garbage collection
sudo nix-collect-garbage -d
```

### Kubernetes
```bash
# Get everything
kubectl get all -A

# Describe resource
kubectl describe pod <name> -n <namespace>

# Logs
kubectl logs <pod> -n <namespace> -f

# Execute in pod
kubectl exec -it <pod> -n <namespace> -- /bin/sh

# Port forward
kubectl port-forward svc/<service> -n <namespace> 8080:80
```

### Flux
```bash
# Check all resources
flux get all

# Suspend/resume reconciliation
flux suspend kustomization <name>
flux resume kustomization <name>

# Export current state
flux export kustomization --all

# Check logs
flux logs --all-namespaces
```

### SOPS
```bash
# Encrypt file
sops -e -i path/to/secret.yaml

# Decrypt file (view only)
sops -d path/to/secret.yaml

# Edit file (interactive)
sops path/to/secret.yaml

# Rotate keys
sops -r -i path/to/secret.yaml
```

---

## 🔗 Important Links

### Documentation
- **NixOS Manual:** https://nixos.org/manual/nixos/stable/
- **Flux Documentation:** https://fluxcd.io/docs/
- **Traefik Docs:** https://doc.traefik.io/traefik/
- **cert-manager:** https://cert-manager.io/docs/
- **SOPS:** https://github.com/getsops/sops

### GitHub
- **Repository:** https://github.com/pxldi/rechenzentrum
- **Issues:** https://github.com/pxldi/rechenzentrum/issues
- **PRs:** https://github.com/pxldi/rechenzentrum/pulls

### Services
- **Cloudflare Dashboard:** https://dash.cloudflare.com
- **Traefik Dashboard:** https://traefik.pxldi.de

---

## 🎯 Next Steps

### Immediate
1. [ ] Add quiet-mode configuration (fan control, HDD spin-down)
2. [ ] Choose first application to deploy
3. [ ] Deploy first application with ingress

### Short-term
1. [ ] Set up Velero for cluster backups
2. [ ] Configure Kopia for file backups
3. [ ] Deploy 2-3 core applications
4. [ ] Test backup and restore procedures

### Medium-term
1. [ ] Add monitoring (Prometheus + Grafana)
2. [ ] Implement external HDD backup automation
3. [ ] Set up Telegram notifications
4. [ ] Document disaster recovery procedures

### Long-term
1. [ ] Consider second node for HA
2. [ ] Implement Mayastor for replicated storage
3. [ ] Add network policies for security
4. [ ] Explore additional applications
