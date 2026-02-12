{ config, pkgs, ... }:

{
  users.users.pxldi = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "docker" ];
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK/pgT6dODgD6smX51WEvvonato0LePX/NpPOv2S1dYQ lsl@DESKTOP-E9I9BHO"
    ];
  };

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      PermitRootLogin = "no";
      PubkeyAuthentication = true;
    };
  };

  security.sudo.wheelNeedsPassword = false;
}
