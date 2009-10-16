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


from eventlet import api

import errno, os, optparse, pprint, signal, socket, sys, time

import commands
import simplejson
import time
import traceback


KEEP_GOING = True
RESTART_CONTROLLER = False
PANIC = False


DEFAULTS = {
    'num_processes': 4,
    'threadpool_workers': 4,
    'watch': [],
    'dev': True,
    'host': '',
    'port': 8080,
    'deadman_timeout': 10,
    'max_memory': None,
}

def print_exc(msg="Exception occured!"):
    print >>sys.stderr, "(%d) %s" % (os.getpid(), msg)
    traceback.print_exc()

def environ():
    env = os.environ.copy()
    # to avoid duplicates in the new sys.path
    revised_paths = set()
    new_path = list()
    for path in sys.path:
        if os.path.exists(path) and path not in revised_paths:
            revised_paths.add(path)
            new_path.append(path)
    current_directory = os.path.realpath('.')
    if current_directory not in revised_paths:
        new_path.append(current_directory)

    env['PYTHONPATH'] = ':'.join(new_path)
    return env


def spawn_new_children(sock, factory_qual, args, config):
    num_processes = int(config.get('num_processes', 1))

    parent_pid = os.getpid()
    print "(%s) Spawning starting up: %s io processes, %s worker threads" % (
        parent_pid, num_processes, config['threadpool_workers'])

    if args.get('verbose'):
        print "(%s) serving wsgi with configuration:" % (
            os.getpid(), )
        prettyconfig = pprint.pformat(config)
        for line in prettyconfig.split('\n'):
            print "(%s)\t%s" % (os.getpid(), line)

    dev = args.get('dev', False)
    child_pipes = []
    for x in range(num_processes):
        child_side, parent_side = os.pipe()
        try:
            child_pid = os.fork()
        except:
            print_exc("Couldn't fork child! Panic!")
            restart_controller(factory_qual, args, sock, panic=True)
            ## Never gets here!

        if not child_pid:
            os.close(parent_side)
            command = [
                sys.executable,
                '-c', 'from  spawning import spawning_child;spawning_child.main();import os;os._exit(0)',
                str(parent_pid),
                str(sock.fileno()),
                str(child_side),
                factory_qual,
                simplejson.dumps(args)]

            if dev and x == 0:
                command.append('--reload')
            env = environ()
            env['EVENTLET_THREADPOOL_SIZE'] = str(config.get('threadpool_workers', 0))
            os.execve(sys.executable, command, env)

        os.close(child_side)
        child_pipes.append(parent_side)

    def sighup(_signum, _stack_frame):
        global RESTART_CONTROLLER
        RESTART_CONTROLLER = True

        tokill = child_pipes[:]
        del child_pipes[:]

        for child in tokill:
            try:
                os.write(child, ' ')
                os.close(child)
            except OSError, e:
                if e[0] != errno.EPIPE:
                    raise

    signal.signal(signal.SIGHUP, sighup)


def reap_children():
    global KEEP_GOING

    try:
        pid, result = os.wait()
    except OSError, e:
        if e.errno != errno.EINTR:
            raise
    except KeyboardInterrupt:
        print "(%s) Controller exiting at %s" % (
            os.getpid(), time.asctime())

        KEEP_GOING = False
        os.kill(os.getpid(), signal.SIGHUP)
        while True:
            ## Keep waiting until all children are dead.
            try:
                pid, result = os.wait()
            except OSError, e:
                if e[0] == errno.ECHILD:
                    break
    else:
        if result:
            signum = os.WTERMSIG(result)
            exitcode = os.WEXITSTATUS(result)

            if signum:
                print "(%s) Child died from signal %s with code %s." % (
                    os.getpid(), signum, exitcode)
            else:
                print "(%s) Child %s died with code %s." % (
                    os.getpid(), pid, exitcode)
            ## The way the code is set up right now it's easier just to panic and
            ## start new children if one of the children dies in a way we didn't expect.
            ## Would probably be better to give this code access to child_pipes
            ## in spawn_new_children somehow so it can just start a new child and munge
            ## child_pipes appropriately
            global PANIC
            PANIC = True
            print "(%s) !!! Panic: Why did that child die? Restarting" % (os.getpid(), )
            os.kill(os.getpid(), signal.SIGHUP)
        else:
            print "(%s) Child %s exited normally." % (
                os.getpid(), pid)


