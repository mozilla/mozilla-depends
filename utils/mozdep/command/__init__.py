# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import sys

from . import basecommand
from . import detect
from . import rustlist

__all__ = ["detect", "rustlist"]
logger = logging.getLogger(__name__)


def __subclasses_of(cls):
    sub_classes = cls.__subclasses__()
    sub_sub_classes = []
    for sub_cls in sub_classes:
        sub_sub_classes += __subclasses_of(sub_cls)
    return sub_classes + sub_sub_classes


# Keep a record of all BaseCommand subclasses
all_commands = dict([(command.name, command) for command in __subclasses_of(basecommand.BaseCommand)])
all_command_names = sorted(all_commands.keys())


def run(args, tmp_dir):
    global logger

    try:
        current_command = all_commands[args.command](args, tmp_dir)
    except KeyError:
        logger.critical("Unknown command `%s`. Choose one of: %s" % (args.command, ", ".join(all_command_names)))
        sys.exit(5)

    logger.debug("Running `%s` .setup()" % args.command)
    current_command.setup()
    logger.debug("Running `%s` .run()" % args.command)
    result = current_command.run()
    logger.debug("Running `%s` .teardown()" % args.command)
    current_command.teardown()
    logger.debug("Command `%s` finished" % args.command)

    return result
