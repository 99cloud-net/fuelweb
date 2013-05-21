# -*- coding: utf-8 -*-

import re
import uuid
import string
import math
from datetime import datetime
from random import choice
from copy import deepcopy

import web
import netaddr
from sqlalchemy import Column, UniqueConstraint, Table
from sqlalchemy import Integer, String, Unicode, Text, Boolean
from sqlalchemy import ForeignKey, Enum, DateTime
from sqlalchemy import create_engine
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base

from nailgun.logger import logger
from nailgun.db import orm
from nailgun.volumes.manager import VolumeManager
from nailgun.api.fields import JSON
from nailgun.settings import settings

Base = declarative_base()


class Release(Base):
    __tablename__ = 'releases'
    __table_args__ = (
        UniqueConstraint('name', 'version'),
    )
    id = Column(Integer, primary_key=True)
    name = Column(Unicode(100), nullable=False)
    version = Column(String(30), nullable=False)
    description = Column(Unicode)
    networks_metadata = Column(JSON, default=[])
    attributes_metadata = Column(JSON, default={})
    volumes_metadata = Column(JSON, default={})
    clusters = relationship("Cluster", backref="release")


class ClusterChanges(Base):
    __tablename__ = 'cluster_changes'
    POSSIBLE_CHANGES = (
        'networks',
        'attributes',
        'disks'
    )
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id'))
    node_id = Column(Integer, ForeignKey('nodes.id', ondelete='CASCADE'))
    name = Column(
        Enum(*POSSIBLE_CHANGES, name='possible_changes'),
        nullable=False
    )


class Cluster(Base):
    __tablename__ = 'clusters'
    TYPES = ('compute', 'storage', 'both')
    MODES = ('singlenode', 'multinode', 'ha')
    STATUSES = ('new', 'deployment', 'operational', 'error', 'remove')
    NET_MANAGERS = ('FlatDHCPManager', 'VlanManager')
    id = Column(Integer, primary_key=True)
    type = Column(
        Enum(*TYPES, name='cluster_type'),
        nullable=False,
        default='compute'
    )
    mode = Column(
        Enum(*MODES, name='cluster_mode'),
        nullable=False,
        default='multinode'
    )
    status = Column(
        Enum(*STATUSES, name='cluster_status'),
        nullable=False,
        default='new'
    )
    net_manager = Column(
        Enum(*NET_MANAGERS, name='cluster_net_manager'),
        nullable=False,
        default='FlatDHCPManager'
    )
    name = Column(Unicode(50), unique=True, nullable=False)
    release_id = Column(Integer, ForeignKey('releases.id'), nullable=False)
    nodes = relationship("Node", backref="cluster", cascade="delete")
    tasks = relationship("Task", backref="cluster", cascade="delete")
    attributes = relationship("Attributes", uselist=False,
                              backref="cluster", cascade="delete")
    changes = relationship("ClusterChanges", backref="cluster",
                           cascade="delete")
    # We must keep all notifications even if cluster is removed.
    # It is because we want user to be able to see
    # the notification history so that is why we don't use
    # cascade="delete" in this relationship
    # During cluster deletion sqlalchemy engine will set null
    # into cluster foreign key column of notification entity
    notifications = relationship("Notification", backref="cluster")
    network_groups = relationship("NetworkGroup", backref="cluster",
                                  cascade="delete")

    @classmethod
    def validate(cls, data):
        d = cls.validate_json(data)
        if d.get("name"):
            if orm().query(Cluster).filter_by(
                name=d["name"]
            ).first():
                c = web.webapi.conflict
                c.message = "Environment with this name already exists"
                raise c()
        if d.get("release"):
            release = orm().query(Release).get(d.get("release"))
            if not release:
                raise web.webapi.badrequest(message="Invalid release id")
        return d

    def add_pending_changes(self, changes_type, node_id=None):
        ex_chs = orm().query(ClusterChanges).filter_by(
            cluster=self,
            name=changes_type
        )
        if not node_id:
            ex_chs = ex_chs.first()
        else:
            ex_chs = ex_chs.filter_by(node_id=node_id).first()
        # do nothing if changes with the same name already pending
        if ex_chs:
            return
        ch = ClusterChanges(
            cluster_id=self.id,
            name=changes_type
        )
        if node_id:
            ch.node_id = node_id
        orm().add(ch)
        orm().commit()

    def clear_pending_changes(self, node_id=None):
        chs = orm().query(ClusterChanges).filter_by(
            cluster_id=self.id
        )
        if node_id:
            chs = chs.filter_by(node_id=node_id)
        map(orm().delete, chs.all())
        orm().commit()


