

from eventlet import api, backdoor, coros, processes, util, wsgi
util.wrap_socket_with_coroutine_socket()
util.wrap_pipes_with_coroutine_pipes()
util.wrap_threading_local_with_coro_local()

import commands, errno, os, optparse, pprint, signal, socket, sys, time

import simplejson

from spawning import spawning_child


KEEP_GOING = True
EXIT_ARGUMENTS = None


def environ():
    env = os.environ.copy()
    env['PYTHONPATH'] = os.environ.get('PYTHONPATH', '')
    return env


def spawn_new_children(sock, factory_qual, args, config):
    num_processes = int(config.get('num_processes', 1))

    parent_pid = os.getpid()
    print "(%s) spawning %s children with %s" % (parent_pid, num_processes, spawning_child.__file__)

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

            if x == 0:
                command.append('--reload')
            env = environ()
            env['EVENTLET_THREADPOOL_SIZE'] = str(config.get('threadpool_workers', 0))
            os.execve(sys.executable, command, env)

        os.close(child_side)
        child_pipes.append(parent_side)

    def sighup(_signum, _stack_frame):
        global EXIT_ARGUMENTS
        tokill = child_pipes[:]
        del child_pipes[:]

        for child in tokill:
            os.write(child, ' ')

        if KEEP_GOING:
            ## In case the installed copy of spawning has changed, get the name of
            ## spawning_controller from a fresh copy of python and then execve it.
            proc = processes.Process('python', [])
            proc.write('from pkg_resources import load_entry_point\n')
            proc.write("print load_entry_point('Spawning', 'console_scripts', 'spawn').func_code.co_filename")
            proc.close_stdin()
            new_script = proc.read().strip()
            command = [sys.executable, new_script]
            command.extend(sys.argv[1:])
            for arg in command:
                if arg.startswith('--fd='):
                    break
            else:
                command.append('--fd=%s' % (sock.fileno(), ))
            
            EXIT_ARGUMENTS = command

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
        print "(%s) Child %s died with code %s." % (
            os.getpid(), pid, result)


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
            controller_pid, host, port)
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
                '--dir=' + base,
                '--pid=' + str(controller_pid)]
            os.execve(sys.executable, args, environ())
            ## Never gets here!

    if sock is None:
        sock = bind_socket(config)

    spawn_new_children(sock, factory_qual, args, config)

    while KEEP_GOING:
        reap_children()
        if EXIT_ARGUMENTS:
            from eventlet import tpool
            tpool.killall()
            while True:
                try:
                    os.execve(sys.executable, EXIT_ARGUMENTS, environ())
                    ## Never gets here!
                except OSError:
                    ## There is a possibility killall will return before all threads are
                    ## killed, causing execve to raise an exception. In this case we just
                    ## keep trying until the threads have exited.
                    pass


def main():
    parser = optparse.OptionParser()
    parser.add_option("-f", "--factory", dest='factory', default='spawning.wsgi_factory.config_factory',
        help="""dotted path (eg mypackage.mymodule.myfunc) to callable which returns:
        {'host': ..., 'port': ..., 'app_factory': ...,
        'num_processes': ..., 'num_threads': ..., 'dev': ..., 'watch': [...]}
            host: The local ip to bind to.
            port: The local port to bind to.
            app_factory: The dotted path to the wsgi application factory.
                Will be called with the result of factory_qual as the argument.
            num_processes: The number of processes to spawn.
            num_threads: The number of threads to use in the threadpool in each process.
                If 0, install the eventlet monkeypatching and do not use the threadpool.
                Code which blocks instead of cooperating will block the process, possibly
                causing stalls. (TODO sigalrm?)
            dev: If True, watch all files in sys.modules, easy-install.pth, and any additional
                file paths in the 'watch' list for changes and restart child
                processes on change. If False, only reload if the svn revision of the
                current directory changes.
            watch: List of additional files to watch for changes and reload when changed.

        The default config factory, spawning.wsgi_factory.config_factory, takes all of these arguments
        from the args specified on the command line. It also requires a positional argument, the
        dotted path to the wsgi application to serve. Example:

            spawn my_package.my_module.my_wsgi_app

        The paste config factory, spawning.paste_factory.config_factory, takes all of these
        arguments from a standard paste .ini file. It ignores the command-line arguments.
        It requires a positional argument, the name of the ini file to load. Example:

            spawn --factory=spawning.paste_factory.config_factory development.ini
        """)
    parser.add_option("-i", "--host",
        dest='host', default='',
        help='The local ip address to bind.')
    parser.add_option("-p", "--port",
        dest='port', type='int', default=8080,
        help='The local port address to bind.')
    parser.add_option("-s", "--processes",
        dest='processes', type='int', default=1,
        help='The number of unix processes to start to use for handling web requests.')
    parser.add_option("-t", "--threads",
        dest='threads', type='int', default=4,
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
    parser.add_option('-z', '--fd', type='int', dest='fd',
        help='For internal use only')

    options, positional_args = parser.parse_args()

    if len(positional_args) < 1:
        parser.error("At least one argument is required. "
            "For the default factory, it is the dotted path to the wsgi application "
            "(eg my_package.my_module.my_wsgi_application). For the paste factory, it "
            "is the ini file to load.")

    factory_args = {
        'host': options.host,
        'port': options.port,
        'num_processes': options.processes,
        'threadpool_workers': options.threads,
        'watch': options.watch,
        'dev': not options.release,
        'args': positional_args
    }

    if options.fd:
        sock = socket.fromfd(options.fd, socket.AF_INET, socket.SOCK_STREAM)
    else:
        sock = None

    run_controller(options.factory, factory_args, sock)


if __name__ == '__main__':
    main()
