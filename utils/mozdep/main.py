#!/usr/bin/env python3
# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import coloredlogs
import logging
import os
import pkg_resources
from pathlib import Path
import sys
from threading import enumerate
from time import sleep, gmtime

from . import command

# Initialize coloredlogs
logging.Formatter.converter = gmtime
logger = logging.getLogger(__name__)
coloredlogs.DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s"
coloredlogs.install(level="INFO")

tmp_dir = None
module_dir = None


def parse_args(argv=None):
    """
    Argument parsing. Parses from sys.argv if argv is None.
    :param argv: argument vector to parse
    :return: parsed arguments
    """
    if argv is None:
        argv = sys.argv[1:]

    pkg_version = pkg_resources.require("mozdep")[0].version
    home = os.path.expanduser("~")

    # Set up the parent parser with shared arguments
    parser = argparse.ArgumentParser(prog="mozdep")
    parser.add_argument("--version", action="version", version="%(prog)s " + pkg_version)
    parser.add_argument("-d", "--debug",
                        help="enable debug",
                        action="store_true")
    parser.add_argument("-t", "--tree",
                        help="path to mozilla-central/unified tree",
                        type=Path,
                        action="store",
                        default=Path("%s/src/mozilla-unified" % home))

    # Set up subparsers, one for each subcommand
    subparsers = parser.add_subparsers(help="Subcommand", dest="command")
    for command_name in command.all_commands:
        command_class = command.all_commands[command_name]
        sub_parser = subparsers.add_parser(command_name, help=command_class.help)
        command_class.setup_args(sub_parser)

    return parser.parse_args(argv)


# This is the entry point used in setup.py
def main(argv=None):
    global logger, tmp_dir, module_dir

    module_dir = os.path.split(__file__)[0]

    args = parse_args(argv)

    if args.debug:
        coloredlogs.install(level='DEBUG')

    logger.debug("Command arguments: %s" % args)

    # Create workdir (usually ~/.trellosa, used for caching etc.)
    # Assumes that no previous code must write to it.
    if not args.tree.exists():
        logger.critical("You must specify a valid Mozilla Central tree")
        return 20

    # Execute the specified command
    try:
        result = command.run(args, tmp_dir)

    except KeyboardInterrupt:
        logger.critical("\nUser interrupt. Quitting...")
        return 10

    # Wait for sub-threads to wind down
    if len(enumerate()) > 1:
        logger.info("Waiting for background threads to finish")
        while len(enumerate()) > 1:
            logger.debug("Remaining threads: %s" % enumerate())
            sleep(2)

    return result


if __name__ == "__main__":
    sys.exit(main(sys.argv))
