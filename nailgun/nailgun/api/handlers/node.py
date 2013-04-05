# -*- coding: utf-8 -*-

import json
from datetime import datetime

import web

from nailgun.keepalive import keep_alive
from nailgun.db import orm
from nailgun.notifier import notifier
from nailgun.logger import logger
from nailgun.api.models import Node, NodeAttributes
from nailgun.api.handlers.base import JSONHandler


class NodeHandler(JSONHandler):
    fields = ('id', 'name', 'meta', 'network_data', 'role', 'progress',
              'status', 'mac', 'fqdn', 'ip', 'manufacturer', 'platform_name',
              'pending_addition', 'pending_deletion', 'os_platform',
              'error_type', 'online')
    model = Node

    def GET(self, node_id):
        web.header('Content-Type', 'application/json')
        node = orm().query(Node).get(node_id)
        if not node:
            return web.notfound()

        return json.dumps(
            self.render(node),
            indent=4
        )

    def PUT(self, node_id):
        web.header('Content-Type', 'application/json')
        node = orm().query(Node).get(node_id)
        if not node:
            return web.notfound()
        # additional validation needed?
        data = Node.validate_update(web.data())
        if not data:
            raise web.badrequest()
        # /additional validation needed?
        for key, value in data.iteritems():
            setattr(node, key, value)
        orm().commit()
        return json.dumps(
            self.render(node),
            indent=4
        )

    def DELETE(self, node_id):
        node = orm().query(Node).get(node_id)
        if not node:
            return web.notfound()
        orm().delete(node)
        orm().commit()
        raise web.webapi.HTTPError(
            status="204 No Content",
            data=""
        )


class NodeCollectionHandler(JSONHandler):

    def GET(self):
        web.header('Content-Type', 'application/json')
        user_data = web.input(cluster_id=None)
        if user_data.cluster_id == '':
            nodes = orm().query(Node).filter_by(
                cluster_id=None).all()
        elif user_data.cluster_id:
            nodes = orm().query(Node).filter_by(
                cluster_id=user_data.cluster_id).all()
        else:
            nodes = orm().query(Node).all()
        return json.dumps(map(
            NodeHandler.render,
            nodes), indent=4)

    def POST(self):
        web.header('Content-Type', 'application/json')
        data = Node.validate(web.data())
        node = Node()
        for key, value in data.iteritems():
            setattr(node, key, value)
        node.name = "Untitled (%s)" % data['mac'][-5:]
        node.timestamp = datetime.now()
        node.generate_volumes_info()
        orm().add(node)
        orm().commit()
        try:
            ram = str(round(float(
                node.meta['memory']['total']) / 1073741824, 1))
        except (KeyError, TypeError, ValueError):
            ram = "unknown"
        cores = str(node.meta.get('cpu', {}).get('total', "unknown"))
        notifier.notify("discover",
                        "New node with %s CPU core(s) "
                        "and %s GB memory is discovered" %
                        (cores, ram), node_id=node.id)
        raise web.webapi.created(json.dumps(
            NodeHandler.render(node),
            indent=4
        ))

    def PUT(self):
        web.header('Content-Type', 'application/json')
        data = Node.validate_collection_update(web.data())
        q = orm().query(Node)
        nodes_updated = []
        for nd in data:
            is_agent = nd.get("is_agent")
            node = None
            if "mac" in nd:
                node = q.filter_by(mac=nd["mac"]).first()
            else:
                node = q.get(nd["id"])
            for key, value in nd.iteritems():
                if key != "is_agent":
                    if is_agent and (key, value) == ("status", "discover") \
                            and node.status == "provisioning":
                        # We don't update provisioning back to discover
                        logger.debug(
                            "Node is already provisioning - "
                            "status not updated by agent"
                        )
                        continue
                    setattr(node, key, value)
            if is_agent:
                node.timestamp = datetime.now()
                if not node.online:
                    node.online = True
                    msg = u"Node '{0}' is back online".format(
                        node.name or node.mac
                    )
                    logger.info(msg)
                    notifier.notify(
                        "discover",
                        msg,
                        node_id=node.id
                    )
            nodes_updated.append(node)
            orm().add(node)
        orm().commit()
        return json.dumps(map(
            NodeHandler.render,
            nodes_updated), indent=4)


class NodeAttributesHandler(JSONHandler):
    fields = ('node_id', 'volumes')

    def GET(self, node_id):
        web.header('Content-Type', 'application/json')
        node_attrs = orm().query(Node).get(node_id).attributes
        if not node_attrs:
            return web.notfound()
        return json.dumps(
            self.render(node_attrs),
            indent=4
        )

    def PUT(self):
        web.header('Content-Type', 'application/json')
        node_attrs = orm().query(Node).get(node_id).attributes
        if not node_attrs:
            return web.notfound()
        for key, value in web.data().iteritems():
            setattr(node_attrs, key, value)
        orm().commit()
        return json.dumps(
            self.render(node_attrs),
            indent=4
        )


class NodeAttributesByNameHandler(JSONHandler):

    def GET(self, node_id, attr_name):
        web.header('Content-Type', 'application/json')
        node_attrs = orm().query(Node).get(node_id).attributes
        if not node_attrs or not hasattr(node_attrs, attr_name):
            raise web.notfound()
        return json.dumps(
            getattr(node_attrs, attr_name),
            indent=4
        )

    def PUT(self, node_id, attr_name):
        web.header('Content-Type', 'application/json')
        node_attrs = orm().query(Node).get(node_id).attributes
        if not node_attrs or not hasattr(node_attrs, attr_name):
            raise web.notfound()
        setattr(node_attrs, attr_name, web.data())
        return json.dumps(
            getattr(node_attrs, attr_name),
            indent=4
        )
