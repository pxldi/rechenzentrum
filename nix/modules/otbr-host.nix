{ config, lib, pkgs, ... }:

# Host-level kernel/networking config required by the OpenThread Border
# Router running in k3s for Home Assistant Matter-over-Thread.
#
# OTBR runs with hostNetwork: true and mounts the host's /var/run/dbus.
# The container's mDNS publisher publishes the Thread border router service
# (`_meshcop._udp.local`) by talking to the host's Avahi daemon over D-Bus,
# so HA needs Avahi running on the host. Without it, OTBR starts but never
# advertises itself, and Home Assistant's Thread integration cannot
# discover the border router.
#
# The IPv6/forwarding sysctls let OTBR bridge Thread <-> LAN. Replace
# `lanInterface` if `ip -br a` shows a different name.

let
  lanInterface = "enp7s0";
in
{
  boot.kernel.sysctl = {
    "net.ipv6.conf.all.forwarding" = 1;
    "net.ipv6.conf.${lanInterface}.accept_ra" = 2;
    "net.ipv6.conf.${lanInterface}.accept_ra_rt_info_max_plen" = 64;
    "net.ipv4.ip_forward" = 1;
  };

  # Avahi mDNS daemon — required by OTBR for `_meshcop._udp` announcements.
  services.avahi = {
    enable = true;
    nssmdns4 = true;        # mDNS resolution for IPv4 in nsswitch
    nssmdns6 = true;        # and IPv6
    publish = {
      enable = true;
      addresses = true;
      domain = true;
      hinfo = true;
      userServices = true;
      workstation = true;
    };
    # Without this, Avahi only listens on lo by default
    openFirewall = true;
  };
}
