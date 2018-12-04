# Base from https://github.com/gevent/gevent/blob/master/examples/psycopg2_pool.py
from __future__ import print_function
import sys
import contextlib

import gevent
from gevent.queue import Queue
from gevent.socket import wait_read, wait_write
from psycopg2 import extensions, OperationalError, connect
import time
from functools import wraps

DEBUG_STM = True
DEBUG_TIMING = True

import logging
logger = logging.getLogger(__name__)
debug = logger.debug
info = logger.info
warn = logger.warn
error = logger.error


def dbg_decorator(debug_stmt=True, measure_execution=True):
    def real_decorator(function):
        if not debug_stmt and not measure_execution:
            return function
        if not DEBUG_STM and not DEBUG_TIMING:
            return function
        
        @wraps(function)
        def wrapper(self, *args, **kwargs):
            dbg_str = function.__name__
            if DEBUG_STM and debug_stmt:
                dbg_str = '%s: Execute "%s"' % (dbg_str, self.mogrify(*args).decode("utf-8"))
            if DEBUG_TIMING and measure_execution:
                s = -time.time()
            retval = function(self, *args, **kwargs)
            if DEBUG_TIMING and measure_execution:
                s += time.time()
                dbg_str = "%s\tneeded %.4f seconds" % (dbg_str, s) 
            if DEBUG_TIMING or DEBUG_STM:
                info(dbg_str)
            return retval
        return wrapper
    return real_decorator



if sys.version_info[0] >= 3:
    integer_types = (int,)
else:
    import __builtin__
    integer_types = (int, __builtin__.long)


def gevent_wait_callback(conn, timeout=None):
    """A wait callback useful to allow gevent to work with Psycopg."""
    while 1:
        state = conn.poll()
        if state == extensions.POLL_OK:
            break
        elif state == extensions.POLL_READ:
            wait_read(conn.fileno(), timeout=timeout)
        elif state == extensions.POLL_WRITE:
            wait_write(conn.fileno(), timeout=timeout)
        else:
            raise OperationalError(
                "Bad result from poll: %r" % state)


extensions.set_wait_callback(gevent_wait_callback)


class AbstractDatabaseConnectionPool(object):

    def __init__(self, *args, maxsize=100, **kwargs):
        if not isinstance(maxsize, integer_types):
            raise TypeError('Expected integer, got %r' % (maxsize, ))
        self.maxsize = maxsize
        self.args = args
        self.kwargs = kwargs
        self.pool = Queue()
        self.size = 0

    def create_connection(self):
        return connect(*self.args, **self.kwargs)

    def get(self):
        pool = self.pool
        if self.size >= self.maxsize or pool.qsize():
            return pool.get()

        self.size += 1
        try:
            new_item = self.create_connection()
        except:
            self.size -= 1
            raise
        return new_item

    def put(self, item):
        self.pool.put(item)

    def closeall(self):
        while not self.pool.empty():
            conn = self.pool.get_nowait()
            try:
                conn.close()
            except Exception:
                pass

    def mogrify(self, *args, **kwargs):
        with self.cursor(**kwargs) as cur:
            return cur.mogrify(*args)

    @dbg_decorator(debug_stmt=False, measure_execution=True)
    @contextlib.contextmanager
    def connection(self, isolation_level=None):
        #if DEBUG: _t = - time.time() # TODO: nice way to check own logging.debuglevel ?
        conn = self.get()
        try:
            if isolation_level is not None:
                if conn.isolation_level == isolation_level:
                    isolation_level = None
                else:
                    conn.set_isolation_level(isolation_level)
            #if DEBUG: debug("Got connection in %.2f ms" % ((_t + time.time())*1000))
            yield conn
        except:
            if conn.closed:
                conn = None
                self.closeall()
            else:
                conn = self._rollback(conn)
            raise
        else:
            if conn.closed:
                raise OperationalError("Cannot commit because connection was closed: %r" % (conn, ))
            conn.commit()
        finally:
            if conn is not None and not conn.closed:
                if isolation_level is not None:
                    conn.set_isolation_level(isolation_level)
                self.put(conn)

    @contextlib.contextmanager
    def cursor(self, *args, **kwargs):
        isolation_level = kwargs.pop('isolation_level', None)
        with self.connection(isolation_level) as conn:
            yield conn.cursor(*args, **kwargs)

    def _rollback(self, conn):
        try:
            conn.rollback()
        except:
            gevent.get_hub().handle_error(conn, *sys.exc_info())
            return
        return conn

    @dbg_decorator()
    def execute(self, *args, **kwargs):
        with self.cursor(**kwargs) as cursor:
            cursor.execute(*args)
            return cursor.rowcount

    @dbg_decorator()
    def fetchone(self, *args, **kwargs):
        with self.cursor(**kwargs) as cursor:
            cursor.execute(*args)
            return cursor.fetchone()
    @dbg_decorator()
    def fetchall(self, *args, **kwargs):
        with self.cursor(**kwargs) as cursor:
            cursor.execute(*args)
            return cursor.fetchall()
        
    @dbg_decorator()
    def fetchiter(self, *args, **kwargs):
        with self.cursor(**kwargs) as cursor:
            cursor.execute(*args)
            while True:
                items = cursor.fetchmany()
                if not items:
                    break
                for item in items:
                    yield item





def main():
    import time
    pool = AbstractDatabaseConnectionPool("dbname=postgres", user="postgres", maxsize=3)
    start = time.time()
    for _ in range(4):
        gevent.spawn(pool.execute, 'select pg_sleep(1);')
    gevent.wait()
    delay = time.time() - start
    print('Running "select pg_sleep(1);" 4 times with 3 connections. Should take about 2 seconds: %.2fs' % delay)

if __name__ == '__main__':
    main()