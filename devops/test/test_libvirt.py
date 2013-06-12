import unittest
import re
from ipaddr import IPv4Network
from devops import xml
from devops.model import Network, Node, Disk, Cdrom
from devops.network import IPv4Address, IPv4Network
from devops.driver.libvirt import Libvirt, LibvirtXMLBuilder, DeploymentSpec


class TestLibvirtXMLBuilder(unittest.TestCase):
    node_spec = DeploymentSpec()
    node_spec.arch = 'x86_64'
    node_spec.os_type = 'hvm'
    node_spec.hypervisor = 'kvm'
    node_spec.emulator = '/usr/bin/kvm'

    def setUp(self):
        self.builder = LibvirtXMLBuilder()

    def test_network(self):
        network = Network('net1')
        network.id = 'net1'
        doc_xml = self.builder.build_network_xml(network)

        doc = xml.parse_string(doc_xml)

        self.assertIsNotNone(doc)
        self.assertEqual('network', doc.tag)

        e = doc.find('name')
        self.assertIsNotNone(e)
        self.assertEqual('net1', e.text)

    def test_network_ip(self):
        network = Network('net1')
        network.id = 'net1'
        network.ip_addresses = IPv4Network('10.0.0.0/24')
        doc_xml = self.builder.build_network_xml(network)

        doc = xml.parse_string(doc_xml)

        ip_element = doc.find('ip')
        self.assertIsNotNone(ip_element)
        self.assertIsNotNone(ip_element['address'])
        self.assertIsNotNone(ip_element['prefix'])

        self.assertValidIp(ip_element['address'])

    def test_network_dhcp(self):
        network = Network('net1')
        network.id = 'net1'
        network.ip_addresses = IPv4Network('10.0.0.0/24')
        network.dhcp_server = True

        doc_xml = self.builder.build_network_xml(network)

        doc = xml.parse_string(doc_xml)

        dhcp_element = doc.find('ip/dhcp')

        self.assertIsNotNone(dhcp_element)

        range_element = dhcp_element.find('range')
        self.assertIsNotNone(range_element)

        self.assertIsNotNone(range_element['start'])
        self.assertIsNotNone(range_element['end'])

        self.assertValidIp(range_element['start'])
        self.assertValidIp(range_element['end'])

    def test_network_dhcp_with_custom_dynamic_ip_range(self):
        network = Network('net1')
        network.id = 'net1'
        network.ip_addresses = IPv4Network('10.0.0.0/24')
        network.dhcp_server = True
        network.dhcp_dynamic_address_start = IPv4Address('10.0.0.100')
        network.dhcp_dynamic_address_end = IPv4Address('10.0.0.200')

        doc_xml = self.builder.build_network_xml(network)

        doc = xml.parse_string(doc_xml)

        range_element = doc.find('ip/dhcp/range')
        self.assertEquals('10.0.0.100', range_element['start'])
        self.assertEquals('10.0.0.200', range_element['end'])

    def test_node_memory(self):
        node = Node('node1')
        node.id = node.name
        node.memory = 123

        doc_xml = self.builder.build_node_xml(node, self.node_spec)

        doc = xml.parse_string(doc_xml)

        memory_element = doc.find('memory')
        self.assertIsNotNone(memory_element)
        self.assertEqual('KiB', memory_element['unit'])
        self.assertEqual(str(123 * 1024), memory_element.text)

    def test_cdrom_disk(self):
        node = Node('node1')
        node.id = node.name
        node.cdrom = Cdrom(isopath='foo.iso')

        doc_xml = self.builder.build_node_xml(node, self.node_spec)

        doc = xml.parse_string(doc_xml)

        cdrom_element = doc.find(
            'devices/disk[@type="file" and @device="cdrom"]')
        self.assertIsNotNone(cdrom_element)

        cdrom_driver_element = cdrom_element.find('driver')
        self.assertIsNotNone(cdrom_driver_element)
        self.assertEqual('qemu', cdrom_driver_element['name'])
        self.assertEqual('raw', cdrom_driver_element['type'])

        cdrom_source_element = cdrom_element.find('source')
        self.assertIsNotNone(cdrom_source_element)
        self.assertEqual('foo.iso', cdrom_source_element['file'])

    IPV4_RE = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')

    def assertValidIp(self, s):
        self.assertIsNotNone(
            self.IPV4_RE.match(s),
            "'%s' is not a valid IPv4 address" % s)

if __name__ == '__main__':
    unittest.main()
