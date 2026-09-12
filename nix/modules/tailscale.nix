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

  # tailscale0 is deliberately NOT added to networking.firewall.trustedInterfaces.
  #
  # Trusting it would expose every listening port on the node to everything on
  # the tailnet, including etcd on 2379 and the kubelet on 10250. The two things
  # actually wanted over the tailnet -- sshd on 48222 and the API on 6443 -- are
  # already open, so trusting the interface would buy nothing and cost the
  # principle.
}
