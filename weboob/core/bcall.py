# -*- coding: utf-8 -*-

# Copyright(C) 2010-2014 Romain Bignon, Christophe Benz
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.


from multiprocessing.pool import ThreadPool
from copy import copy
from threading import Thread
import Queue

from weboob.capabilities.base import CapBaseObject
from weboob.tools.misc import get_backtrace
from weboob.tools.log import getLogger


__all__ = ['BackendsCall', 'CallErrors']


class CallErrors(Exception):
    def __init__(self, errors):
        msg = 'Errors during backend calls:\n' + \
                '\n'.join(['Module(%r): %r\n%r\n' % (backend, error, backtrace)
                           for backend, error, backtrace in errors])

        Exception.__init__(self, msg)
        self.errors = copy(errors)

    def __iter__(self):
        return self.errors.__iter__()


class BackendsCall(object):
    def __init__(self, backends, function, *args, **kwargs):
        """
        :param backends: List of backends to call
        :type backends: list[:class:`BaseBackend`]
        :param function: backends' method name, or callable object.
        :type function: :class:`str` or :class:`callable`
        """
        self.logger = getLogger('bcall')
        # Waiting responses
        self.responses = Queue.Queue()
        # Threads
        self.threads = ThreadPool(len(backends))
        self.backends = [(backend, function, args, kwargs) for backend in backends]

    def store_result(self, backend, result):
        if isinstance(result, CapBaseObject):
            result.backend = backend.name
        self.responses.put((backend, result))

    def _caller(self, args):
        return self.backend_thread(*args)

    def backend_thread(self, backend, function, args, kwargs):
        with backend:
            try:
                # Call method on backend
                try:
                    self.logger.debug('%s: Calling function %s' % (backend, function))
                    if callable(function):
                        result = function(backend, *args, **kwargs)
                    else:
                        result = getattr(backend, function)(*args, **kwargs)
                except Exception as error:
                    self.logger.debug('%s: Called function %s raised an error: %r' % (backend, function, error))
                    return backend, error, get_backtrace(error)
                else:
                    self.logger.debug('%s: Called function %s returned: %r' % (backend, function, result))

                    if hasattr(result, '__iter__') and not isinstance(result, basestring):
                        # Loop on iterator
                        try:
                            for subresult in result:
                                # Lock mutex only in loop in case the iterator is slow
                                # (for example if backend do some parsing operations)
                                self.store_result(backend, subresult)
                        except Exception as error:
                            return backend, error, get_backtrace(error)
                    else:
                        self.store_result(backend, result)
            finally:
                # This backend is now finished
                #self.response_event.set()
                #self.finish_event.set()
                pass

    def _callback_thread_run(self, callback, errback):
        r = self.threads.map_async(self._caller, self.backends)

        while not r.ready() or not self.responses.empty():
            try:
                callback(*self.responses.get(timeout=0.1))
            except Queue.Empty:
                continue

        # Raise errors
        errors = get_errors(r)
        while errors:
            errback(*errors.pop(0))

        callback(None, None)

    def callback_thread(self, callback, errback=None):
        """
        Call this method to create a thread which will callback a
        specified function everytimes a new result comes.

        When the process is over, the function will be called with
        both arguments set to None.

        The functions prototypes:
            def callback(backend, result)
            def errback(backend, error)

        """
        thread = Thread(target=self._callback_thread_run, args=(callback, errback))
        thread.start()
        return thread

    def wait(self):
        r = self.threads.map(self._caller, self.backends)

        errors = get_errors(r)
        if errors:
            raise CallErrors(errors)

    def __iter__(self):
        r = self.threads.map_async(self._caller, self.backends)

        while not r.ready() or not self.responses.empty():
            try:
                yield self.responses.get(timeout=0.1)
            except Queue.Empty:
                continue

        errors = get_errors(r)
        if errors:
            raise CallErrors(errors)

def get_errors(r):
    return [e for e in r.get() if e is not None]
