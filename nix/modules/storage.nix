{ config, pkgs, ... }:

{
  # HDD mount options for quiet mode and reduced wear
  # noatime: Don't update file access times → less disk writes → quieter
  # nofail: Don't fail boot if HDD is unavailable
  fileSystems."/mnt/hdd1" = {
    options = [ "nofail" "noatime" "nodiratime" ];
  };

  fileSystems."/mnt/hdd2" = {
    options = [ "nofail" "noatime" "nodiratime" ];
  };
}
