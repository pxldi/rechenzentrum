{ ... }:

{
  # A private network for the node, the workstation, the laptop and the KVM.
  #
  # The point is not convenience, it is closing 48222. Right now sshd is one of
  # exactly two things reachable from the internet, and while a pubkey-only,
  # root-disabled sshd on a non-standard port is a defensible thing to expose, a
  # closed port is strictly better than a well-configured open one. Once this is
  # up and proven, the forward can be deleted on the router and the node's only
  # inbound path from the internet is 443 to Traefik.
  #
  # It also gives the GL.iNet Comet KVM somewhere to live that is not the
  # internet and not a vendor's cloud relay. That device emulates a keyboard
  # attached to this machine; it should never be port-forwarded, and with a
  # tailnet it does not have to be.
  services.tailscale = {
    enable = true;
    # Opens UDP 41641 for direct connections. Without it traffic still works but
    # falls back to a DERP relay -- slower, and it routes through Tailscale's
    # infrastructure rather than point to point.
    openFirewall = true;
    # "client" is the right level here: it lets this node use an exit node or
    # accept subnet routes if that is ever wanted, without advertising itself as
    # a router. "server" would enable IP forwarding, which this node does not
    # need and which interacts with flannel in ways not worth inviting.
    useRoutingFeatures = "client";
  };

  # Split DNS for the tailnet. The house-only routes (the `internal-only`
  # middleware) accept the LAN and the tailnet, but a tailnet device away from
  # home asked public DNS for *.pxldi.de, got the house's public address and
  # arrived over the internet with its mobile address, so every one of those
  # routes answered 403 even with Tailscale on. At home AdGuard rewrites the
  # names to the node; nothing did the same for the tailnet, and the router
  # that runs AdGuard is not on it.
  #
  # This answers *.pxldi.de with the node's tailnet address, which Traefik
  # listens on (externalIPs in its HelmRelease), so the request travels inside
  # the tailnet and Traefik sees the client's tailnet address. It answers
  # nothing else. The tailnet uses it through a split-DNS nameserver entry for
  # pxldi.de in the Tailscale admin console, which is not in this repository.
  services.dnsmasq = {
    enable = true;
    # The node keeps its own resolver; this server is for tailnet clients only.
    resolveLocalQueries = false;
    settings = {
      interface = "tailscale0";
      except-interface = "lo";
      # tailscale0 comes up after dnsmasq may have started.
      bind-dynamic = true;
      no-resolv = true;
      no-hosts = true;
      address = "/pxldi.de/100.122.211.109";
    };
  };

  networking.firewall.interfaces.tailscale0 = {
    allowedUDPPorts = [ 53 ];
    allowedTCPPorts = [ 53 ];
  };

  # tailscale0 is deliberately NOT added to networking.firewall.trustedInterfaces.
  #
  # Trusting it would expose every listening port on the node to everything on
  # the tailnet, including etcd on 2379 and the kubelet on 10250. The two things
  # actually wanted over the tailnet -- sshd on 48222 and the API on 6443 -- are
  # already open, so trusting the interface would buy nothing and cost the
  # principle. DNS on 53 is opened by name above for the same reason.
}
