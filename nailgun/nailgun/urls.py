# -*- coding: utf-8 -*-

from nailgun.api.urls import api_app
from nailgun.webui.urls import webui_app

urls = (
    "/api", api_app,
    "", webui_app
)