def bind_socket(config):
    sleeptime = 0.5
    host = config.get('host', '')
    port = config.get('port', 8080)
    for x in range(8):
        try:
            sock = api.tcp_listener((host, port))
            break
        except socket.error, e:
            if e[0] != errno.EADDRINUSE:
                raise
            print "(%s) socket %s:%s already in use, retrying after %s seconds..." % (
                os.getpid(), host, port, sleeptime)
            api.sleep(sleeptime)
            sleeptime *= 2
    else:
        print "(%s) could not bind socket %s:%s, dying." % (
            os.getpid(), host, port)
        sys.exit(1)
    return sock


def restart_controller(factory_qual, args, sock, panic=False):
    ## In case the installed copy of spawning has changed,
    ## execv spawn here so the controller process gets reloaded.

    ## We could somehow check to see if the spawning_controller
    ## actually is different from the current one and not restart the
    ## entire process in this case, which would result in faster restarts.
    ## But it's 'fast enough' for now.

    restart_args = dict(
        factory=factory_qual,
        factory_args=args)

    if sock is not None:
        restart_args['fd'] = sock.fileno()

    if panic:
        start_delay = args.get('start_delay')
        if start_delay is None:
            start_delay = 0.125
        else:
            start_delay *= 2
        restart_args['start_delay'] = start_delay

    os.execvpe(
        sys.executable,
        [sys.executable, '-c', 'from  spawning import spawning_controller;spawning_controller.main()', '-z', simplejson.dumps(restart_args)],
        environ())
    ## Never gets here!


def run_controller(factory_qual, args, sock=None):
    controller_pid = os.getpid()
    print "(%s) **** Controller starting up at %s" % (
        controller_pid, time.asctime())

    try:
        config = api.named(factory_qual)(args)
    except:
        print_exc("Couldn't import the WSGI factory! Panic!")
        restart_controller(factory_qual, args, sock, panic=True)
        ## Never gets here!

    pidfile = config.get("pidfile")
    if pidfile:
        try:
            f = open(pidfile, "w")
        except (IOError, OSError), e:
            print "(%s) Couldn't write pidfile, going on without it"
            traceback.print_exc()
        else:
            try:
                f.write("%s\n" % (controller_pid,))
            finally:
                f.close()

    dev = config.get('dev', False)
    if not dev:
        ## Set up the production reloader that watches the svn revision number.
        if not os.fork():
            if sock is not None:
                sock.close()
            base = os.path.dirname(__file__)
            os.chdir(base)
            args = [
                sys.executable,
                'reloader_svn.py',
                '--pid=' + str(controller_pid),
                '--dir=' + base,
            ]
            for dirname in config.get('source_directories', []):
                args.append('--dir=' + dirname)

            os.execve(sys.executable, args, environ())
            ## Never gets here!

    if sock is None:
        sock = bind_socket(config)

    spawn_new_children(sock, factory_qual, args, config)

    start_time = time.time()
    start_delay = args.get('start_delay')

    while True:
        reap_children()
        ## Random heuristic: If we've been running for 64x longer than the start_delay
        ## or 5 minutes, whatever is shorter, we can clear the start_delay
        if start_delay is not None:
            if time.time() - start_time > min(start_delay * 64, 60 * 5):
                print "(%s) We've been running OK for a while, clear the exponential backoff" % (
                    os.getpid(), )
                del args['start_delay']

        if RESTART_CONTROLLER:
            break

    if KEEP_GOING:
        restart_controller(factory_qual, args, sock, panic=PANIC)
        ## Never gets here!

def set_process_owner(spec):
    import pwd, grp
    if ":" in spec:
        user, group = spec.split(":", 1)
    else:
        user, group = spec, None
    if group:
        os.setgid(grp.getgrnam(group).gr_gid)
    if user:
        os.setuid(pwd.getpwnam(user).pw_uid)
    return user, group

def watch_memory(max_memory):
    process_group = os.getpgrp()
    while True:
        time.sleep(MEMORY_WATCH_INTERVAL)
        out = commands.getoutput('ps -o rss -g %s' % (process_group, ))
        if sum(int(x) for x in out.split('\n')[1:]) > max_memory:
            print "(%s) memory watcher restarting processes! Memory exceeded %s" % (
                os.getpid(), max_memory)
            os.kill(int(controller_pid), signal.SIGHUP)


