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
"""This is the main entry point.
It implements some functionality common to all subtools such as command line
parsing and running the unit-testing and linting harnesses, before calling the
requested subtool.
"""

import imp
import os
import sys

from dex.utils import PrettyOutput, Timer
from dex.utils import ExtArgParse as argparse
from dex.utils import get_root_directory
from dex.utils.Exceptions import Error, ToolArgumentError
from dex.utils.Linting import linting_ok
from dex.utils.UnitTests import unit_tests_ok
from dex.utils.Version import version
from dex.utils import WorkingDirectory


def get_tools_directory():
    tools_directory = os.path.join(get_root_directory(), 'tools')
    assert os.path.isdir(tools_directory), tools_directory
    return tools_directory


def get_tool_names():
    tools_directory = get_tools_directory()
    return [
        t.replace('_', '-') for t in os.listdir(tools_directory)
        if os.path.isfile(os.path.join(tools_directory, t, 'Tool.py'))
    ]


def tool_main(context, tool, args):
    with Timer(tool.name):
        options, defaults = tool.parse_command_line(args)
        Timer.display = options.time_report
        Timer.indent = options.indent_timer_level
        Timer.fn = context.o.blue
        context.options = options
        context.version = version(tool.name)

        if options.version:
            context.o.green('{}\n'.format(context.version))
            return 0

        if (options.unittest != 'off' and not unit_tests_ok(context)):
            raise Error('<d>unit test failures</>')

        if options.lint != 'off' and not linting_ok(context):
            raise Error('<d>linting failures</>')

        if options.colortest:
            context.o.colortest()
            return 0

        try:
            tool.handle_base_options(defaults)
        except ToolArgumentError as e:
            raise Error(e)

        dir_ = context.options.working_directory
        with WorkingDirectory(context, dir=dir_) as context.working_directory:
            tool.go()
        return 0


def main():
    class context(object):
        pass

    with PrettyOutput() as context.o:
        try:
            context.root_directory = get_root_directory()

            # Flag some strings for auto-highlighting.
            context.o.auto_reds.extend([
                r'[Ee]rror\:',
                r'[Ee]xception\:',
                r'un(expected|recognized) argument',
            ])
            context.o.auto_yellows.extend([
                r'[Ww]arning\:',
                r'\(did you mean ',
                r'During handling of the above exception, another exception',
            ])

            tools_directory = get_tools_directory()

            parser = argparse.ExtArgumentParser(context, add_help=False)
            parser.add_argument('tool', default=None, nargs='?')

            options, args = parser.parse_known_args(sys.argv[1:])
            tool_name = options.tool

            if tool_name is None:
                tool_name = 'no_tool_'
            else:
                valid_tools = get_tool_names()
                if tool_name not in valid_tools:
                    raise Error('invalid tool "{}" (choose from {})'.format(
                        tool_name, ', '.join(
                            [t for t in valid_tools if not t.endswith('-')])))

                tool_name = tool_name.replace('-', '_')

            module_info = imp.find_module(tool_name, [tools_directory])
            module = imp.load_module(tool_name, *module_info)

            return tool_main(context, module.Tool(context), args)
        except Error as e:
            context.o.auto(
                '\nerror: {}\n'.format(str(e)), stream=PrettyOutput.stderr)

            try:
                if context.options.error_debug:
                    raise
            except AttributeError:
                pass
            return 1
        except (KeyboardInterrupt, SystemExit):
            raise
        except:  # noqa
            context.o.red(
                '\n\n'
                '<g>****************************************</>\n'
                '<b>****************************************</>\n'
                '****************************************\n'
                '**                                    **\n'
                '** <y>This is a bug in <a>DExTer</>.</>           **\n'
                '**                                    **\n'
                '**                  <y>Please report it.</> **\n'
                '**                                    **\n'
                '****************************************\n'
                '<b>****************************************</>\n'
                '<g>****************************************</>\n'
                '\n'
                '<b>system:</>\n'
                '<d>{}</>\n\n'
                '<b>version:</>\n'
                '<d>{}</>\n\n'
                '<b>args:</>\n'
                '<d>{}</>\n'
                '\n'.format(sys.platform, version('DExTer'),
                            [sys.executable] + sys.argv),
                stream=PrettyOutput.stderr)
            raise