class Node(Base):
    __tablename__ = 'nodes'
    NODE_STATUSES = (
        'ready',
        'discover',
        'provisioning',
        'provisioned',
        'deploying',
        'error'
    )
    NODE_ROLES = (
        'controller',
        'compute',
        'cinder',
    )
    NODE_ERRORS = (
        'deploy',
        'provision',
        'deletion'
    )
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id'))
    name = Column(Unicode(100))
    status = Column(
        Enum(*NODE_STATUSES, name='node_status'),
        nullable=False,
        default='discover'
    )
    meta = Column(JSON, default={})
    mac = Column(String(17), nullable=False, unique=True)
    ip = Column(String(15))
    fqdn = Column(String(255))
    manufacturer = Column(Unicode(50))
    platform_name = Column(String(150))
    progress = Column(Integer, default=0)
    os_platform = Column(String(150))
    role = Column(Enum(*NODE_ROLES, name='node_role'))
    pending_addition = Column(Boolean, default=False)
    pending_deletion = Column(Boolean, default=False)
    changes = relationship("ClusterChanges", backref="node")
    error_type = Column(Enum(*NODE_ERRORS, name='node_error_type'))
    error_msg = Column(String(255))
    timestamp = Column(DateTime, nullable=False)
    online = Column(Boolean, default=True)
    attributes = relationship("NodeAttributes",
                              backref=backref("node"),
                              uselist=False)
    interfaces = relationship("NodeNICInterface", backref="node")

    @property
    def network_data(self):
        # It is required for integration tests; to get info about nets
        #   which must be created on target node
        from nailgun.network import manager as netmanager
        return netmanager.get_node_networks(self.id)

    @property
    def volume_manager(self):
        return VolumeManager(self)

    @property
    def needs_reprovision(self):
        return self.status == 'error' and self.error_type == 'provision'

    @property
    def needs_redeploy(self):
        cases = [
            self.status == 'error' and self.error_type == 'deploy',
            self.cluster is not None and list(self.cluster.changes) != []
        ]
        return any(cases)

    @property
    def needs_redeletion(self):
        return self.status == 'error' and self.error_type == 'deletion'


class NodeAttributes(Base):
    __tablename__ = 'node_attributes'
    id = Column(Integer, primary_key=True)
    node_id = Column(Integer, ForeignKey('nodes.id'))
    volumes = Column(JSON, default=[])


class IPAddr(Base):
    __tablename__ = 'ip_addrs'
    id = Column(Integer, primary_key=True)
    network = Column(Integer, ForeignKey('networks.id'))
    node = Column(Integer, ForeignKey('nodes.id', ondelete="CASCADE"))
    ip_addr = Column(String(25), nullable=False)
    # admin field is for mark IPAddr instance as address
    # allocated in fuelweb (admin) network
    admin = Column(Boolean, nullable=False, default=False)


class Vlan(Base):
    __tablename__ = 'vlan'
    id = Column(Integer, primary_key=True)
    network = relationship("Network",
                           backref=backref("vlan"))


