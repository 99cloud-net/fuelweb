import re
import my_yaml
from model import Environment, Network, Node, Disk, Interface, Cdrom


class ConfigError(Exception):
    pass


def load(stream):
    data = my_yaml.load(stream)

    if not data.has_key('nodes'):
        raise ConfigError, "No nodes defined"

    name = 'default'
    if data.has_key('name'):
        name = data['name']
    environment = Environment(name)

    for network_data in (data.get('networks') or []):
        parse_network(environment, network_data)

    for node_data in data['nodes']:
        parse_node(environment, node_data)

    return environment


def dump(stream):
    raise "Not implemented yet"


def parse_network(environment, data):
    if data.has_key('name'):
        name = data['name']
    elif data.has_key('network'):
        name = data['network']
    else:
        raise ConfigError, "Unnamed network"

    network = Network(name)

    if data.has_key('dhcp_server'):
        network.dhcp_server = data['dhcp_server']

    for existing_network in environment.networks:
        if existing_network.name == network.name:
            raise ConfigError, "Network with given name already exists: %s" % network.name

    environment.networks.append(network)

    return network


def parse_node(environment, data):
    if data.has_key('name'):
        name = data['name']
    elif data.has_key('node'):
        name = data['node']
    else:
        raise ConfigError, "Unnamed node"

    node = Node(name)
    if data.has_key('cpu'):
        node.cpu = data['cpu']
    if data.has_key('memory'):
        node.memory = data['memory']

    if data.has_key('vnc'):
        node.vnc = data['vnc']

    if data.has_key('cdrom'):
        isopath = data['cdrom']
        if not isinstance(isopath, (str,)):
            raise ConfigError, "It must be string containing path to iso image file"

        node.cdrom = Cdrom(isopath)

    if data.has_key('disk'):
        disks_data = data['disk']
        if type(disks_data) != list:
            disks_data = (disks_data,)

        for disk_data in disks_data:
            if type(disk_data) == str:
                try:
                    size = parse_size(disk_data)
                    node.disks.append(Disk(size=size))
                except ValueError:
                    path = disk_data
                    node.disks.append(Disk(path=path))
            elif isinstance(disk_data, dict):
                node.disks.append(Disk(**disk_data))
            else:
                raise ConfigError, "Unknown disk config: %s" % str(disk_data)

    if data.has_key('networks'):
        networks_data = data['networks']
        if type(networks_data) != list:
            networks_data = (networks_data,)

        for network_data in networks_data:
            if type(network_data) == str:
                network = None
                for n in environment.networks:
                    if n.name == network_data:
                        network = n
                        break

                        # Inline networks
                        # if network is None:
                        #     network = parse_network(environment, {'name': network_data})
                        #     self.networks.append(network)

            # TODO: add support for specifying additional network interface params (e.g. mac address)

            if network is None:
                raise ConfigError, "Unknown network %s" % network_data

            node.interfaces.append(Interface(network))

    if data.has_key('boot'):
        boot_data = data['boot']
        if type(boot_data) != list:
            boot_data = list(boot_data)

        for boot in boot_data:
            if not boot in ('disk', 'network', 'cdrom'):
                raise ConfigError, "Unknown boot option: %s" % boot
            node.boot.append(boot)
    else:
        if len(node.disks) > 0:
            node.boot.append('disk')
        if node.cdrom:
            node.boot.append('cdrom')
        if len(node.interfaces) > 0:
            node.boot.append('network')

    for existing_node in environment.nodes:
        if existing_node.name == node.name:
            raise ConfigError, "Node with given name already exists: %s" % node.name

    environment.nodes.append(node)


SIZE_RE = re.compile('^(\d+)\s*(|kb|k|mb|m|gb|g)$')


def parse_size(s):
    m = SIZE_RE.match(s.lower())
    if not m:
        raise ValueError, "Invalid size format: %s" % s

    value = int(m.group(1))
    units = m.group(2)
    if   units in ['k', 'kb']:
        multiplier = 1024
    elif units in ['m', 'mb']:
        multiplier = 1024 ** 2
    elif units in ['g', 'gb']:
        multiplier = 1024 ** 3
    elif units in ['t', 'tb']:
        multiplier = 1024 ** 4
    elif units == '':
        multiplier = 1
    else:
        raise ValueError, "Invalid size format: %s" % units

    return value * multiplier