def main():
    current_directory = os.path.realpath('.')
    if current_directory not in sys.path:
        sys.path.append(current_directory)

    parser = optparse.OptionParser(description="Spawning is an easy-to-use and flexible wsgi server. It supports graceful restarting so that your site finishes serving any old requests while starting new processes to handle new requests with the new code. For the simplest usage, simply pass the dotted path to your wsgi application: 'spawn my_module.my_wsgi_app'")
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true', help='Display verbose configuration '
        'information when starting up or restarting.')
    parser.add_option("-f", "--factory", dest='factory', default='spawning.wsgi_factory.config_factory',
        help="""Dotted path (eg mypackage.mymodule.myfunc) to a callable which takes a dictionary containing the command line arguments and figures out what needs to be done to start the wsgi application. Current valid values are: spawning.wsgi_factory.config_factory, spawning.paste_factory.config_factory, and spawning.django_factory.config_factory. The factory used determines what the required positional command line arguments will be. See the spawning.wsgi_factory module for documentation on how to write a new factory.
        """)
    parser.add_option("-i", "--host",
        dest='host', default=DEFAULTS['host'],
        help='The local ip address to bind.')
    parser.add_option("-p", "--port",
        dest='port', type='int', default=DEFAULTS['port'],
        help='The local port address to bind.')
    parser.add_option("-s", "--processes",
        dest='processes', type='int', default=DEFAULTS['num_processes'],
        help='The number of unix processes to start to use for handling web i/o.')
    parser.add_option("-t", "--threads",
        dest='threads', type='int', default=DEFAULTS['threadpool_workers'],
        help="The number of posix threads to use for handling web requests. "
            "If threads is 0, do not use threads but instead use eventlet's cooperative "
            "greenlet-based microthreads, monkeypatching the socket and pipe operations which normally block "
            "to cooperate instead. Note that most blocking database api modules will not "
            "automatically cooperate.")
    parser.add_option('-d', '--daemonize', dest='daemonize', action='store_true',
        help="Daemonize after starting children.")
    parser.add_option('-u', '--chuid', dest='chuid', metavar="ID",
        help="Change user ID in daemon mode (and group ID if given, "
             "separate with colon.)")
    parser.add_option('--pidfile', dest='pidfile', metavar="FILE",
        help="Write own process ID to FILE in daemon mode.")
    parser.add_option('--stdout', dest='stdout', metavar="FILE",
        help="Redirect stdout to FILE in daemon mode.")
    parser.add_option('--stderr', dest='stderr', metavar="FILE",
        help="Redirect stderr to FILE in daemon mode.")
    parser.add_option('-w', '--watch', dest='watch', action='append',
        help="Watch the given file's modification time. If the file changes, the web server will "
            'restart gracefully, allowing old requests to complete in the old processes '
            'while starting new processes with the latest code or configuration.')
    parser.add_option("-r", "--release",
        action='store_true', dest='release',
        help='If --release is passed, reload the server only when the svn '
        'revision changes. Otherwise, reload any time '
        'a loaded module or configuration file changes.')
    parser.add_option("--deadman", "--deadman_timeout",
        type='int', dest='deadman_timeout', default=DEFAULTS['deadman_timeout'],
        help='When killing an old i/o process because the code has changed, don\'t wait '
        'any longer than the deadman timeout value for the process to gracefully exit. '
        'If all requests have not completed by the deadman timeout, the process will be mercilessly killed.')
    parser.add_option('-l', '--access-log-file', dest='access_log_file', default=None,
        help='The file to log access log lines to. If not given, log to stdout. Pass /dev/null to discard logs.')
    parser.add_option('-c', '--coverage', dest='coverage', action='store_true',
        help='If given, gather coverage data from the running program and make the '
            'coverage report available from the /_coverage url. See the figleaf docs '
            'for more info: http://darcs.idyll.org/~t/projects/figleaf/doc/')
    parser.add_option('-m', '--max-memory', dest='max_memory', type='int', default=0,
        help='If given, the maximum amount of memory this instance of Spawning '
            'is allowed to use. If all of the processes started by this Spawning controller '
            'use more than this amount of memory, send a SIGHUP to the controller '
            'to get the children to restart.')
    parser.add_option('-a', '--max-age', dest='max_age', type='int',
        help='If given, the maximum amount of time (in seconds) an instance of spawning_child '
            'is allowed to run. Once this time limit has expired a SIGHUP will be sent to '
            'spawning_controller, causing it to restart all of the child processes.')
    parser.add_option('-z', '--z-restart-args', dest='restart_args',
        help='For internal use only')

    options, positional_args = parser.parse_args()

    if len(positional_args) < 1 and not options.restart_args:
        parser.error("At least one argument is required. "
            "For the default factory, it is the dotted path to the wsgi application "
            "(eg my_package.my_module.my_wsgi_application). For the paste factory, it "
            "is the ini file to load. Pass --help for detailed information about available options.")

    sock = None

    if options.restart_args:
        restart_args = simplejson.loads(options.restart_args)
        factory = restart_args['factory']
        factory_args = restart_args['factory_args']

        start_delay = restart_args.get('start_delay')
        if start_delay is not None:
            factory_args['start_delay'] = start_delay
            print "(%s) delaying startup by %s" % (os.getpid(), start_delay)
            time.sleep(start_delay)

        fd = restart_args.get('fd')
        if fd is not None:
            sock = socket.fromfd(restart_args['fd'], socket.AF_INET, socket.SOCK_STREAM)
            ## socket.fromfd doesn't result in a socket object that has the same fd.
            ## The old fd is still open however, so we close it so we don't leak.
            os.close(restart_args['fd'])
    else:
        ## We're starting up for the first time.
        if options.daemonize:
            # Do the daemon dance. Note that this isn't what is considered good
            # daemonization, because frankly it's convenient to keep the file
            # descriptiors open (especially when there are prints scattered all
            # over the codebase.)
            # What we do instead is fork off, create a new session, fork again.
            # This leaves the process group in a state without a session
            # leader.
            pid = os.fork()
            if not pid:
                os.setsid()
                pid = os.fork()
                if pid:
                    os._exit(0)
            else:
                os._exit(0)
            print "(%s) now daemonized" % (os.getpid(),)
            # Close _all_ open (and othewise!) files.
            import resource
            maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            if maxfd == resource.RLIM_INFINITY:
                maxfd = 4096
            for fdnum in xrange(maxfd):
                try:
                    os.close(fdnum)
                except OSError, e:
                    if e.errno != errno.EBADF:
                        raise
            # Remap std{in,out,err}
            devnull = os.open(os.path.devnull, os.O_RDWR)
            if devnull != 0:  # stdin
                os.dup2(devnull, 0)
            if options.stdout:
                stdout_fd = os.open(options.stdout, os.O_WRONLY | os.O_CREAT)
                if stdout_fd != 1:
                    os.dup2(stdout_fd, 1)
                    os.close(stdout_fd)
            else:
                os.dup2(devnull, 1)
            if options.stderr:
                stderr_fd = os.open(options.stderr, os.O_WRONLY | os.O_CREAT)
                if stderr_fd != 2:
                    os.dup2(stderr_fd, 2)
                    os.close(stderr_fd)
            else:
                os.dup2(devnull, 2)
            # Change user & group ID.
            if options.chuid:
                user, group = set_process_owner(options.chuid)
                print "(%s) set user=%s group=%s" % (os.getpid(), user, group)
        else:
            # Become a process group leader only if not daemonizing.
            os.setpgrp()

        ## Fork off the thing that watches memory for this process group.
        controller_pid = os.getpid()
        if (options.max_memory or options.max_age) and not os.fork():
            env = environ()
            from spawning import memory_watcher
            basedir, cmdname = os.path.split(memory_watcher.__file__)
            if cmdname.endswith('.pyc'):
                cmdname = cmdname[:-1]

            os.chdir(basedir)
            command = [
                sys.executable,
                cmdname,
                '--max-age', str(options.max_age),
                str(controller_pid),
                str(options.max_memory)]
            os.execve(sys.executable, command, env)

        factory = options.factory
        factory_args = {
            'verbose': options.verbose,
            'host': options.host,
            'port': options.port,
            'num_processes': options.processes,
            'threadpool_workers': options.threads,
            'watch': options.watch,
            'dev': not options.release,
            'deadman_timeout': options.deadman_timeout,
            'access_log_file': options.access_log_file,
            'pidfile': options.pidfile,
            'coverage': options.coverage,
            'args': positional_args,
        }

    run_controller(factory, factory_args, sock)


if __name__ == '__main__':
    main()



