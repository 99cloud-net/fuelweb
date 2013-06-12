from itertools import chain
from devops.helpers import retry


class EnvironmentException(object):
    pass


class ManagedObject(object):
    def __init__(self):
        super(ManagedObject, self).__init__()
        self._driver = None
        self.name = None

    @property
    def driver(self):
        if self._driver is None:
            raise EnvironmentException, "Object '%s' wasn't built yet" % self.name
        return self._driver

    @driver.setter
    def driver(self, driver):
        self._driver = driver

    @driver.deleter
    def driver(self):
        del self._driver


class Environment(ManagedObject):
    def __init__(self, name):
        super(Environment, self).__init__()

        self.name = name
        self.networks = []
        self.nodes = []
        self.built = False

    @property
    def node(self):
        name2node = {}
        for node in self.nodes:
            name2node[node.name] = node
        return name2node

    @property
    def network(self):
        name2network = {}
        for network in self.networks:
            name2network[network.name] = network
        return name2network


class Network(ManagedObject):
    def __init__(self, name, dhcp_server=False, pxe=False,
                 reserve_static=True, forward='nat'):
        super(Network, self).__init__()

        self.name = name
        self.dhcp_server = dhcp_server
        self.reserve_static=reserve_static
        self.interfaces = []
        self.pxe = pxe
        self.forward = forward
        self.environment = None

    def start(self):
        self.driver.start_network(self)

    def stop(self):
        self.driver.stop_network(self)

class Node(ManagedObject):
    def __init__(self, name, cpu=1, memory=512, arch='x86_64', vnc=False,
                 metadata=None):
        super(Node, self).__init__()

        self.name = name
        if metadata is None:
            self.metadata = {}
        else:
            self.metadata = metadata
        self.cpu = cpu
        self.memory = memory
        self.arch = arch
        self.vnc = vnc
        self.interfaces = []
        self.bridged_interfaces = []
        self.disks = []
        self.boot = []
        self.cdrom = None
        self.environment = None

    def start(self):
        self.driver.start_node(self)

    def stop(self):
        self.driver.stop_node(self)

    def reset(self):
        self.driver.reset_node(self)

    def reboot(self):
        self.driver.reboot_node(self)

    def shutdown(self):
        self.driver.shutdown_node(self)

    def suspend(self):
        self.driver.suspend_node(self)

    def resume(self):
        self.driver.resume_node(self)

    @property
    def snapshots(self):
        return self.driver.get_node_snapshots(self)

    def has_snapshot(self, snapshot_name):
        return snapshot_name in self.snapshots

    def _delete_and_create(self, name):
        #noinspection PyBroadException
        try:
            self.delete_snapshot(name)
        except:
            pass
        return self.driver.create_snapshot(self, name=name)

    def save_snapshot(self, name=None, force=False):
        "Create node state snapshot. Returns snapshot name"
        if name and force and self.has_snapshot(name):
            return retry(10, self._delete_and_create, name=name)
        return self.driver.create_snapshot(self, name=name)

    def restore_snapshot(self, snapshot_name=None):
        "Revert node state to given snapshot. If no snapshot name given, revert to current snapshot."
        self.driver.revert_snapshot(self, snapshot_name)

    def delete_snapshot(self, snapshot_name=None):
        "Delete snapshot. If no snapshot name given, delete current snapshot."
        self.driver.delete_snapshot(self, snapshot_name)

    def send_keys(self, keys):
        self.driver.send_keys_to_node(self, keys)

    @property
    def ip_addresses(self):
        addresses = []
        for interface in self.interfaces:
            addresses += interface.ip_addresses
        return addresses

    @property
    def ip_address(self):
        x = self.ip_addresses
        if len(x) == 0:
            return None
        return x[0]

    @property
    def ip_address_by_network(self):
        name2ip_addresses = {}
        for interface in self.interfaces:
            if len(interface.ip_addresses) == 0:
                name2ip_addresses[interface.network.name] = None
            else:
                name2ip_addresses[interface.network.name] = interface.ip_addresses[0]
        return name2ip_addresses

    @ManagedObject.driver.setter
    def driver(self, driver):
        ManagedObject.driver.fset(self, driver)
        for interface in self.interfaces:
            interface.driver = driver


class Cdrom(object):
    def __init__(self, isopath=None, bus='ide'):
        self.isopath = isopath
        self.bus = bus


class Disk(object):
    def __init__(self, size=None, path=None, format='qcow2', bus='virtio',
                 base_image=None):
        self.size = size
        self.format = format
        self.bus = bus
        self.path = path
        # Either copy or use "backing file" feature
        self.base_image = base_image


class BridgedInterface(ManagedObject):
    def __init__(self, bridge, type='virtio'):
        super(BridgedInterface, self).__init__()
        self.bridge = bridge
        self.type = type

class Interface(ManagedObject):
    def __init__(self, network, ip_addresses=None, type='virtio'):
        super(Interface, self).__init__()
        if not ip_addresses: ip_addresses = []
        self.node = None
        self.network = network
        if not isinstance(ip_addresses, (list, tuple)):
            ip_addresses = (ip_addresses,)
        self._ip_addresses = ip_addresses
        self.mac_address = None
        self.type = type
        self.target_dev = None

    @property
    def ip_addresses(self):
        return self._ip_addresses

    @ip_addresses.setter
    def ip_addresses(self, value):
        if not isinstance(value, (list, tuple)):
            value = (value,)
        self._ip_addresses = value
