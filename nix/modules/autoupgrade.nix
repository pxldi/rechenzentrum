{ pkgs, ... }:

let
  # healthchecks.io pings for the upgrade below: a start ping before it runs,
  # then success or failure from systemd's OnSuccess=/OnFailure=. A morning
  # where the timer never fires, or the node is down, shows as a missed ping
  # on a service that does not live on this node.
  #
  # The key is read from a root-only file, not the Nix store, which every
  # user on the box can read. Created once by hand (scripts/healthchecks-setup.sh
  # prints the command); until it exists every ping is a no-op, so this
  # changes nothing on a host that has not been set up. A ping that fails is
  # ignored: it must never fail or delay the upgrade itself.
  pingKeyFile = "/var/lib/healthchecks/ping-key";
  hcPing = pkgs.writeShellScript "healthchecks-ping" ''
    [ -r ${pingKeyFile} ] || exit 0
    key=$(${pkgs.coreutils}/bin/tr -d '[:space:]' < ${pingKeyFile})
    [ -n "$key" ] || exit 0
    ${pkgs.curl}/bin/curl -fsS -o /dev/null --max-time 10 --retry 3 \
      "https://hc-ping.com/$key/$1" || true
  '';
  pingUnit = suffix: {
    description = "healthchecks.io ping: nixos-upgrade${suffix}";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${hcPing} nixos-upgrade${suffix}";
    };
  };
in

{
  # Merging to main already deploys the cluster (Flux). This makes it deploy
  # the host too: every morning the node fetches the flake from the repo and
  # runs `nixos-rebuild switch` against it. Before this, the OS side of the
  # repo was applied by hand over ssh, which in practice meant "weeks after
  # the PR merged", or never -- the nixos-26.05 bump in #996 sat unapplied
  # while the lock file said otherwise.
  #
  # Every PR now evaluates the full system in CI (infra-check.yml), so a
  # change that cannot build never reaches main. What CI cannot catch is a
  # change that builds and then misbehaves; for that there is the previous
  # generation and `nixos-rebuild switch --rollback`.
  #
  # Guard rails, in order of how much they matter:
  #
  # - allowReboot is off, for now. A kernel or initrd change is applied on
  #   disk but only takes effect after a reboot somebody chooses to do. This
  #   box holds every RWO volume in the cluster, and until the ATX board on
  #   the Comet is wired up nothing can power it back on if a reboot goes
  #   wrong. Once it is: flip allowReboot to true. rebootWindow below is
  #   already set so the reboot happens right after the switch, and only
  #   when the running kernel, initrd or kernel modules actually differ from
  #   the new generation -- a config-only change never reboots.
  # - The fetch is anonymous over https. The repository is public since the
  #   2026-09-12 handover, so the host holds no credential for it at all.
  # - 04:45, not a round number. 03:00 is when the internet goes away every
  #   night (renovate learned that the hard way), velero's daily backup runs
  #   at 04:00 local, and fredy restarts at 05:17. 04:45 is between them and
  #   after the backup has had 45 minutes.
  #
  # The unit still restarts services whose definition changed, including
  # k3s.service if k3s.nix changes. On a single node that bounces every pod
  # for a minute or two. Acceptable at 04:45; keep it in mind when touching
  # k3s.nix.
  system.autoUpgrade = {
    enable = true;
    operation = "switch";
    # `?dir=nix` because the flake sits in a subdirectory of the repo; nix
    # clones the repo and reads the flake from there. `ref=main` pins the
    # branch, and the module adds --refresh so the fetch is not served from
    # the flake cache.
    flake = "git+https://github.com/pxldi/rechenzentrum?dir=nix&ref=main";
    dates = "04:45";
    # Spread nothing: the window above was chosen on purpose.
    randomizedDelaySec = "0";
    allowReboot = false;
    rebootWindow = { lower = "04:45"; upper = "05:10"; };
    persistent = true;
  };

  systemd.services.nixos-upgrade = {
    # "-": a failed start ping must not stop the upgrade from running.
    serviceConfig.ExecStartPre = [ "-${hcPing} nixos-upgrade/start" ];
    unitConfig = {
      OnSuccess = [ "healthchecks-nixos-upgrade-success.service" ];
      OnFailure = [ "healthchecks-nixos-upgrade-fail.service" ];
    };
  };
  systemd.services.healthchecks-nixos-upgrade-success = pingUnit "";
  systemd.services.healthchecks-nixos-upgrade-fail = pingUnit "/fail";

  systemd.tmpfiles.rules = [ "d /var/lib/healthchecks 0700 root root -" ];
}
