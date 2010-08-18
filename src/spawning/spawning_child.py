#!/usr/bin/env python
# Copyright (c) 2008, Donovan Preston
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""spawning_child.py
"""

import eventlet
import eventlet.event
import eventlet.greenio
import eventlet.hubs
import eventlet.wsgi

import errno
import optparse
import os
import signal
import socket
import sys
import time

import spawning.util
from spawning import setproctitle, reloader_dev

try:
    import json
except ImportError:
    import simplejson as json

class FigleafCoverage(object):
    def __init__(self, app):
        import figleaf

        self.app = app
        figleaf.start()

    def __call__(self, env, start_response):
        import figleaf
        try:
            import cPickle as pickle
        except ImportError:
            import pickle

        if env['PATH_INFO'] == '/_coverage':
            coverage = figleaf.get_info()
            s = pickle.dumps(coverage)
            start_response("200 OK", [('Content-type', 'application/x-pickle')])
            return [s]
        return self.app(env, start_response)


class ExitChild(Exception):
    pass

def read_pipe_and_die(the_pipe, server_coro):
    try:
        eventlet.hubs.trampoline(the_pipe, read=True)
        os.read(the_pipe, 1)
    except socket.error:
        pass
    try:
        os.close(the_pipe)
    except socket.error:
        pass
    return server_coro.throw(ExitChild)


def deadman_timeout(signum, frame):
    print "(%s) !!! Deadman timer expired, killing self with extreme prejudice" % (
        os.getpid(), )
    os.kill(os.getpid(), signal.SIGKILL)

def tpool_wsgi(app):
    from eventlet import tpool
    def tpooled_application(e, s):
        result = tpool.execute(app, e, s)
        # return builtins directly
        if isinstance(result, (basestring, list, tuple)):
            return result
        else:
            # iterators might execute code when iterating over them,
            # so we wrap them in a Proxy object so every call to
            # next() goes through tpool
            return tpool.Proxy(result)
    return tpooled_application


def serve_from_child(sock, config, controller_pid):
    threads = config.get('threadpool_workers', 0)
    wsgi_application = spawning.util.named(config['app_factory'])(config)

    if config.get('coverage'):
        wsgi_application = FigleafCoverage(wsgi_application)

    if threads > 1:
        # proxy calls of the application through tpool
        wsgi_application = tpool_wsgi(wsgi_application)
    elif threads != 1:
        print "(%s) not using threads, installing eventlet cooperation monkeypatching" % (
            os.getpid(), )
        eventlet.patcher.monkey_patch(all=False, socket=True)

    host, port = sock.getsockname()

    access_log_file = config.get('access_log_file')
    if access_log_file is not None:
        access_log_file = open(access_log_file, 'a')

    max_age = 0
    if config.get('max_age'):
        max_age = int(config.get('max_age'))

    server_event = eventlet.event.Event()
    http_version = config.get('no_keepalive') and 'HTTP/1.0' or 'HTTP/1.1'
    try:
        wsgi_args = (sock, wsgi_application)
        wsgi_kwargs = {'log' : access_log_file, 'server_event' : server_event, 'max_http_version' : http_version}
        if config.get('no_keepalive'):
            wsgi_kwargs.update({'keepalive' : False})
        if max_age:
            wsgi_kwargs.update({'timeout_value' : True})
            eventlet.with_timeout(max_age, eventlet.wsgi.server, *wsgi_args,
                    **wsgi_kwargs)
        else:
            eventlet.wsgi.server(*wsgi_args, **wsgi_kwargs)
    except KeyboardInterrupt:
        pass
    except ExitChild:
        pass

    ## Set a deadman timer to violently kill the process if it doesn't die after
    ## some long timeout.
    signal.signal(signal.SIGALRM, deadman_timeout)
    signal.alarm(config['deadman_timeout'])

    ## Once we get here, we just need to handle outstanding sockets, not
    ## accept any new sockets, so we should close the server socket.
    sock.close()

    server = server_event.wait()

    last_outstanding = None
    if server.outstanding_requests:
        ## Let's tell our parent that we're dying
        try:
            os.kill(controller_pid, signal.SIGUSR1)
        except OSError, e:
            if not e.errno == errno.ESRCH:
                raise

    while server.outstanding_requests:
        if last_outstanding != server.outstanding_requests:
            print "(%s) %s requests remaining, waiting... (timeout after %s)" % (
                os.getpid(), server.outstanding_requests, config['deadman_timeout'])
        last_outstanding = server.outstanding_requests
        eventlet.sleep(0.1)

    print "(%s) *** Child exiting: all requests completed at %s" % (
        os.getpid(), time.asctime())

def main():
    parser = optparse.OptionParser()
    parser.add_option("-r", "--reload",
        action='store_true', dest='reload',
        help='If --reload is passed, reload the server any time '
        'a loaded module changes.')

    options, args = parser.parse_args()

    if len(args) != 5:
        print "Usage: %s controller_pid httpd_fd death_fd factory_qual factory_args" % (
            sys.argv[0], )
        sys.exit(1)

    controller_pid, httpd_fd, death_fd, factory_qual, factory_args = args
    controller_pid = int(controller_pid)
    config = spawning.util.named(factory_qual)(json.loads(factory_args))

    setproctitle("spawn: child (%s)" % ", ".join(config.get("args")))

    ## Set up the reloader
    if config.get('reload'):
        watch = config.get('watch', None)
        if watch:
            watching = ' and %s' % watch
        else:
            watching = ''
        print "(%s) reloader watching sys.modules%s" % (os.getpid(), watching)
        eventlet.spawn(
            reloader_dev.watch_forever, controller_pid, 1, watch)

    ## The parent will catch sigint and tell us to shut down
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    ## Expect a SIGHUP when we want the child to die
    signal.signal(signal.SIGHUP, lambda *a, **kw: exit(0))
    eventlet.spawn(read_pipe_and_die, int(death_fd), eventlet.getcurrent())

    ## Make the socket object from the fd given to us by the controller
    sock = eventlet.greenio.GreenSocket(
        socket.fromfd(int(httpd_fd), socket.AF_INET, socket.SOCK_STREAM))

    serve_from_child(
        sock, config, controller_pid)

if __name__ == '__main__':
    main()
