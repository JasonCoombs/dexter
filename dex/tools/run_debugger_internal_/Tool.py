# DExTer : Debugging Experience Tester
# ~~~~~~   ~         ~~         ~   ~~
#
# Copyright (c) 2018 by SN Systems Ltd., Sony Interactive Entertainment Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""This is an internal subtool used to sandbox the communication with a
debugger into a separate process so that any crashes inside the debugger will
not bring down the entire DExTer tool.
"""

import pickle

from dex.debugger import Debuggers
from dex.dextIR.DextIR import importDextIR
from dex.tools import ToolBase
from dex.utils import Timer
from dex.utils.Exceptions import DebuggerException, Error


class Tool(ToolBase):
    @property
    def name(self):
        return 'DExTer run debugger internal'

    def add_tool_arguments(self, parser, defaults):
        parser.add_argument('json', type=str, help='json file')
        parser.add_argument(
            'pickled_options', type=str, help='pickled options file')

    def handle_options(self, defaults):
        with open(self.context.options.json) as fp:
            self.context.dextIR = importDextIR(fp.read())

        with open(self.context.options.pickled_options, 'rb') as fp:
            poptions = pickle.load(fp)
            poptions.working_directory = (
                self.context.options.working_directory[:])
            poptions.lint = self.context.options.lint
            poptions.unittest = self.context.options.unittest
            poptions.json = self.context.options.json
            self.context.options = poptions

        Timer.display = self.context.options.time_report

    def go(self):
        options = self.context.options

        with Timer('loading debugger'):
            debugger = Debuggers(self.context).load(options.debugger,
                                                    self.context.dextIR)
            self.context.dextIR.debugger = debugger.debugger_info

        with Timer('running debugger'):
            if not debugger.is_available:
                msg = '<d>could not load {}</> ({})\n'.format(
                    debugger.name, debugger.loading_error)
                if options.verbose:
                    msg = '{}\n    {}'.format(
                        msg, '    '.join(debugger.loading_error_trace))
                raise Error(msg)

            with debugger:
                try:
                    debugger.start()
                except DebuggerException as e:
                    raise Error(e)

        with open(self.context.options.json, 'w') as fp:
            fp.write(self.context.dextIR.as_json)
