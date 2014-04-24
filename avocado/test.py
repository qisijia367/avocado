# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; specifically version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# This code was inspired in the autotest project,
# client/shared/test.py
# Authors: Martin J Bligh <mbligh@google.com>, Andy Whitcroft <apw@shadowen.org>

"""
Contains the base test implementation, used as a base for the actual
framework tests.
"""

import logging
import os
import sys
import time
import traceback
import unittest

from avocado.core import data_dir
from avocado.core import exceptions
from avocado.utils import process
from avocado import sysinfo


class Test(unittest.TestCase):

    """
    Base implementation for the test class.

    You'll inherit from this to write your own tests. Tipically you'll want
    to implement setup(), action() and cleanup() methods on your own tests.

    Test Attributes:

    basedir:
        Where the test .py file is located (root dir).
    depsdir:
        If this is an existing test suite wrapper, it'll contain the
        test suite sources and other auxiliary files. Usually inside
        basedir, 'deps' subdirectory.
    workdir:
        Place where temporary copies of the source code, binaries,
        image files will be created and modified.
    base_logdir:
        Base log directory, where logs from all tests go to.
    """

    def __init__(self, methodName='runTest', name=None, base_logdir=None,
                 tag=None):
        """
        Initializes the test.

        :param methodName: Name of the main method to run. For the sake of
                           compatibility with the original unittest class,
                           you should not set this.
        :param name: Pretty name of the test name. For normal tests, written
                     with the avocado API, this should not be set, this is
                     reserved for running random executables as tests.
        :param base_logdir: Directory where test logs should go. If None
                            provided, it'll use ~/avocado.
        :param tag: Tag that differentiates 2 executions of the same test name.
                    Example: 'long', 'short', so we can differentiate
                    'sleeptest.long' and 'sleeptest.short'.
        """
        if name is not None:
            self.name = name
        else:
            self.name = self.__class__.__name__

        self.tag = tag
        self.basedir = os.path.join(data_dir.get_test_dir(), self.name)
        self.depsdir = os.path.join(self.basedir, 'deps')
        self.workdir = os.path.join(data_dir.get_tmp_dir(), self.name)
        if not os.path.isdir(self.workdir):
            os.makedirs(self.workdir)
        self.srcdir = os.path.join(self.workdir, 'src')
        if not os.path.isdir(self.srcdir):
            os.makedirs(self.srcdir)
        if base_logdir is None:
            base_logdir = os.path.expanduser('~/avocado')
        self.tagged_name = self.get_tagged_name(base_logdir)
        self.logdir = os.path.join(base_logdir, self.tagged_name)
        if not os.path.isdir(self.logdir):
            os.makedirs(self.logdir)
        self.logfile = os.path.join(self.logdir, 'debug.log')
        self.sysinfodir = os.path.join(self.logdir, 'sysinfo')

        self.log = logging.getLogger("avocado.test")

        self.debugdir = None
        self.resultsdir = None
        self.status = None
        self.fail_reason = None
        self.fail_class = None
        self.traceback = None
        self.text_output = None

        self.time_elapsed = None
        unittest.TestCase.__init__(self)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return "Test(%r)" % self.tagged_name

    def get_deps_path(self, basename):
        """
        Find a test dependency path inside the test depsdir.

        :param basename: Basename of the dep file. Ex: ``testsuite.tar.bz2``.

        :return: Path where dependency is supposed to be found.
        """
        return os.path.join(self.depsdir, basename)

    def start_logging(self):
        """
        Simple helper for adding a file logger to the root logger.
        """
        self.file_handler = logging.FileHandler(filename=self.logfile)
        self.file_handler.setLevel(logging.DEBUG)

        fmt = '%(asctime)s %(levelname)-5.5s| %(message)s'
        formatter = logging.Formatter(fmt=fmt, datefmt='%H:%M:%S')

        self.file_handler.setFormatter(formatter)
        self.log.addHandler(self.file_handler)

    def stop_logging(self):
        """
        Stop the logging activity of the test by cleaning the logger handlers.
        """
        self.log.removeHandler(self.file_handler)

    def get_tagged_name(self, logdir):
        """
        Get a test tagged name.

        If a test tag is defined, just return name.tag. If tag is absent,
        it'll try to find a tag that is not already taken (so there are no
        clashes in the results directory).

        :param logdir: Log directory being in use for result storage.

        :return: String `test.tag`.
        """
        if self.tag is not None:
            return "%s.%s" % (self.name, self.tag)
        tag = 1
        tagged_name = "%s.%s" % (self.name, tag)
        test_logdir = os.path.join(logdir, tagged_name)
        while os.path.isdir(test_logdir):
            tag += 1
            tagged_name = "%s.%s" % (self.name, tag)
            test_logdir = os.path.join(logdir, tagged_name)
        self.tag = str(tag)
        return tagged_name

    def setup(self):
        """
        Setup stage that the test needs before passing to the actual action.

        Must be implemented by tests if they want such an stage. Commonly we'll
        download/compile test suites, create files needed for a test, among
        other possibilities.
        """
        pass

    def action(self):
        """
        Actual test payload. Must be implemented by tests.

        In case of an existing test suite wrapper, it'll execute the suite,
        or perform a series of operations, and based in the results of the
        operations decide if the test pass (let the test complete) or fail
        (raise a test related exception).
        """
        raise NotImplementedError('Test subclasses must implement an action '
                                  'method')

    def cleanup(self):
        """
        Cleanup stage after the action is done.

        Examples of cleanup actions are deleting temporary files, restoring
        firewall configurations or other system settings that were changed
        in setup.
        """
        pass

    def runTest(self, result=None):
        """
        Run test method, for compatibility with unittest.TestCase.

        :result: Unused param, compatibiltiy with :class:`unittest.TestCase`.
        """
        sysinfo_logger = sysinfo.SysInfo(basedir=self.sysinfodir)
        self.start_logging()
        sysinfo_logger.start_job_hook()
        try:
            self.setup()
        except Exception, details:
            raise exceptions.TestSetupFail(details)
        self.action()
        self.cleanup()
        self.status = 'PASS'

    def run_avocado(self, result=None):
        """
        Wraps the runTest metod, for execution inside the avocado runner.

        :result: Unused param, compatibiltiy with :class:`unittest.TestCase`.
        """
        start_time = time.time()
        try:
            self.runTest(result)
        except exceptions.TestBaseException, detail:
            self.status = detail.status
            self.fail_class = detail.__class__.__name__
            self.fail_reason = detail
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_info = traceback.format_exception(exc_type, exc_value,
                                                 exc_traceback.tb_next)
            self.traceback = "".join(tb_info)
        except AssertionError, detail:
            self.status = 'FAIL'
            self.fail_class = detail.__class__.__name__
            self.fail_reason = detail
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_info = traceback.format_exception(exc_type, exc_value,
                                                 exc_traceback.tb_next)
            self.traceback = "".join(tb_info)
        except Exception, detail:
            self.status = 'FAIL'
            self.fail_class = detail.__class__.__name__
            self.fail_reason = detail
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_info = traceback.format_exception(exc_type, exc_value,
                                                 exc_traceback.tb_next)
            self.traceback = "".join(tb_info)
            for e_line in tb_info:
                self.log.error(e_line)
        finally:
            end_time = time.time()
            self.time_elapsed = end_time - start_time
            self.report()
            with open(self.logfile, 'r') as log_file_obj:
                self.text_output = log_file_obj.read()
            self.stop_logging()

    def report(self):
        """
        Report result to the logging system.
        """
        if self.fail_reason is not None:
            self.log.error("%s %s -> %s: %s", self.status,
                           self.tagged_name,
                           self.fail_reason.__class__.__name__,
                           self.fail_reason)

        else:
            self.log.info("%s %s", self.status,
                          self.tagged_name)


class DropinTest(Test):

    """
    Run an arbitrary command that returns either 0 (PASS) or !=0 (FAIL).
    """

    def __init__(self, path, base_logdir, tag=None):
        basename = os.path.basename(path)
        name = basename.split(".")[0]
        self.path = os.path.abspath(path)
        super(DropinTest, self).__init__(name=name, base_logdir=base_logdir,
                                         tag=tag)

    def _log_detailed_cmd_info(self, result):
        """
        Log detailed command information.

        :param result: :class:`avocado.utils.process.CmdResult` instance.
        """
        run_info = str(result)
        for line in run_info.splitlines():
            self.log.info(line)

    def action(self):
        """
        Run the executable, and log its detailed execution.
        """
        try:
            result = process.run(self.path, verbose=True)
            self._log_detailed_cmd_info(result)
        except exceptions.CmdError, details:
            self._log_detailed_cmd_info(details.result)
            raise exceptions.TestFail(details)
