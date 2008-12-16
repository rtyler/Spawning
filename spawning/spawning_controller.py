

from eventlet import api

import errno, os, optparse, pprint, signal, socket, sys, time

import commands
import simplejson

from spawning import spawning_child


KEEP_GOING = True
RESTART_CONTROLLER = False


DEFAULTS = {
    'num_processes': 1,
    'threadpool_workers': 10, 
    'processpool_workers': 0,
    'watch': [],
    'dev': True,
    'host': '',
    'port': 8080,
    'deadman_timeout': 120,
}


def environ():
    env = os.environ.copy()
    env['PYTHONPATH'] = os.environ.get('PYTHONPATH', '')
    return env


def spawn_new_children(sock, factory_qual, args, config):
    num_processes = int(config.get('num_processes', 1))

    parent_pid = os.getpid()
    print "(%s) spawning %s children with %s" % (
        parent_pid, num_processes, spawning_child.__file__)

    print "(%s) serving wsgi with configuration:" % (
        os.getpid(), )
    prettyconfig = pprint.pformat(config)
    for line in prettyconfig.split('\n'):
        print "(%s)\t%s" % (os.getpid(), line)

    dev = args.get('dev', False)
    child_pipes = []
    for x in range(num_processes):
        child_side, parent_side = os.pipe()
        if not os.fork():
            os.close(parent_side)
            command = [
                sys.executable,
                spawning_child.__file__,
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
    except OSError: # "Interrupted System Call"
        pass
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
            print "(%s) Child %s died with code %s (%s)." % (
                os.getpid(), pid, result, errno.errorcode.get(result, '?'))
            ## The way the code is set up right now it's easier just to panic and
            ## start new children if one of the children dies in a way we didn't expect.
            ## Would probably be better to give this code access to child_pipes
            ## in spawn_new_children somehow so it can just start a new child and munge
            ## child_pipes appropriately
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


def run_controller(factory_qual, args, sock=None):
    controller_pid = os.getpid()
    print "(%s) **** Controller starting up at %s" % (
        controller_pid, time.asctime())

    config = api.named(factory_qual)(args)

    dev = config.get('dev', False)
    if not dev:
        ## Set up the production reloader that watches the svn revision number.
        if not os.fork():
            base = os.path.split(__file__)[0]
            args = [
                sys.executable,
                os.path.join(
                    base, 'reloader_svn.py'),
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

    while True:
        reap_children()
        if RESTART_CONTROLLER:
            break

    if KEEP_GOING:
        ## In case the installed copy of spawning has changed, 
        ## execv spawn here so the controller process gets reloaded.

        ## We could somehow check to see if the spawning_controller
        ## actually is different from the current one and not restart the
        ## entire process in this case, which would result in faster restarts.
        ## But it's 'fast enough' for now.

        restart_args = dict(
            factory=factory_qual,
            factory_args=args,
            fd=sock.fileno())

        env = '/usr/bin/env'
        os.execve(
            env,
            [env, 'spawn', '-z', simplejson.dumps(restart_args)],
            environ())
        ## Never gets here!


def main():
    parser = optparse.OptionParser(description="Spawning is an easy-to-use and flexible wsgi server. It supports graceful restarting so that your site finishes serving any old requests while starting new processes to handle new requests with the new code. For the simplest usage, simply pass the dotted path to your wsgi application: 'spawn my_module.my_wsgi_app'")
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
    parser.add_option("-o", "--workers",
        dest='workers', type='int', default=DEFAULTS['processpool_workers'],
        help='The number of unix worker processes to start to execute the wsgi application in. If defined, this overrides --threads and no posix threads are used.')
    parser.add_option("-t", "--threads",
        dest='threads', type='int', default=DEFAULTS['threadpool_workers'],
        help="The number of posix threads to use for handling web requests. "
            "If threads is 0, do not use threads but instead use eventlet's cooperative "
            "greenlet-based microthreads, monkeypatching the socket and pipe operations which normally block "
            "to cooperate instead. Note that most blocking database api modules will not "
            "automatically cooperate.")
    parser.add_option('-w', '--watch', dest='watch', action='append',
        help="Watch the given file's modification time. If the file changes, the web server will "
            'restart gracefully, allowing old requests to complete in the old processes '
            'while starting new processes with the latest code or configuration.')
    parser.add_option("-r", "--release",
        action='store_true', dest='release',
        help='If --release is passed, reload the server only when the svn '
        'revision changes. Otherwise, reload any time '
        'a loaded module or configuration file changes.')
    parser.add_option("-d", "--deadman_timeout",
        type='int', dest='deadman_timeout', default=DEFAULTS['deadman_timeout'],
        help='When killing an old i/o process because the code has changed, don\'t wait '
        'any longer than the deadman timeout value for the process to gracefully exit. '
        'If all requests have not completed by the deadman timeout, the process will be mercilessly killed.')
    parser.add_option('-z', '--z-restart-args', dest='restart_args',
        help='For internal use only')

    options, positional_args = parser.parse_args()

    if len(positional_args) < 1 and not options.restart_args:
        parser.error("At least one argument is required. "
            "For the default factory, it is the dotted path to the wsgi application "
            "(eg my_package.my_module.my_wsgi_application). For the paste factory, it "
            "is the ini file to load. Pass --help for detailed information about available options.")

    if options.restart_args:
        restart_args = simplejson.loads(options.restart_args)
        factory = restart_args['factory']
        factory_args = restart_args['factory_args']
        sock = socket.fromfd(restart_args['fd'], socket.AF_INET, socket.SOCK_STREAM)
        ## socket.fromfd doesn't result in a socket object that has the same fd.
        ## The old fd is still open however, so we close it so we don't leak.
        os.close(restart_args['fd'])
    else:
        factory = options.factory
        factory_args = {
            'host': options.host,
            'port': options.port,
            'num_processes': options.processes,
            'processpool_workers': options.workers,
            'threadpool_workers': options.threads,
            'watch': options.watch,
            'dev': not options.release,
            'deadman_timeout': options.deadman_timeout,
            'args': positional_args,
        }
        sock = None

    run_controller(factory, factory_args, sock)


if __name__ == '__main__':
    main()



