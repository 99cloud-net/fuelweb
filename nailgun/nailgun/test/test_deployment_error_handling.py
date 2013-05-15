# -*- coding: utf-8 -*-
import re
import json
import time
from functools import partial

from mock import patch

from nailgun.settings import settings

import nailgun
import nailgun.rpc as rpc
from nailgun.task.manager import DeploymentTaskManager
from nailgun.task.fake import FAKE_THREADS
from nailgun.test.base import BaseHandlers
from nailgun.test.base import reverse
from nailgun.test.base import fake_tasks
from nailgun.api.models import Cluster, Attributes, Task, Notification, Node


def raise_(*args, **kwargs):
    raise kwargs.pop("ex")

alert = partial(raise_, ex=Exception("ALERT"))
no_message_alert = partial(raise_, ex=Exception(""))


class TestErrors(BaseHandlers):

    def tearDown(self):
        self._wait_for_threads()

    @patch('nailgun.task.task.rpc.cast')
    @patch('nailgun.task.task.DeploymentTask._provision', alert)
    def test_deployment_errors_update_cluster(self, mocked_rpc):
        self.env.create(
            cluster_kwargs={},
            nodes_kwargs=[
                {"pending_addition": True},
            ]
        )
        supertask = self.env.launch_deployment()
        self.env.wait_error(supertask, 60, "Failed to call cobbler: ALERT")
        self.db.refresh(supertask.cluster)
        self.assertEquals(supertask.cluster.status, 'error')

    @patch('nailgun.task.task.rpc.cast')
    @patch('nailgun.task.task.DeploymentTask._provision', no_message_alert)
    def test_deployment_cobbler_no_message(self, mocked_rpc):
        self.env.create(
            cluster_kwargs={},
            nodes_kwargs=[
                {"pending_addition": True},
            ]
        )
        supertask = self.env.launch_deployment()
        self.env.wait_error(supertask, 60,
                            "Failed to call cobbler: see logs for details")

    @fake_tasks(error="provisioning")
    def test_deployment_error_during_provisioning(self):
        self.env.create(
            cluster_kwargs={},
            nodes_kwargs=[
                {"name": "First",
                 "pending_addition": True},
                {"name": "Second",
                 "role": "compute",
                 "pending_addition": True}
            ]
        )
        supertask = self.env.launch_deployment()
        self.env.wait_error(supertask, 60, re.compile(
            "Deployment has failed\. Check these nodes:\n'(First|Second)'"
        ))
        self.env.refresh_nodes()
        self.env.refresh_clusters()
        n_error = lambda n: (n.status, n.error_type) == ('error', 'provision')
        self.assertEqual(
            sum(map(n_error, self.env.nodes)),
            1
        )
        self.assertEquals(supertask.cluster.status, 'error')

    @fake_tasks(error="provisioning", error_msg="Terrible error")
    def test_deployment_error_from_orchestrator(self):
        self.env.create(
            cluster_kwargs={},
            nodes_kwargs=[
                {"name": "First",
                 "pending_addition": True},
                {"name": "Second",
                 "role": "compute",
                 "pending_addition": True},
                {"name": "Third",
                 "role": "compute",
                 "status": "error",
                 "error_type": "provision",
                 "error_msg": "I forgot about teapot!"}
            ]
        )
        supertask = self.env.launch_deployment()
        err_msg = "Deployment has failed. Terrible error"
        self.env.wait_error(supertask, 60, err_msg)
        self.assertIsNotNone(
            self.db.query(Notification).filter_by(message=err_msg).first()
        )
        self.assertEqual(
            self.db.query(Notification).filter_by(
                node_id=self.env.nodes[2].id
            ).first().message,
            "Failed to deploy node 'Third': I forgot about teapot!"
        )
        self.env.refresh_nodes()
        self.env.refresh_clusters()
        n_error = lambda n: (n.status, n.error_type) == ('error', 'provision')
        self.assertIn(
            sum(map(n_error, self.env.nodes)),
            [1, 2]
        )
        self.assertEquals(supertask.cluster.status, 'error')

    @fake_tasks(error="deployment")
    def test_deployment_error_during_deployment(self):
        self.env.create(
            cluster_kwargs={},
            nodes_kwargs=[
                {"name": "First",
                 "pending_addition": True},
                {"name": "Second",
                 "role": "compute",
                 "pending_addition": True}
            ]
        )
        supertask = self.env.launch_deployment()
        self.env.wait_error(supertask, 60, re.compile(
            "Deployment has failed\. Check these nodes:\n'(First|Second)'"
        ))
        self.env.refresh_nodes()
        self.env.refresh_clusters()
        n_error = lambda n: (n.status, n.error_type) == ('error', 'deploy')
        self.assertEqual(
            sum(map(n_error, self.env.nodes)),
            1
        )
        self.assertEquals(supertask.cluster.status, 'error')

    @fake_tasks(error="deployment", task_ready=True)
    def test_task_ready_node_error(self):
        self.env.create(
            cluster_kwargs={},
            nodes_kwargs=[
                {"name": "First",
                 "pending_addition": True},
                {"name": "Second",
                 "role": "compute",
                 "pending_addition": True}
            ]
        )
        supertask = self.env.launch_deployment()
        self.env.wait_error(supertask, 60, re.compile(
            "Deployment has failed\. Check these nodes:\n'(First|Second)'"
        ))
