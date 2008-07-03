

from eventlet import api, backdoor, coros, processes, util, wsgi
util.wrap_socket_with_coroutine_socket()
util.wrap_pipes_with_coroutine_pipes()
util.wrap_threading_local_with_coro_local()

import commands, errno, os, optparse, signal, socket, sys, time

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
            command = [sys.executable, new_script, '--fd=%s' % (sock.fileno(), )]
            if dev:
                command.append('--dev')
            command.append(factory_qual)
            command.append(simplejson.dumps(args))
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
    parser.add_option("-d", "--dev",
        action='store_true', dest='dev',
        help='If --dev is passed, reload the server any time '
        'a loaded module changes. Otherwise, only when the svn '
        'revision changes. Dev servers '
        'also run only one python process at a time.')
    parser.add_option('-f', '--fd', type='int', dest='fd',
        help='For internal use only')

    options, args = parser.parse_args()

    if len(args) < 2:
        print """Usage: %s factory_qual factory_args
    factory_qual: dotted path (eg mypackage.mymodule.myfunc) to callable which returns:
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

    factory_args: json object which will be passed to application factory.
        The boolean value of the --dev command line flag will be added as the
        'dev' key with a value of True or False.""" % (
            sys.argv[0], )
        sys.exit(1)

    factory_qual, factory_args = args
    factory_args = simplejson.loads(factory_args)
    factory_args['dev'] = options.dev

    if options.fd:
        sock = socket.fromfd(options.fd, socket.AF_INET, socket.SOCK_STREAM)
    else:
        sock = None

    run_controller(factory_qual, factory_args, sock)


if __name__ == '__main__':
    main()
