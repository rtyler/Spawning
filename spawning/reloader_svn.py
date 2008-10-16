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


def watch_forever(directories, pid, interval):
    """
    """
    ## Look for externals
    all_svn_repos = set(directories)

    def visit(parent, subdirname, children):
        if '.svn' in children:
            children.remove('.svn')
        out = commands.getoutput('svn propget svn:externals %s' % (subdirname, ))
        for line in out.split('\n'):
            line = line.strip()
            if line and 'is not a working copy' not in line:
                name, _external_url = line.split()
                fulldir = os.path.join(parent, subdirname, name)
                ## Don't keep going into the external in the walk()
                children.remove(name)
                directories.append(fulldir)
                all_svn_repos.add(fulldir)

    while directories:
        dirname = directories.pop(0)
        os.path.walk(dirname, visit, dirname)

    revisions = {}
    for dirname in all_svn_repos:
        revisions[dirname] = get_revision(dirname)

    print "(%s) svn watcher watching directories: %s" % (
        os.getpid(), list(all_svn_repos))

    while True:
        for dirname in all_svn_repos:
            new_revision = get_revision(dirname)

            if new_revision is not None and new_revision != revisions[dirname]:
                revisions[dirname] = new_revision
                if pid:
                    print "(%s) SVN revision changed on %s to %s; Sending SIGHUP to %s at %s" % (
                        os.getpid(), dirname, new_revision, pid, time.asctime())
                    os.kill(pid, signal.SIGHUP)
                    os._exit(0)
                else:
                    print "(%s) Revision changed, dying at %s" % (
                        os.getpid(), time.asctime())
                    os._exit(3)

        time.sleep(interval)


def main():
    parser = optparse.OptionParser()
    parser.add_option("-d", "--dir", dest='dirs', action="append",
        help="The directories to do svn info in. If not given, use cwd.")
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
        watch_forever(options.dirs, int(options.pid), options.interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