class Network(Base):
    __tablename__ = 'networks'
    id = Column(Integer, primary_key=True)
    release = Column(Integer, ForeignKey('releases.id'), nullable=False)
    name = Column(Unicode(100), nullable=False)
    access = Column(String(20), nullable=False)
    vlan_id = Column(Integer, ForeignKey('vlan.id'))
    network_group_id = Column(Integer, ForeignKey('network_groups.id'))
    cidr = Column(String(25), nullable=False)
    gateway = Column(String(25))
    nodes = relationship(
        "Node",
        secondary=IPAddr.__table__,
        backref="networks")


class NetworkGroup(Base):
    __tablename__ = 'network_groups'
    id = Column(Integer, primary_key=True)
    name = Column(Unicode(100), nullable=False)
    access = Column(String(20), nullable=False)
    release = Column(Integer, nullable=False)
    cluster_id = Column(Integer, ForeignKey('clusters.id'), nullable=False)
    cidr = Column(String(25), nullable=False)
    network_size = Column(Integer, default=256)
    amount = Column(Integer, default=1)
    vlan_start = Column(Integer, default=1)
    gateway_ip_index = Column(Integer)
    networks = relationship("Network", cascade="delete",
                            backref="network_groups")

    @classmethod
    def generate_vlan_ids_list(cls, data):
        vlans = []
        for ng in data:
            current_vlan = ng["vlan_start"]
            for i in xrange(int(ng['amount'])):
                vlans.append({'vlan_id': current_vlan})
                current_vlan += 1
        return vlans


class NetworkConfiguration(object):
    @classmethod
    def update(cls, cluster, network_configuration):
        from nailgun.network.manager import NetworkManager
        network_manager = NetworkManager()
        if 'net_manager' in network_configuration:
            setattr(
                cluster,
                'net_manager',
                network_configuration['net_manager'])

        if 'networks' in network_configuration:
            for ng in network_configuration['networks']:
                ng_db = orm().query(NetworkGroup).get(ng['id'])

                for key, value in ng.iteritems():
                    setattr(ng_db, key, value)

                network_manager.create_networks(ng_db)
                ng_db.cluster.add_pending_changes('networks')


class AttributesGenerators(object):
    @classmethod
    def password(cls, arg=None):
        try:
            length = int(arg)
        except:
            length = 8
        chars = string.letters + string.digits
        return u''.join([choice(chars) for _ in xrange(length)])

    @classmethod
    def ip(cls, arg=None):
        if str(arg) in ("admin", "master"):
            return settings.MASTER_IP
        return "127.0.0.1"

    @classmethod
    def identical(cls, arg=None):
        return str(arg)


class Attributes(Base):
    __tablename__ = 'attributes'
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id'))
    editable = Column(JSON)
    generated = Column(JSON)

    def generate_fields(self):
        self.generated = self.traverse(self.generated)
        orm().add(self)
        orm().commit()

    @classmethod
    def traverse(cls, cdict):
        new_dict = {}
        if cdict:
            for i, val in cdict.iteritems():
                if isinstance(val, dict) and "generator" in val:
                    try:
                        generator = getattr(
                            AttributesGenerators,
                            val["generator"]
                        )
                    except AttributeError:
                        logger.error("Attribute error: %s" % val["generator"])
                        raise
                    else:
                        new_dict[i] = generator(val.get("generator_arg"))
                else:
                    new_dict[i] = cls.traverse(val)
        return new_dict

    def merged_attrs(self):
        return self._dict_merge(self.generated, self.editable)

    def merged_attrs_values(self):
        attrs = self.merged_attrs()
        for group_attrs in attrs.itervalues():
            for attr, value in group_attrs.iteritems():
                if isinstance(value, dict) and 'value' in value:
                    group_attrs[attr] = value['value']
        if 'common' in attrs:
            attrs.update(attrs.pop('common'))
        return attrs

    def _dict_merge(self, a, b):
        '''recursively merges dict's. not just simple a['key'] = b['key'], if
        both a and bhave a key who's value is a dict then dict_merge is called
        on both values and the result stored in the returned dictionary.'''
        if not isinstance(b, dict):
            return b
        result = deepcopy(a)
        for k, v in b.iteritems():
            if k in result and isinstance(result[k], dict):
                    result[k] = self._dict_merge(result[k], v)
            else:
                result[k] = deepcopy(v)
        return result


