# Rollout inventory

Live baseline, 2026-09-12; includes Helm-generated workloads.
Review shared storage, concurrent writers and capacity before changing strategy.
The Excalidraw pilot is configured separately; this table records the state before it.

| Namespace | Workload | Strategy | PVCs | Readiness on all containers |
| --- | --- | --- | --- | --- |
| adventurelog | Deployment/adventurelog-backend | Recreate | adventurelog-media | yes |
| adventurelog | Deployment/adventurelog-db | Recreate | adventurelog-db | yes |
| adventurelog | Deployment/adventurelog-frontend | RollingUpdate | none | yes |
| arc-systems | Deployment/arc-controller-gha-rs-controller | RollingUpdate | none | no |
| authentik | StatefulSet/authentik-postgresql | RollingUpdate | none | yes |
| authentik | Deployment/authentik-server | RollingUpdate | none | yes |
| authentik | Deployment/authentik-worker | RollingUpdate | none | yes |
| branding | Deployment/branding | RollingUpdate | none | yes |
| cert-manager | Deployment/cert-manager | RollingUpdate | none | no |
| cert-manager | Deployment/cert-manager-cainjector | RollingUpdate | none | no |
| cert-manager | Deployment/cert-manager-webhook | RollingUpdate | none | yes |
| claudebox | Deployment/claudebox | Recreate | claudebox-data-pvc | no |
| cloudflare-ddns | Deployment/cloudflare-ddns | RollingUpdate | none | no |
| cnpg-system | Deployment/barman-cloud-plugin-barman-cloud | Recreate | none | yes |
| cnpg-system | Deployment/cnpg-cloudnative-pg | RollingUpdate | none | yes |
| device-plugins | DaemonSet/generic-device-plugin | RollingUpdate | none | no |
| excalidraw | Deployment/excalidraw | RollingUpdate | none | yes |
| flux-system | Deployment/helm-controller | RollingUpdate | none | yes |
| flux-system | Deployment/kustomize-controller | RollingUpdate | none | yes |
| flux-system | Deployment/notification-controller | RollingUpdate | none | yes |
| flux-system | Deployment/source-controller | Recreate | none | yes |
| fredy | Deployment/fredy | Recreate | fredy-config, fredy-data | yes |
| gotify | Deployment/gotify | Recreate | gotify-data-pvc | yes |
| grimmory | Deployment/grimmory | Recreate | grimmory-bookdrop-pvc, grimmory-books-pvc, grimmory-data-pvc | yes |
| grimmory | Deployment/grimmory-mariadb | Recreate | grimmory-mariadb-pvc | yes |
| home-assistant | StatefulSet/home-assistant | RollingUpdate | none | yes |
| home-assistant | Deployment/matter-server | Recreate | matter-server-data | yes |
| home-assistant | Deployment/otbr | Recreate | otbr-data | no |
| immich | Deployment/immich-machine-learning | RollingUpdate | immich-machine-learning | yes |
| immich | Deployment/immich-server | RollingUpdate | immich-library-pvc | yes |
| immich | Deployment/immich-valkey | Recreate | immich-valkey | yes |
| jdownloader | Deployment/jdownloader | Recreate | jdownloader-config, jdownloader-downloads | no |
| karakeep | Deployment/karakeep | Recreate | karakeep-data | no |
| karakeep | StatefulSet/karakeep-meilisearch | RollingUpdate | none | yes |
| kube-system | Deployment/coredns | RollingUpdate | none | yes |
| kube-system | Deployment/metrics-server | RollingUpdate | none | yes |
| kube-system | DaemonSet/svclb-minecraft-7b0e2051 | RollingUpdate | none | no |
| kube-system | DaemonSet/svclb-palworld-68fa85b4 | RollingUpdate | none | no |
| kube-system | DaemonSet/svclb-traefik-c7aec652 | RollingUpdate | none | no |
| media | Deployment/cantus | Recreate | cantus-music-pvc, downloads-pvc, cantus-uploads-pvc | yes |
| media | Deployment/jellyfin | Recreate | jellyfin-config-pvc, jellyfin-data-pvc, media-pvc | yes |
| media | Deployment/navidrome | Recreate | soundcloud-music-pvc, cantus-music-pvc, navidrome-data-pvc | yes |
| media | Deployment/prowlarr | Recreate | prowlarr-config-pvc | yes |
| media | Deployment/radarr | Recreate | radarr-config-pvc, downloads-pvc, media-pvc | yes |
| media | Deployment/sabnzbd | Recreate | sabnzbd-config-pvc, downloads-pvc | yes |
| media | StatefulSet/seerr-seerr-chart | RollingUpdate | seerr-config-pvc | yes |
| media | Deployment/slskd | Recreate | slskd-config-pvc, downloads-pvc, cantus-music-pvc | yes |
| media | Deployment/sonarr | Recreate | sonarr-config-pvc, downloads-pvc, media-pvc | yes |
| minecraft | Deployment/minecraft | Recreate | minecraft-data | yes |
| monitoring | Deployment/gatus | RollingUpdate | none | yes |
| opengym | Deployment/opengym | Recreate | opengym-data, opengym-media | yes |
| firefly | Deployment/firefly | Recreate | firefly-upload | yes |
| nextcloud | Deployment/nextcloud | Recreate | nextcloud-nextcloud, nextcloud-data-pvc | no |
| nextcloud | StatefulSet/nextcloud-postgresql | RollingUpdate | none | yes |
| nextcloud | StatefulSet/nextcloud-redis-master | RollingUpdate | none | yes |
| nextcloud | StatefulSet/nextcloud-redis-replicas | RollingUpdate | none | yes |
| observability | StatefulSet/alertmanager-kube-prometheus-stack-alertmanager | RollingUpdate | none | no |
| observability | Deployment/gotify-bridge-critical | RollingUpdate | none | yes |
| observability | Deployment/gotify-bridge-flux | RollingUpdate | none | yes |
| observability | Deployment/gotify-bridge-warning | RollingUpdate | none | yes |
| observability | Deployment/kube-prometheus-stack-grafana | Recreate | kube-prometheus-stack-grafana | no |
| observability | Deployment/kube-prometheus-stack-kube-state-metrics | RollingUpdate | none | yes |
| observability | Deployment/kube-prometheus-stack-operator | RollingUpdate | none | yes |
| observability | DaemonSet/kube-prometheus-stack-prometheus-node-exporter | RollingUpdate | none | yes |
| observability | StatefulSet/prometheus-kube-prometheus-stack-prometheus | RollingUpdate | none | no |
| observability | Deployment/speedtest-exporter | RollingUpdate | none | yes |
| obsidian-sync | StatefulSet/obsidian-sync | RollingUpdate | obsidian-sync-data-pvc | yes |
| ollama | Deployment/ollama | Recreate | ollama-models | yes |
| openebs | Deployment/openebs-localpv-provisioner | Recreate | none | no |
| palworld | Deployment/palworld | Recreate | palworld-data | no |
| paperless | Deployment/paperless | Recreate | paperless-data-pvc, paperless-media-pvc, paperless-consume-pvc, paperless-export-pvc | yes |
| paperless | Deployment/paperless-postgres | Recreate | paperless-postgres-pvc | yes |
| paperless | Deployment/paperless-redis | Recreate | paperless-redis-pvc | yes |
| searxng | Deployment/searxng | RollingUpdate | none | yes |
| tandoor | Deployment/tandoor | Recreate | tandoor-media-pvc | yes |
| traefik | Deployment/traefik | RollingUpdate | traefik | yes |
| velero | DaemonSet/node-agent | RollingUpdate | none | no |
| velero | Deployment/velero | Recreate | none | yes |
| velero | Deployment/velero-ui | RollingUpdate | none | yes |
| whisper-cpp | Deployment/whisper-cpp | Recreate | whisper-cpp-models | yes |
