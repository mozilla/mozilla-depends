# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from IPython import embed
import logging

from .basecommand import BaseCommand
from .. import knowledgegraph as kg
import networkx as nx

logger = logging.getLogger(__name__)


class IpythonCommand(BaseCommand):
    """
    Command for listing dependencies detected in tree
    """

    name = "ipython"
    help = "drop into test shell"

    @classmethod
    def setup_args(cls, parser):
        """
        Add subparser for setup-specific arguments.

        :param parser: parent argparser to add to
        :return: None
        """
        pass

    def run(self) -> int:
        repo_dir = self.args.tree.resolve()

        g = kg.KnowledgeGraph()

        lib_x = g.new_subject({kg.Ns().fx.mc.lib.name: "libx", })

        dep_i = g.new_subject({
            kg.Ns().fx.mc.lib.dep.name: "libx",
            kg.Ns().version.spec: "0.2",
            kg.Ns().fx.mc.lib: lib_x,
        })

        dep_j = g.new_subject({
            kg.Ns().fx.mc.lib.dep.name: "libx",
            kg.Ns().version.spec: "0.1",
            kg.Ns().fx.mc.lib: lib_x,
        })

        file_a = g.new_subject({
            kg.Ns().fx.mc.file.path: "layout/foo",
            kg.Ns().fx.mc.lib.dep: dep_i,
            kg.Ns().fx.mc.file.in_component: "Core::Foo"
        })
        file_b = g.new_subject({
            kg.Ns().fx.mc.file.path: "layout/bar",
            kg.Ns().fx.mc.lib.dep: dep_i,
            kg.Ns().fx.mc.file.in_component: "Core::Foo"
        })
        file_c = g.new_subject({
            kg.Ns().fx.mc.file.path: "layout/baz",
            kg.Ns().fx.mc.lib.dep: dep_j,
            kg.Ns().fx.mc.file.in_component: "Core::Foo"
        })

        embed()
        return 0