class Task(Base):
    __tablename__ = 'tasks'
    TASK_STATUSES = (
        'ready',
        'running',
        'error'
    )
    TASK_NAMES = (
        'super',
        'deploy',
        'deployment',
        'node_deletion',
        'cluster_deletion',
        'check_networks',
        'verify_networks'
    )
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id'))
    uuid = Column(String(36), nullable=False,
                  default=lambda: str(uuid.uuid4()))
    name = Column(
        Enum(*TASK_NAMES, name='task_name'),
        nullable=False,
        default='super'
    )
    message = Column(Text)
    status = Column(
        Enum(*TASK_STATUSES, name='task_status'),
        nullable=False,
        default='running'
    )
    progress = Column(Integer, default=0)
    cache = Column(JSON, default={})
    result = Column(JSON, default={})
    parent_id = Column(Integer, ForeignKey('tasks.id'))
    subtasks = relationship(
        "Task",
        backref=backref('parent', remote_side=[id])
    )
    notifications = relationship(
        "Notification",
        backref=backref('task', remote_side=[id])
    )

    def __repr__(self):
        return "<Task '{0}' {1} ({2}) {3}>".format(
            self.name,
            self.uuid,
            self.cluster_id,
            self.status
        )

    def execute(self, instance, *args, **kwargs):
        return instance.execute(self, *args, **kwargs)

    def create_subtask(self, name):
        if not name:
            raise ValueError("Subtask name not specified")

        task = Task(name=name, cluster=self.cluster)

        self.subtasks.append(task)
        orm().commit()
        return task


class Notification(Base):
    __tablename__ = 'notifications'

    NOTIFICATION_STATUSES = (
        'read',
        'unread',
    )

    NOTIFICATION_TOPICS = (
        'discover',
        'done',
        'error',
    )

    id = Column(Integer, primary_key=True)
    cluster_id = Column(
        Integer,
        ForeignKey('clusters.id', ondelete='SET NULL')
    )
    node_id = Column(Integer, ForeignKey('nodes.id', ondelete='SET NULL'))
    task_id = Column(Integer, ForeignKey('tasks.id', ondelete='SET NULL'))
    topic = Column(
        Enum(*NOTIFICATION_TOPICS, name='notif_topic'),
        nullable=False
    )
    message = Column(Text)
    status = Column(
        Enum(*NOTIFICATION_STATUSES, name='notif_status'),
        nullable=False,
        default='unread'
    )
    datetime = Column(DateTime, nullable=False)


class L2Topology(Base, BasicValidator):
    __tablename__ = 'l2_topologies'
    id = Column(Integer, primary_key=True)
    network_id = Column(
        Integer,
        ForeignKey('networks.id', ondelete="CASCADE"),
        nullable=False
    )


class L2Connection(Base, BasicValidator):
    __tablename__ = 'l2_connections'
    id = Column(Integer, primary_key=True)
    topology_id = Column(
        Integer,
        ForeignKey('l2_topologies.id', ondelete="CASCADE"),
        nullable=False
    )
    interface_id = Column(
        Integer,
        # If interface is removed we should somehow remove
        # all L2Topologes which include this interface.
        ForeignKey('node_nic_interfaces.id', ondelete="CASCADE"),
        nullable=False
    )


class AllowedNetworks(Base, BasicValidator):
    __tablename__ = 'allowed_networks'
    id = Column(Integer, primary_key=True)
    network_id = Column(
        Integer,
        ForeignKey('networks.id', ondelete="CASCADE"),
        nullable=False
    )
    interface_id = Column(
        Integer,
        ForeignKey('node_nic_interfaces.id', ondelete="CASCADE"),
        nullable=False
    )


