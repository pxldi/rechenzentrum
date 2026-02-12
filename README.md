# rechenzentrum

Das heimische Rechenzentrum - A declarative homelab infrastructure.

## Stack

- **OS**: NixOS
- **Orchestration**: K3s
- **GitOps**: Flux
- **Storage**: OpenEBS (LocalPV + Mayastor)
- **Backups**: Velero + Kopia
- **Secrets**: SOPS + Age

## Repository Structure
```
rechenzentrum/
├── nix/              # NixOS configuration
│   ├── flake.nix
│   ├── configuration.nix
│   └── modules/
├── kubernetes/       # K8s manifests (managed by Flux)
│   ├── flux-system/
│   ├── infrastructure/
│   └── apps/
├── docs/            # Documentation
└── scripts/         # Helper scripts
```

## Quick Start

TODO

## Documentation

TODO

---

Built as a personal learning experience and to ensure privacy + comfort for cloud services.
