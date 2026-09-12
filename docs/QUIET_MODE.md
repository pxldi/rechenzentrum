# Host power settings

`nix/modules/quiet.nix` configures:

- CPU governor: `schedutil`.
- `hdparm-spindown.service`: `hdparm -B 254 -S 244` for both configured HDD UUIDs.
- Installed tools: `lm_sensors` and `hdparm`.

The fancontrol configuration and service are **commented out**. This repository
does not currently enable fan control; configure and test it for the actual
hardware before enabling it in Nix.

`nix/modules/storage.nix` sets `nofail`, `noatime` and `nodiratime` on both HDD mounts.

```sh
sensors
systemctl status hdparm-spindown.service
journalctl -u hdparm-spindown.service -n 30
findmnt /mnt/hdd1 /mnt/hdd2
```

Use the stable device paths from `quiet.nix` for disk checks. Media scans,
application writes and backups can keep drives active.
