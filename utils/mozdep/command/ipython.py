# -*- coding: utf8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from IPython import embed
import logging
import networkx as nx

from .basecommand import BaseCommand
import mozdep.component as comp
import mozdep.node_utils as nu
import mozdep.knowledge_utils as ku
import mozdep.knowledgegraph as kg
import mozdep.repo_utils as ru

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
        if self.args.tree is not None:
            repo_dir = self.args.tree.resolve()
            hg = ru.HgRepo(repo_dir)

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
