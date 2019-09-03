# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import configparser
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager(object):
    """
    Class for managing global configuration

    This is supposed to be a singleton class to avoid de-synchronization.
    Use ConfigManager.get_singleton() to get the global instance.
    """

    __global_instance = None

    @classmethod
    def get_singleton(cls, args, filename: str = "mozdep.cfg"):
        """Return global singleton instance of ConfigManager"""
        if cls.__global_instance is None:
            cls.__global_instance = cls(args, filename, singleton_check=False)
        if cls.__global_instance.__args != args:
            raise Exception("ConfigManager singleton fetched with mismatching arguments: %s != %s" %
                            (args, cls.__global_instance.__args))
        return cls.__global_instance

    @classmethod
    def reset_singleton(cls):
        """Dispose of singleton instance of ConfigManager"""
        cls.__global_instance = None

    def __init__(self, args, filename: str = "mozdep.cfg", singleton_check=True):
        if singleton_check:
            raise Exception("Use ConfigManager.get_singleton() for getting global instance")
        self.__args = args
        if not self.__args.workdir.exists():
            self.__args.workdir.mkdir()
        self.__filename = self.__args.workdir / filename
        self.__config = configparser.ConfigParser()
        self.read()

    @property
    def config_file(self):
        return self.__filename

    def as_dict(self):
        res = {}
        for section in self.__config.sections():
            res[section] = dict(self.__config.items(section))
        return res

    def read(self):
        """Read config from disk"""
        logger.debug("Reading config from `%s`" % self.__filename)
        try:
            with self.__filename.open(mode="r") as fp:
                self.__config.read_file(fp)
            self.__filename.chmod(0o660)
            logger.debug("Config content is: %s" % self.as_dict())
        except FileNotFoundError:
            pass

    def write(self):
        """Write config to disk"""
        logger.debug("Writing config to `%s`: `%s`" % (self.__filename, self.as_dict()))
        self.__config.write(self.__filename.open(mode="w"))
        # Minor race condition here
        self.__filename.chmod(0o660)

    def get(self, section: str, option: str, fallback: str or None = None, write: bool = True):
        """
        Get config value. Returns fallback if option has no value.
        If write is True and fallback is not None, config is written to disk
        if fallback takes effect.

        :param section: str
        :param option: str
        :param fallback: str
        :param write: bool
        :return: str or None
        """
        try:
            return self.__config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                self.set(section, option, fallback)
                if write:
                    self.write()
            return fallback

    def set(self, section, option, value, write=True):
        """
        Set config value. Writes new config to disk if write is True.

        :param section: str
        :param option: str
        :param value: str
        :param write: bool
        :return:
        """
        if not self.__config.has_section(section):
            self.__config.add_section(section)
        self.__config.set(section, option, value)
        if write:
            self.write()
