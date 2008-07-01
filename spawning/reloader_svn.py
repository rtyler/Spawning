"""Watch the svn revision returned from svn info and send a SIGHUP
to a process when the revision changes.
"""


import commands, optparse, os, signal, sys, tempfile, time


def get_revision(directory):
    cmd = 'svn info'
    if directory is not None:
        cmd = '%s %s' % (cmd, directory)

    try:
        out = commands.getoutput(cmd).split('\n')
    except IOError:
        return

    for line in out:
        if line.startswith('Revision: '):
            return int(line[len('Revision: '):])


def watch_forever(directory, pid, interval):
    """
    """
    revision = get_revision(directory)
    while True:
        new_revision = get_revision(directory)
        if new_revision is not None and new_revision != revision:
            revision = new_revision
            if pid:
                ## This is stupid: Since we can't tell whether the ini file changed
                ## and paste makes it a pain to re-parse the ini file,
                ## we just terminate the controller when running with the svn reloader.
                ## There will be a short period when the socket is not accepting,
                ## causing refused connections.
                print "(%s) Sending SIGTERM to %s at %s" % (
                    os.getpid(), pid, time.asctime())
                os.kill(pid, signal.SIGTERM)     
            else:
                print "(%s) Revision changed, dying at %s" % (
                    os.getpid(), time.asctime())
                os._exit(3)

        time.sleep(interval)


def main():
    parser = optparse.OptionParser()
    parser.add_option("-d", "--dir", dest='dir',
        help="The directory to do svn info in. If not given, use cwd.")
    parser.add_option("-p", "--pid",
        type="int", dest="pid",
        help="A pid to SIGHUP when the svn revision changes. "
        "If not given, just print a message to stdout and kill this process instead.")
    parser.add_option("-i", "--interval",
        type="int", dest="interval",
        help="The time to wait between scans, in seconds.", default=10)
    options, args = parser.parse_args()

    print "(%s) svn watcher running, controller pid %s" % (os.getpid(), options.pid)
    if options.pid is None:
        options.pid = os.getpid()
    try:
        watch_forever(options.dir, int(options.pid), options.interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

