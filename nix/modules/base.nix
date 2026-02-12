{ config, pkgs, ... }:

{
  users.users.pxldi = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "docker" ];
    openssh.authorizedKeys.keys = [
      # TODO: Add SSH public key here after generation
      # "ssh-ed25519 AAAAC3... your-key-here"
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
