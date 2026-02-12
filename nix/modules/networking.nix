{ config, pkgs, ... }:

{
  networking = {
    networkmanager.enable = true;
    
    firewall = {
      enable = true;
      allowedTCPPorts = [ 
        22    # SSH
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
}
