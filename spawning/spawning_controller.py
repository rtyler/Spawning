

from eventlet import api, backdoor, coros, util, wsgi
util.wrap_socket_with_coroutine_socket()
util.wrap_pipes_with_coroutine_pipes()
util.wrap_threading_local_with_coro_local()


import errno, os, optparse, signal, sys, time

from paste.deploy import loadwsgi


KEEP_GOING = True


def spawn_new_children(sock, base_dir, config_url, dev, num_processes):
    child_pipes = []
    parent_pid = os.getpid()
    for x in range(num_processes):
        child_side, parent_side = os.pipe()
        if not os.fork():
            os.close(parent_side)
            args = [
                sys.executable,
                os.path.join(
                    os.path.split(os.path.abspath(__file__))[0],
                    'spawning_child.py'),
                str(parent_pid),
                config_url,
                base_dir,
                str(sock.fileno()),
                str(child_side)]

            if dev:
                args.append('--dev')

            os.execve(sys.executable, args, {'PYTHONPATH': os.environ.get('PYTHONPATH', '')})
            ## Never gets here!

    os.close(child_side)
    child_pipes.append(parent_side)

    def sighup(_signum, _stack_frame):
        tokill = child_pipes[:]
        del child_pipes[:]

        if KEEP_GOING:
            spawn_new_children(sock, base_dir, config_url, dev)

        for child in tokill:
            os.write(child, ' ')

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


def run_controller(base_dir, config_url, dev=False, num_processes=1):
    print "(%s) Controller starting up at %s" % (
        os.getpid(), time.asctime())

    controller_pid = os.getpid()
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
            os.execve(sys.executable, args, {'PYTHONPATH': os.environ.get('PYTHONPATH', '')})
            ## Never gets here!

    ctx = loadwsgi.loadcontext(
        loadwsgi.SERVER,
        config_url, relative_to=base_dir)

    sock = api.tcp_listener(
        (ctx.local_conf['host'], int(ctx.local_conf['port'])))
    spawn_new_children(sock, base_dir, config_url, dev, num_processes)

    while KEEP_GOING:
        reap_children()


def server_factory(global_conf, host, port, *args, **kw):
    config_name = 'config:' + os.path.split(
        global_conf['__file__'])[1]
    base_dir = global_conf['here']
    def run(app):
        run_controller(
            base_dir,
            config_name,
            global_conf.get('debug') == 'true',
            int(global_conf.get('num_processes', 1)))
    return run


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option("-d", "--dev",
        action='store_true', dest='dev',
        help='If --dev is passed, reload the server any time '
        'a loaded module changes. Otherwise, only when the svn '
        'revision changes. Dev servers '
        'also run only one python process at a time.')

    options, args = parser.parse_args()

    if len(args) < 2:
        print "Usage: %s config_url base_dir" % (
            sys.argv[0], )
        sys.exit(1)

    config_url, base_dir = args
    run_controller(base_dir, config_url, options.dev)

