{ ... }:

# The cluster's second DNS upstream, encrypted.
#
# CoreDNS forwards to the nameservers in kubeletResolvConf (k3s.nix): the
# router's AdGuard and, as a fallback for when the router fails, Quad9. Since
# 2026-11-27 the node reaches the internet through a Wi-Fi network run by
# someone else, and AdGuard asks its own upstreams over DNS-over-HTTPS. A
# plain `nameserver 9.9.9.9` would still send about half of the cluster's
# lookups across that network in clear text, because CoreDNS picks an
# upstream at random.
#
# So the fallback is this unbound, which forwards everything to Quad9 over
# DNS-over-TLS (port 853) and caches. It keeps what the plain entry gave:
# Quad9's malware filtering, no ad filtering, and no dependency on the router.
#
# It listens only on cni0's address, the pod network's gateway on this node.
# cni0 is a trusted interface (networking.nix), so pods reach it without a
# firewall rule, and nothing on the LAN or the tailnet can. cni0 appears only
# once k3s has started, hence ip-freebind.
{
  services.unbound = {
    enable = true;
    # The node itself keeps resolving through NetworkManager and the router.
    resolveLocalQueries = false;
    settings = {
      server = {
        interface = [ "10.42.0.1" ];
        ip-freebind = true;
        access-control = [ "10.42.0.0/16 allow" ];
        do-ip6 = false;
        tls-cert-bundle = "/etc/ssl/certs/ca-certificates.crt";
        # Serve a stale answer for up to a day while Quad9 cannot be reached,
        # the riding-out that the plain entry never gave.
        serve-expired = true;
        serve-expired-ttl = 86400;
        qname-minimisation = true;
        hide-identity = true;
        hide-version = true;
      };
      forward-zone = [
        {
          name = ".";
          forward-tls-upstream = true;
          forward-addr = [
            "9.9.9.9@853#dns.quad9.net"
            "149.112.112.112@853#dns.quad9.net"
          ];
        }
      ];
    };
  };
}
