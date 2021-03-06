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
"""Interface for communicating with the Visual Studio debugger via DTE."""

import abc
import imp
import os
import sys

from dex.debugger.DebuggerBase import DebuggerBase
from dex.dextIR import FrameIR, LocIR, StepIR, StopReason, ValueIR
from dex.utils.compatibility import add_metaclass
from dex.utils.Exceptions import LoadDebuggerException


def _load_com_module():
    try:
        module_info = imp.find_module(
            'ComInterface',
            [os.path.join(os.path.dirname(__file__), 'windows')])
        return imp.load_module('ComInterface', *module_info)
    except ImportError as e:
        raise LoadDebuggerException(e, sys.exc_info())


@add_metaclass(abc.ABCMeta)
class VisualStudio(DebuggerBase):  # pylint: disable=abstract-method

    # Constants for results of Debugger.CurrentMode
    # (https://msdn.microsoft.com/en-us/library/envdte.debugger.currentmode.aspx)
    dbgDesignMode = 1
    dbgBreakMode = 2
    dbgRunMode = 3

    def __init__(self, *args):
        self.com_module = None
        self._debugger = None
        self._solution = None
        self._fn_step = None
        self._fn_go = None
        super(VisualStudio, self).__init__(*args)

    def _custom_init(self):
        try:
            self._debugger = self._interface.Debugger
            self._debugger.HexDisplayMode = False

            self._interface.MainWindow.Visible = (
                self.context.options.show_debugger)

            self._solution = self._interface.Solution
            self._solution.Create(self.context.working_directory.path,
                                  'DexterSolution')

            try:
                self._solution.AddFromFile(self._project_file)
            except OSError:
                raise LoadDebuggerException(
                    'could not debug the specified executable', sys.exc_info())

            self._fn_step = self._debugger.StepInto
            self._fn_go = self._debugger.Go

        except AttributeError as e:
            raise LoadDebuggerException(str(e), sys.exc_info())

    def _custom_exit(self):
        if self._interface:
            self._interface.Quit()

    @property
    def _project_file(self):
        return self.context.options.executable

    @abc.abstractproperty
    def _dte_version(self):
        pass

    @property
    def _location(self):
        bp = self._debugger.BreakpointLastHit
        return {
            'path': getattr(bp, 'File', None),
            'lineno': getattr(bp, 'FileLine', None),
            'column': getattr(bp, 'FileColumn', None)
        }

    @property
    def _mode(self):
        return self._debugger.CurrentMode

    def _load_interface(self):
        self.com_module = _load_com_module()
        return self.com_module.DTE(self._dte_version)

    @property
    def version(self):
        try:
            return self._interface.Version
        except AttributeError:
            return None

    def clear_breakpoints(self):
        for bp in self._debugger.Breakpoints:
            bp.Delete()

    def add_breakpoint(self, file_, line):
        self._debugger.Breakpoints.Add('', file_, line)

    def launch(self):
        self.step()

    def step(self):
        self._fn_step()

    def go(self):
        self._fn_go()

    def get_step_info(self):
        thread = self._debugger.CurrentThread
        stackframes = thread.StackFrames

        frames = []

        for sf in stackframes:
            frame = FrameIR(
                function=self._sanitize_function_name(sf.FunctionName),
                is_inlined=sf.FunctionName.startswith('[Inline Frame]'),
                loc=LocIR(path=None, lineno=None, column=None))

            fname = frame.function or ''  # pylint: disable=no-member
            if any(name in fname for name in self.frames_below_main):
                break

            frames.append(frame)

        loc = LocIR(**self._location)
        if frames:
            frames[0].loc = loc

        reason = StopReason.BREAKPOINT
        if loc.path is None:  # pylint: disable=no-member
            reason = StopReason.STEP

        return StepIR(
            step_index=self.step_index, frames=frames, stop_reason=reason)

    @property
    def is_running(self):
        return self._mode == VisualStudio.dbgRunMode

    @property
    def is_finished(self):
        return self._mode == VisualStudio.dbgDesignMode

    @property
    def frames_below_main(self):
        return [
            '[Inline Frame] invoke_main', '__scrt_common_main_seh',
            '__tmainCRTStartup', 'mainCRTStartup'
        ]

    def evaluate_expression(self, expression):
        result = self._debugger.GetExpression(expression)
        value = result.Value

        is_optimized_away = any(s in value for s in [
            'Variable is optimized away and not available',
            'Value is not available, possibly due to optimization',
        ])

        is_irretrievable = any(s in value for s in [
            '???',
            '<Unable to read memory>',
        ])

        # an optimized away value is still counted as being able to be
        # evaluated.
        could_evaluate = (result.IsValidValue or is_optimized_away
                          or is_irretrievable)

        return ValueIR(
            expression=expression,
            value=value,
            type=result.Type,
            error_string=None,
            is_optimized_away=is_optimized_away,
            could_evaluate=could_evaluate,
            is_irretrievable=is_irretrievable,
        )
