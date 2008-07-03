"""Watch files and send a SIGHUP signal to another process
if any of the files change.
"""


import optparse, os, sets, signal, sys, tempfile, time
from os.path import join
from distutils import sysconfig

from eventlet import api, coros, jsonhttp

import simplejson


def watch_forever(urls, pid, interval, files=None):
    """
    """
    limiter = coros.CoroutinePool(track_events=True)
    module_mtimes = {}
    last_changed_time = None
    while True:
        uniques = sets.Set()

        if urls:
            for url in urls:
                limiter.execute(jsonhttp.get, url)
    
            for i in range(len(urls)):
                uniques.update(limiter.wait()['files'])
        else:
            uniques.add(join(sysconfig.get_python_lib(), 'easy-install.pth'))
            uniques.update(list(get_sys_modules_files()))

        if files:
            uniques.update(files)

        changed = False
        for filename in uniques:
            try:
                stat = os.stat(filename)
                if stat:
                    mtime = stat.st_mtime
                else:
                    mtime = 0
            except (OSError, IOError):
                continue
            if filename.endswith('.pyc') and os.path.exists(filename[:-1]):
                mtime = max(os.stat(filename[:-1]).st_mtime, mtime)
            if not module_mtimes.has_key(filename):
                module_mtimes[filename] = mtime
            elif module_mtimes[filename] < mtime:
                changed = True
                last_changed_time = mtime
                module_mtimes[filename] = mtime
                print "(%s) File %r changed" % (os.getpid(), filename)

        if not changed and last_changed_time is not None:
            last_changed_time = None
            if pid:
                print "(%s) ** Sending SIGHUP to %s at %s" % (
                    os.getpid(), pid, time.asctime())
                os.kill(pid, signal.SIGHUP)
                return ## this process is going to die now, no need to keep watching
            else:
                os._exit(3)

        api.sleep(interval)


def get_sys_modules_files():
    for module in sys.modules.values():
        fn = getattr(module, '__file__', None)
        if fn is not None:
            yield os.path.abspath(fn)


def main():
    parser = optparse.OptionParser()
    parser.add_option("-u", "--url",
        action="append", dest="urls",
        help="A url to GET for a JSON object with a key 'files' of filenames to check. "
        "If not given, use the filenames of everything in sys.modules.")
    parser.add_option("-p", "--pid",
        type="int", dest="pid",
        help="A pid to SIGHUP when a monitored file changes. "
        "If not given, just print a message to stdout and kill this process instead.")
    parser.add_option("-i", "--interval",
        type="int", dest="interval",
        help="The time to wait between scans, in seconds.", default=1)
    options, args = parser.parse_args()

    try:
        watch_forever(options.urls, options.pid, options.interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

