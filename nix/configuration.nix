{ config, pkgs, ... }:

{
  imports = [
    ./hardware-configuration.nix
    ./modules/base.nix
    ./modules/networking.nix
    ./modules/tailscale.nix
    ./modules/storage.nix
    ./modules/k3s.nix
    ./modules/backup.nix
    ./modules/quiet.nix
    ./modules/otbr-host.nix
    ./modules/autoupgrade.nix
  ];

  boot.kernel.sysctl = {
    # A panicking kernel hangs forever by default (kernel.panic = 0), which is
    # the worst outcome for a machine nobody is standing next to: powered on,
    # dead, and holding its RWO volumes. Reboot 10 seconds in instead.
    #
    # The watchdog in networking.nix covers the same case, but only after its
    # full 3 minute timeout and only if the SP5100 timer is actually armed.
    # This is the cheaper, faster path and depends on nothing.
    "kernel.panic" = 10;

    "fs.inotify.max_user_watches" = 1048576;
    "fs.inotify.max_user_instances" = 8192;
  };

  boot.supportedFilesystems = [ "ntfs" ];

  services.udev.extraRules = ''
    ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TOSHIBA_EXT", RUN+="${pkgs.systemd}/bin/systemd-mount --no-block --collect --options=rw,uid=1000,gid=100  $devnode /mnt/usb-backup"
    ACTION=="remove", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="TOSHIBA_EXT", RUN+="${pkgs.systemd}/bin/systemd-umount /mnt/usb-backup"
  '';

  systemd.tmpfiles.rules = [
    "d /mnt/usb-backup 0755 root root -"
    # Empty anchor dir on the nvme filesystem. Homepage bind-mounts this to read
    # free space via statfs, which reports the whole filesystem — so it no longer
    # needs a hostPath on /var (which exposes /var/lib/rancher/k3s/server/token).
    "d /var/lib/homepage-df 0755 root root -"
  ];

  networking.hostName = "rechenzentrum";

  boot.loader = {
    systemd-boot.enable = true;
    efi.canTouchEfiVariables = true;
  };

  nix = {
    settings = {
      experimental-features = [ "nix-command" "flakes" ];
      auto-optimise-store = true;
    };
    gc = {
      automatic = true;
      dates = "weekly";
      options = "--delete-older-than 30d";
    };
  };

  time.timeZone = "Europe/Berlin";

  i18n.defaultLocale = "en_US.UTF-8";
  console = {
    font = "Lat2-Terminus16";
    keyMap = "us";
  };

  nixpkgs.config.allowUnfree = true;

  environment.systemPackages = with pkgs; [
    vim
    git
    htop
    curl
    wget
  ];

  hardware.graphics.enable = true;
  hardware.graphics.extraPackages = with pkgs; [
    libvdpau-va-gl
    libva-vdpau-driver
  ];

  system.stateVersion = "24.11";
}
