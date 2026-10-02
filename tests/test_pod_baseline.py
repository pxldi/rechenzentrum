import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/pod_baseline.py'
spec = importlib.util.spec_from_file_location('pod_baseline', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
EXCEPTIONS = module.load_exceptions()


def pod(namespace='media', **spec):
    spec.setdefault('containers', [{'name': 'app', 'image': 'app:1'}])
    return {'kind': 'Pod', 'metadata': {'name': 'p', 'namespace': namespace}, 'spec': spec}


def container(**sc):
    return [{'name': 'app', 'image': 'app:1', 'securityContext': sc}]


class PodBaseline(unittest.TestCase):
    def check(self, doc):
        return module.check_documents([doc], EXCEPTIONS)

    def test_plain_pod_passes(self):
        self.assertEqual(self.check(pod()), [])

    def test_privileged_refused_outside_exception(self):
        self.assertTrue(self.check(pod(containers=container(privileged=True))))

    def test_privileged_allowed_for_device_plugins(self):
        self.assertEqual(self.check(pod('device-plugins', containers=container(privileged=True))), [])

    def test_privileged_refused_for_retired_runner_namespace(self):
        # arc-runners lost its dind exception with the ARC removal on 2026-10-02.
        self.assertTrue(self.check(pod('arc-runners', containers=container(privileged=True))))

    def test_exception_is_per_check(self):
        # observability may mount the host for node-exporter, but not run privileged.
        self.assertEqual(self.check(pod('observability', volumes=[{'name': 'root', 'hostPath': {'path': '/'}}])), [])
        self.assertTrue(self.check(pod('observability', containers=container(privileged=True))))

    def test_hostpath_refused(self):
        self.assertTrue(self.check(pod(volumes=[{'name': 'root', 'hostPath': {'path': '/'}}])))

    def test_host_namespaces_refused(self):
        for field in ('hostNetwork', 'hostPID', 'hostIPC'):
            self.assertTrue(self.check(pod(**{field: True})), field)

    def test_host_port_refused(self):
        containers = [{'name': 'app', 'image': 'app:1', 'ports': [{'containerPort': 80, 'hostPort': 80}]}]
        self.assertTrue(self.check(pod(containers=containers)))

    def test_default_capabilities_allowed_others_refused(self):
        self.assertEqual(self.check(pod(containers=container(capabilities={'add': ['CHOWN', 'NET_BIND_SERVICE']}))), [])
        self.assertTrue(self.check(pod(containers=container(capabilities={'add': ['SYS_ADMIN']}))))
        self.assertEqual(self.check(pod('slskd', containers=container(capabilities={'add': ['NET_ADMIN']}))), [])

    def test_ephemeral_and_init_containers_checked(self):
        debug = [{'name': 'debug', 'image': 'busybox:1', 'securityContext': {'privileged': True}}]
        self.assertTrue(self.check(pod(ephemeralContainers=debug)))
        self.assertTrue(self.check(pod(initContainers=debug)))

    def test_unconfined_seccomp_refused_everywhere(self):
        self.assertTrue(self.check(pod('home-assistant', securityContext={'seccompProfile': {'type': 'Unconfined'}})))

    def test_templates_checked(self):
        deploy = {'kind': 'Deployment', 'metadata': {'name': 'd', 'namespace': 'media'},
                  'spec': {'template': {'spec': {'containers': [], 'hostNetwork': True}}}}
        self.assertTrue(self.check(deploy))

    def test_excluded_system_namespaces(self):
        self.assertEqual(self.check(pod('kube-system', hostNetwork=True)), [])


if __name__ == '__main__':
    unittest.main()
