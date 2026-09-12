{ config, lib, pkgs, ... }:

let
  # Image GC, as a kubelet config drop-in rather than a flag or
  # services.k3s.extraKubeletConfig. Both of those are wrong here, for
  # different reasons.
  #
  # There is no --image-maximum-gc-age flag: grepping the k3s binary finds 0
  # occurrences of the flag name and 6 of the ImageMaximumGCAge struct field,
  # so it is settable only through a KubeletConfiguration file.
  #
  # And extraKubeletConfig cannot reach it. That option lowers to
  # `--kubelet-arg=config=<file>`, but kubelet merges its config *directory*
  # over the file it was handed, and k3s writes 00-k3s-defaults.conf into that
  # directory with `imageMaximumGCAge: 0s` set explicitly. Anything passed via
  # --config loses to it. The thresholds below are absent from that file and
  # would have worked either way; the one setting that actually matters is the
  # one that would have silently done nothing.
  #
  # 10- sorts after 00-, and later drop-ins win.
  kubeletImageGC = pkgs.writeText "10-image-gc.conf" ''
    apiVersion: kubelet.config.k8s.io/v1beta1
    kind: KubeletConfiguration
    # The knob that actually prevents accumulation. Kubelet only ran image GC
    # under disk pressure, and the default trigger of 85% was never reached --
    # the disk sat at 67% while 447 GB of superseded images piled up behind it,
    # 21.8M inodes, five versions of ollama, both openclaw images months after
    # the app was deleted. A manual prune reclaimed 390 GB. Without an age
    # bound, Renovate rebuilds that pile at the same rate it built the first.
    #
    # An image backing a running container is never "unused", so nothing
    # serving traffic is at risk here -- only genuinely orphaned layers, plus
    # the occasional re-pull for a job that runs less often than weekly.
    imageMaximumGCAge: 168h
    # Safety net, not the mechanism. Kept well clear of the eviction-hard
    # nodefs.available<10% threshold set below so that GC gets a chance to
    # reclaim long before the kubelet starts evicting pods for disk.
    imageGCHighThresholdPercent: 70
    imageGCLowThresholdPercent: 55
  '';

  # The node's own /etc/resolv.conf carries `search lan` from DHCP, and kubelet
  # copies the host search list onto the end of every pod's, producing:
  #
  #   search <ns>.svc.cluster.local svc.cluster.local cluster.local lan
  #   options ndots:5
  #
  # Under ndots:5 any name with fewer than five dots is search-expanded before
  # it is tried as written. The three cluster.local variants cost nothing --
  # CoreDNS answers them locally -- but the `lan` variant is forwarded to the
  # router and comes back NXDOMAIN. Every internal call by FQDN therefore burns
  # one external query that cannot ever succeed: sonarr.media.svc.cluster.local
  # has four dots, so `sonarr.media.svc.cluster.local.lan` goes upstream first.
  #
  # It is not a rounding error. Over 122 days CoreDNS forwarded 21.4M queries to
  # the router, 18.7M of them NXDOMAIN -- 87%, against 2.7M that resolved. That
  # volume is what kept the cluster pressed against AdGuard's 20 qps per-client
  # limit, which on this router applies to the whole LAN at once.
  #
  # Nothing here needs the zone: of the `.lan` lookups CoreDNS logged in 24h,
  # zero were single-label (a real LAN host) and all were already-qualified
  # names with the suffix appended. ndots:5 is left alone deliberately, so no
  # application's resolution behaviour changes -- only the junk disappears.
  #
  # The nameserver has to be spelled out because resolvConf replaces the file
  # wholesale, and pods with dnsPolicy: Default (CoreDNS itself) read it for
  # their upstream. If the router's address ever changes, it changes here too.
  # CoreDNS forwards with `forward . /etc/resolv.conf`, so this file *is* the
  # cluster's upstream list. Until 2026-08-26 it held one entry, which made the
  # router a single point of failure for every name the cluster resolves.
  #
  # On 2026-08-26 between roughly 14:00 and 14:40 that upstream returned
  # SERVFAIL, and CoreDNS relayed it. One 40-minute router hiccup took out the
  # velero BackupStorageLocation, flux's git fetch, image scanning, the Helm
  # index and renovate simultaneously -- seven alerts, one cause. CoreDNS query
  # volume was flat at ~13 qps throughout, so this was not load.
  #
  # Quad9 as the second upstream: CoreDNS's forward policy defaults to `random`,
  # so roughly half of queries take each path and both must be acceptable
  # answers. Quad9 blocks malicious domains and does not block ads -- which is
  # the right shape here, because the cluster resolves infrastructure names
  # (github.com, ghcr.io, B2) where ad filtering does nothing and malware
  # filtering is worth having. Client devices still go through AdGuard directly.
  #
  # This buys redundancy, not caching. Riding out an outage on cached answers
  # would need `cache` and `serve_stale` tuned in the Corefile, which k3s owns
  # via its addon manager and only permits *adding* plugins to -- so that is a
  # larger change than it looks. See the PR for the note.
  kubeletResolvConf = pkgs.writeText "kubelet-resolv.conf" ''
    # No `search` line, on purpose. See nix/modules/k3s.nix.
    nameserver 192.168.8.1
    nameserver 9.9.9.9
    options edns0
  '';

  kubeletDNS = pkgs.writeText "10-dns.conf" ''
    apiVersion: kubelet.config.k8s.io/v1beta1
    kind: KubeletConfiguration
    resolvConf: /etc/rancher/k3s/kubelet-resolv.conf
  '';

  # seccomp for everything that did not ask for it.
  #
  # A container with no seccompProfile runs *unconfined*: every syscall the
  # kernel offers is reachable, including the ones no container image has any
  # business making. 44 of 103 running pods declare a profile -- the four
  # `restricted` namespaces, which are forced to, plus a handful that set it by
  # hand. The other 59 are unconfined, and that set is almost exactly the
  # internet-facing media and web apps.
  #
  # seccompDefault makes RuntimeDefault the floor: containerd's default profile,
  # which blocks roughly 50 syscalls (keyctl, bpf, mount, kexec_load, ptrace of
  # other processes...) and allows the several hundred a normal process uses.
  # An explicit securityContext still wins, so nothing that already declares
  # Unconfined or a custom profile changes.
  #
  # Low risk here specifically: the workloads that genuinely need syscalls
  # outside the default profile -- otbr talking to the Thread dongle, docker
  # dind in the ARC runners -- are privileged, and privileged bypasses the
  # default profile anyway. They are unaffected by definition.
  #
  # Applies at pod creation, so coverage moves as pods churn, not at rebuild.
  kubeletSeccomp = pkgs.writeText "10-seccomp.conf" ''
    apiVersion: kubelet.config.k8s.io/v1beta1
    kind: KubeletConfiguration
    seccompDefault: true
  '';
