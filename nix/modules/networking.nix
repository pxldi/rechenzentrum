{ config, pkgs, ... }:

{
  networking = {
    networkmanager.enable = true;
    
    firewall = {
      enable = true;
      allowedTCPPorts = [
        # 22 is deliberately absent: sshd listens on 48222 (see base.nix) and
        # services.openssh.openFirewall opens that port itself. Nothing has
        # listened on 22 since the port was changed, so the rule allowed
        # traffic to a closed port and implied an sshd that is not there.
        80    # HTTP
        443   # HTTPS
        6443  # K3s API server
      ];
      allowedUDPPorts = [
        8472  # Flannel VXLAN
      ];
      # Trust K3s interfaces
      trustedInterfaces = [ "cni0" "flannel.1" ];
    };
  };

  # Hardware watchdog. The board exposes an SP5100 TCO timer at /dev/watchdog0
  # and, until this, nothing was petting it -- systemd reported
  # RuntimeWatchdogUSec=0, so the timer sat there doing nothing.
  #
  # With it armed, systemd pets the timer every runtimeTime/2. If the *kernel*
  # stops scheduling -- a hard hang, not a crash -- the chipset resets the
  # machine on its own. That covers the one failure a KVM's keyboard and screen
  # cannot: a box that is up, drawing power, and completely unresponsive.
  # kernel.panic in configuration.nix handles the panic case faster, and does
  # not depend on this timer being armed. The two are deliberately redundant.
  #
  # 3 minutes, deliberately long, and the number is chosen against the eviction
  # settings in k3s.nix rather than picked for feel. The soft threshold there
  # gives a memory burst a 2 minute grace period before anything is killed. A
  # watchdog shorter than that would reset the node while the kubelet was still
  # doing its job -- turning a recoverable squeeze into a hard reset of six
  # databases. 3 minutes lets eviction finish first and only fires when nothing
  # is running at all.
  #
  # The cost of being generous is three minutes of downtime on a genuine hang,
  # which for this machine is nothing. The cost of being aggressive is resets
  # that look like hardware faults and are not. This node has already had one
  # thrashing incident where it was unresponsive for minutes and recovered.
  #
  # systemd.settings.Manager.RuntimeWatchdogSec, not the older
  # systemd.watchdog.runtimeTime: nixpkgs renamed it, and the old name still
  # works but warns on every evaluation. Caught by evaluating the config rather
  # than by reading the option docs.
  systemd.settings.Manager.RuntimeWatchdogSec = "3min";
}
