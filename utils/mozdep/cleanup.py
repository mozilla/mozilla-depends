# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from abc import ABC, abstractmethod
import atexit
import signal
import sys


__cleanup_done = False


def init():
    """Register cleanup handler"""

    # print "Registering cleanup handler"

    global __cleanup_done
    __cleanup_done = False

    # Will be OS-specific, see https://docs.python.org/3/library/signal.html
    atexit.register(cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)
    if sys.platform == "darwin" or "linux" in sys.platform:
        # SIGHUP is not available on Windows
        signal.signal(signal.SIGHUP, cleanup_handler)


def cleanup_handler():
    """The cleanup handler that runs when process terminates"""
    # print "Cleanup handler called"
    global __cleanup_done
    if not __cleanup_done:
        __cleanup_done = True
        for child in CleanUp.__subclasses__():
            child.at_exit()


class CleanUp(ABC):
    """When process terminates, .at_exit() is called on every subclass."""
    @staticmethod
    @abstractmethod
    def at_exit():
        pass