in
{
  services.k3s = {
    enable = true;
    role = "server";
    package = pkgs.k3s_1_33;
    extraFlags = toString [
      "--disable=traefik"
      # Pin the node to its LAN interface and address.
      #
      # k3s auto-detects both, and auto-detection is fine right up until the
      # node grows another interface. tailscale0 arrives with this change, and
      # docker0, cni0 and flannel.1 were already here; on some future restart
      # the detection could land somewhere other than enp7s0 and the node would
      # re-register on an address nothing routes to.
      #
      # Cheap insurance, and it makes the assumption explicit rather than
      # implicit. If this machine is ever re-cabled, these two lines are what
      # change.
      "--node-ip=192.168.8.226"
      "--flannel-iface=enp7s0"
      # Two StorageClasses both claimed to be the default: k3s's bundled
      # `local-path` and openebs `local-ssd`. With more than one default, the
      # apiserver picks the most recently created — `local-ssd`, by three
      # hours — so any chart that omits storageClassName was already getting
      # local-ssd, silently, by a tiebreak nobody chose.
      #
      # Disabling it rather than un-annotating it, because the annotation
      # cannot be managed from git: k3s re-applies its bundled manifests on
      # every start and would overwrite the change on the next restart.
      #
      # Safe to remove outright: zero PVs and zero PVCs use local-path, and
      # nothing in kubernetes/ references it. Everything here names its class
      # explicitly.
      "--disable=local-storage"
      "--write-kubeconfig-mode=640"
      # Encrypt Secrets at rest in the embedded etcd.
      #
      # Without this every Secret sits in /var/lib/rancher as base64 -- which is
      # not encoding anyone has to break -- and so does every copy of that
      # directory: etcd snapshots, and any full-disk or filesystem-level backup
      # that walks it. SOPS protects them in git and stops there; the cluster
      # decrypts on apply and stores the result in the clear.
      #
      # This is defense in depth, not a hole being closed. Single node, so
      # anyone with disk access already has the kubeconfig next to it. What it
      # buys is that a backup or a snapshot leaving the machine is no longer a
      # secret leaving the machine.
      #
      # THE FLAG ALONE IS NOT ENOUGH. It encrypts writes from here on; the
      # Secrets already in etcd stay plaintext until something rewrites them.
      # After the rebuild:
      #
      #   sudo k3s secrets-encrypt status      # expect: Enabled
      #   sudo k3s secrets-encrypt reencrypt   # rewrites every existing Secret
      #   sudo k3s secrets-encrypt status      # expect: reencrypt_finished
      #
      # The key lives in /var/lib/rancher/k3s/server/cred/encryption-config.json
      # on this same disk, and it is not in any backup this repo configures.
      # Losing it loses every Secret in the cluster.
      "--secrets-encryption"
      "--cluster-init"
      # Raise kubelet maxPods from the default 110. Full-cluster Velero
      # backups burst many concurrent per-volume backup pods and were hitting
      # the 110 ceiling (rejecting volume backups). /24 pod CIDR allows ~256.
      "--kubelet-arg=max-pods=250"
      # Shed load deliberately before the node grinds.
      #
      # The kubelet had no eviction threshold configured at all, which meant
      # there was no point at which the node decided anything. On 2026-08-19
      # claudebox sat welded to its own 8Gi ceiling for the better part of an
      # hour — never over it, so never OOM-killed, oom_kill stayed 0 — and
      # bought every allocation by evicting page cache it read straight back.
      # 61Gi off the disk in one four-minute k3s lifetime. Nothing evicted,
      # because nothing was asked to.
      #
      # A hard threshold gives the kubelet a point at which it reclaims and,
      # failing that, evicts. The soft one with a grace period gives a burst
      # two minutes to finish before anything is killed for it, which is the
      # difference between shedding a build and shedding a database.
      "--kubelet-arg=eviction-hard=memory.available<512Mi,nodefs.available<10%"
      "--kubelet-arg=eviction-soft=memory.available<1Gi"
      "--kubelet-arg=eviction-soft-grace-period=memory.available=2m"
      # Keep a slice of the box out of the scheduler's reach: the kubelet and
      # apiserver under kube-reserved, and sshd, systemd and the shell you fix
      # it from under system-reserved. Without these, allocatable is the whole
      # node and the control plane's own headroom is whatever the workloads
      # happen to leave it.
      #
      # Deliberately modest — 1 CPU and 2Gi in total. Reserving more is better
      # protection and costs schedulable capacity on a 12-core, 30Gi box that
      # is already full. Check that requests still fit before raising it.
      "--kubelet-arg=kube-reserved=cpu=500m,memory=1Gi"
      "--kubelet-arg=system-reserved=cpu=500m,memory=1Gi"
    ];
  };

  # Reserved capacity is an accounting promise to the scheduler. This is the
  # part the kernel enforces.
  #
  # k3s.service and kubepods.slice are siblings under the root cgroup, so by
  # default the control plane competes for CPU and disk with the pods it
  # schedules, on equal weight, and a pod thrashing hard enough can starve it.
  # That is exactly what happened: the apiserver stopped answering itself
  # ("http: Handler timeout" against its own :6443), missed a leader-election
  # lease renewal, logged "leaderelection lost" and exited 1. systemd restarted
  # it 75 times in an afternoon.
  #
  # Weights are relative to the default 100, so 10000 does not reserve
  # anything — it settles who yields when the two are contended, which under
  # normal load is never and under this load is the whole problem.
  systemd.services.k3s.serviceConfig = {
    CPUWeight = 10000;
    IOWeight = 10000;
    # Restarting into a cold cache on a node that is already thrashing is not
    # free: rebuilding the informer caches is itself expensive, which makes
    # the next restart likelier than the last. At the stock 5s that compounds.
    # 30s is long enough for a stampede to drain and short enough that a real
    # crash still recovers unattended.
    RestartSec = lib.mkForce "30s";
  };

  # k3s creates this directory itself and rewrites 00-k3s-defaults.conf on every
  # start, but it leaves other files alone. The `d` rule is only here so a
  # rebuild on a node that has never run k3s does not fail on a missing parent;
  # the perms match what k3s creates.
  #
  # Verify it took effect after rebuilding -- a drop-in that kubelet ignored
  # looks exactly like one it applied:
  #   kubectl get --raw /api/v1/nodes/rechenzentrum/proxy/configz \
  #     | jq '.kubeletconfig | {imageMaximumGCAge, imageGCHighThresholdPercent}'
  systemd.tmpfiles.rules = [
    "d /var/lib/rancher/k3s/agent/etc/kubelet.conf.d 0700 root root -"
    "L+ /var/lib/rancher/k3s/agent/etc/kubelet.conf.d/10-image-gc.conf - - - - ${kubeletImageGC}"
    "L+ /var/lib/rancher/k3s/agent/etc/kubelet.conf.d/10-dns.conf - - - - ${kubeletDNS}"
    "L+ /var/lib/rancher/k3s/agent/etc/kubelet.conf.d/10-seccomp.conf - - - - ${kubeletSeccomp}"
  ];

  # Kept out of kubelet.conf.d: kubelet parses every file in that directory as a
  # KubeletConfiguration, and a resolv.conf sitting there would fail to load.
  environment.etc."rancher/k3s/kubelet-resolv.conf".source = kubeletResolvConf;

  environment.systemPackages = with pkgs; [
    k3s_1_33
    kubectl
    kubernetes-helm
    docker-compose
  ];

  environment.variables = {
    KUBECONFIG = "/etc/rancher/k3s/k3s.yaml";
  };
}
