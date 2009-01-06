
import commands
import os
import optparse
import signal
import sys
import time


MEMORY_WATCH_INTERVAL = 60


def watch_memory(controller_pid, max_memory):
    process_group = os.getpgrp()
    while True:
        time.sleep(MEMORY_WATCH_INTERVAL)
        out = commands.getoutput('ps -o rss -g %s' % (process_group, ))
        used_mem = sum(int(x) for x in out.split('\n')[1:])
        print "USED", used_mem
        if used_mem > max_memory:
            print "(%s) *** memory watcher restarting processes! Memory usage of %s exceeded %s." % (
                os.getpid(), used_mem, max_memory)
            os.kill(controller_pid, signal.SIGHUP)


if __name__ == '__main__':
    parser = optparse.OptionParser(
        description="Watch all the processes in the process group"
        " and if the total memory used goes over a configurable amount, send a SIGHUP"
        " to a given pid.")

    options, positional_args = parser.parse_args()

    if len(positional_args) < 2:
        parser.error("Usage: %s controller_pid max_memory_in_megabytes")

    print "(%s) memory watcher starting up, limiting memory to %s" % (
        os.getpid(), positional_args[1])

    try:
        watch_memory(int(positional_args[0]), int(positional_args[1]))
    except KeyboardInterrupt:
        pass
