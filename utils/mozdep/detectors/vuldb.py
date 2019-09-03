# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from json import loads, decoder
from pathlib import Path
import requests
from tempfile import NamedTemporaryFile

from .basedetector import DependencyDetector
from mozdep.config import ConfigManager
from mozdep.knowledgegraph import Ns
import mozdep.knowledge_utils as ku
from mozdep.node_utils import NodeEnv, NodeError

logger = logging.getLogger(__name__)



class VulDBClient(object):

    __global_instance = None

    @classmethod
    def get_singleton(cls, args=None):
        """
        Return global singleton instance of VulDBClient.

        The first call to this must include a reference to the global args object,
        else it raises an exception. Subsequent calls may omit passing that reference.
        If a reference to a different args object is passed, an exception is raised.
        """
        if cls.__global_instance is None:
            if args is None:
                raise Exception("VulDBClient singleton requires argument object for first instantiation")
            cls.__global_instance = cls(args, singleton_check=False)
        if args is not None and cls.__global_instance.__args != args:
            raise Exception("VulDBClient singleton fetched with mismatching arguments")
        return cls.__global_instance


    @classmethod
    def reset_singleton(cls):
        """Dispose of singleton instance of VulDBClient"""
        cls.__global_instance = None

    def __init__(self, args, singleton_check=True):
        if singleton_check:
            raise Exception("Use VulDBClient.get_singleton() for getting global instance")
        self.__args = args
        self.__config = ConfigManager.get_singleton(self.__args)
        self.__url = self.__config.get("vuldb", "api_url", fallback="https://vuldb.com/?api")
        self.__token = self.__config.get("vuldb", "token", "__API_TOKEN__")

    def set_token(self, user_token: str):
        self.__token = user_token

    def is_authenticated(self):
        # There is no way to query the VulDB API in a way that validates a token but
        # does not waste credits, so falling back to naive checking.
        return len(self.__token) == 32 and self.__token.isalnum()

    def get(self, **kwargs):
        """
        Make an authenticated GET request and return parsed JSON result.

        Generally used for retrieving Trello objects.
        """
        params = kwargs
        params.update({"apikey": self.__token})
        r = requests.get(self.__url, params=params)
        r.raise_for_status()
        return r.json()

    def post(self, **kwargs):
        """
        Make an authenticated POST request and return parsed JSON result.

        Generally used for creating Trello objects.
        """
        data = kwargs
        data.update({"apikey": self.__token})
        r = requests.post(self.__url, data=data)
        r.raise_for_status()
        return r.json()


# 200	Request correct, allowed, processed and results returned
# 204	Request correct, allowed, processed but no results returned because they are empty
# 401	Authentication required, API key missing or unrecognized
# 403	API rate exceeded, no further requests allowed until counter reset
# 405	Unknown request type


class VulDBDetector(DependencyDetector):

    @staticmethod
    def name() -> str:
        return "vuldb"

    @staticmethod
    def priority() -> int:
        return -20

    def setup(self) -> bool:
        cm = ConfigManager.get_singleton(self.args)
        cm.get("vuldb", "api_url", "https://vuldb.com/?api")
        if cm.get("vuldb", "token", "__API_TOKEN__") == "__API_TOKEN__":
            logger.error(f"Unable to query VulnDB without API token. Check {str(cm.config_file)}")
            return False
        return True

    def run(self):
        return