class NetworkAssignment(Base, NetAssignmentValidator):
    __tablename__ = 'net_assignments'
    id = Column(Integer, primary_key=True)
    network_id = Column(
        Integer,
        ForeignKey('networks.id', ondelete="CASCADE"),
        nullable=False
    )
    interface_id = Column(
        Integer,
        ForeignKey('node_nic_interfaces.id', ondelete="CASCADE"),
        nullable=False
    )

    @classmethod
    def verify_data_correctness(cls, node):
        db_node = cls.db.query(Node).filter_by(id=node['id']).first()
        if not db_node:
            raise web.webapi.badrequest(
                message="There is no node with ID '%d' in DB" % node['id']
            )
        interfaces = node['interfaces']
        db_interfaces = db_node.interfaces
        if len(interfaces) != len(db_interfaces):
            raise web.webapi.badrequest(
                message="Node '%d' has different amount of interfaces" %
                        node['id']
            )
        # FIXIT: we should use not all networks but appropriate for this
        # node only.
        db_network_group = cls.db.query(NetworkGroup).filter_by(
            cluster_id=db_node.cluster_id
        ).first()
        if not db_network_group:
            raise web.webapi.badrequest(
                message="There are no networks related to"
                        " node '%d' in DB" % node['id']
            )
        network_ids = set([n.id for n in db_network_group.networks])

        for iface in interfaces:
            db_iface = filter(
                lambda i: i.id == iface['id'],
                db_interfaces
            )
            if not db_iface:
                raise web.webapi.badrequest(
                    message="There is no interface with ID '%d'"
                            " for node '%d' in DB" %
                            (iface['id'], node['id'])
                )
            db_iface = db_iface[0]

            for net in iface['assigned_networks']:
                if net['id'] not in network_ids:
                    raise web.webapi.badrequest(
                        message="Node '%d' shouldn't be connected to"
                                " network with ID '%d'" %
                                (node['id'], net['id'])
                    )
                network_ids.remove(net['id'])

        # Check if there are unassigned networks for this node.
        if network_ids:
            raise web.webapi.badrequest(
                message="Too few neworks to assign to node '%d'" %
                        node['id']
            )

    @classmethod
    def _update_attrs(cls, node):
        db_node = cls.db.query(Node).filter_by(id=node['id']).first()
        interfaces = node['interfaces']
        db_interfaces = db_node.interfaces
        for iface in interfaces:
            db_iface = filter(
                lambda i: i.id == iface['id'],
                db_interfaces
            )
            db_iface = db_iface[0]
            # Remove all old network's assignment for this interface.
            old_assignment = cls.db.query(NetworkAssignment).filter_by(
                interface_id=db_iface.id,
            ).all()
            map(cls.db.delete, old_assignment)
            for net in iface['assigned_networks']:
                net_assignment = NetworkAssignment()
                net_assignment.network_id = net['id']
                net_assignment.interface_id = db_iface.id
                cls.db.add(net_assignment)

    @classmethod
    def update_attributes(cls, node):
        cls.verify_data_correctness(node)
        cls._update_attrs(node)
        cls.db.commit()

    @classmethod
    def update_collection_attributes(cls, data):
        for node in data:
            cls.verify_data_correctness(node)
            cls._update_attrs(node)
        cls.db.commit()


class NodeNICInterface(Base, BasicValidator):
    __tablename__ = 'node_nic_interfaces'
    id = Column(Integer, primary_key=True)
    node_id = Column(
        Integer,
        ForeignKey('nodes.id', ondelete="CASCADE"),
        nullable=False
    )
    name = Column(String(128), nullable=False) #eth0
    mac = Column(String(32), nullable=False) #aa:00:00
    max_speed = Column(Integer)
    current_speed = Column(Integer)
    allowed_networks = relationship(
        "Network",
        secondary=AllowedNetworks.__table__,
    )
    assigned_networks = relationship(
        "Network",
        secondary=NetworkAssignment.__table__,
    )


