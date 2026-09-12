{ config, pkgs, ... }:
{
  powerManagement.cpuFreqGovernor = "schedutil";

  #environment.etc."fancontrol".source = ./fancontrol.conf;

  #systemd.services.fancontrol = {
  #  description = "Fan speed regulator";
  #  wantedBy = [ "multi-user.target" ];
  #  serviceConfig = {
  #    ExecStart = "${pkgs.lm_sensors}/bin/fancontrol /etc/fancontrol";
  #    Restart = "on-failure";
  #  };
  #};
	
  systemd.services.hdparm-spindown = {
    description = "HDD power management - Deactivated APM";
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = pkgs.writeShellScript "hdparm-spindown" ''
        # -B 254: Deaktiviert APM (kein aggressives Parken)
        # -S [WERT]: Steuert nur noch den Standby-Timeout
        ${pkgs.hdparm}/bin/hdparm -B 254 -S 244 /dev/disk/by-uuid/a00c073a-8d62-4da2-b5d1-b67b3f485aff
        ${pkgs.hdparm}/bin/hdparm -B 254 -S 244 /dev/disk/by-uuid/13864c23-ea60-441c-a9be-358f3a1042b4
      '';
    };
  };

  environment.systemPackages = with pkgs; [ lm_sensors hdparm ];
}
