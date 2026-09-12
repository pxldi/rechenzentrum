# Quiet Mode

Fan control and HDD spin-down for quieter operation. The declarative half lives in `nix/modules/quiet.nix` (hdparm spin-down timer, lm_sensors, fancontrol service); the fan curve itself cannot be declared in Nix and needs a **one-time interactive setup after installing on new hardware**.

## One-time setup

```bash
# 1. Detect temperature and fan sensors
sudo sensors-detect --auto

# 2. Generate the fan curve interactively
sudo pwmconfig
```

`pwmconfig` walks you through selecting the PWM fans, probing their minimum/maximum values, and setting temperature thresholds. Rough curve that works well on the Ryzen 5 5600G: minimum below 40 °C, ramping through 40–70 °C, maximum above 70 °C.

```bash
# 3. Enable and start fan control
sudo systemctl enable --now fancontrol
```

## HDD spin-down

Configured declaratively in `nix/modules/quiet.nix` — a systemd service applies `hdparm -B 254 -S 244` (spin down after 2 hours idle) to both HDDs, addressed by UUID. No manual setup needed; to change the timeout, edit the `-S` value there (see `man hdparm` for the encoding) and rebuild.

The HDD mounts use `noatime,nodiratime` so reads don't cause writes that keep the disks awake.

## Verification

```bash
# Real-time sensor readings
watch -n 2 sensors

# Fan control status / logs
sudo systemctl status fancontrol
sudo journalctl -u fancontrol -n 50

# HDD power state ("active/idle" or "standby"); use the UUIDs from quiet.nix
sudo hdparm -C /dev/sda /dev/sdb

# Force a spin-down to test (disk wakes on next access)
sudo hdparm -y /dev/sda
```

## Troubleshooting

**Fans don't respond to the config**

1. Check BIOS: fan mode may need to be "PWM" / "Auto".
2. Verify you picked the right PWM device in `pwmconfig`.
3. Inspect `/etc/fancontrol` — sensor paths can shift between kernels; re-run `pwmconfig` if they have.

**HDDs keep spinning**

```bash
# See what's touching the drives
sudo iotop -oP

# Confirm noatime is active
mount | grep hdd
```

Usual suspects: Nextcloud cron, media scans (Sonarr/Radarr/Jellyfin), backup runs, or anything with a PVC on the HDD classes.
