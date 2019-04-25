# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import logging

logger = logging.getLogger(__name__)


class BaseCommand(object):
    """
    Generic Command
    Base functionality for all commands
    """

    @classmethod
    def setup_args(cls, parser):
        """
        Add subparser for command-specific arguments.

        This definition serves as default, but commands are free to
        override it.

        :param parser: parent argparser to add to
        :return: None
        """

        group = parser.add_argument_group("unspecified basemode arguments")
        group.add_argument("-f", "--foo",
                           help="Limit for number of foos given (default: no limit)",
                           type=int,
                           action="store",
                           default=None)

    def __init__(self, args, tmp_dir):
        self.args = args
        self.command = args.command
        self.tmp_dir = tmp_dir

    @staticmethod
    def setup():
        """
        Runs all the steps required before doing the command runs.
        Put everything here that takes too long for __init__().
        :return: bool success
        """
        return True

    def run(self):
        """
        Executes the the steps that constitutes the actual command run.
        Results are kept internally in the class instance.
        :return: None
        """
        pass

    def teardown(self):
        """
        Clean up steps required after a command run.
        :return: None
        """
        pass
