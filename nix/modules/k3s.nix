{ config, pkgs, ... }:

{
  services.k3s = {
    enable = true;
    role = "server";
    extraFlags = toString [
      "--disable=traefik"
      "--write-kubeconfig-mode=644"
      "--cluster-init"
    ];
  };

  environment.systemPackages = with pkgs; [
    k3s
    kubectl
    kubernetes-helm
  ];

  environment.variables = {
    KUBECONFIG = "/etc/rancher/k3s/k3s.yaml";
  };
}
