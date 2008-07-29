"""This sentence is false.
"""

import mmap
import optparse
import os
import StringIO
import struct
import sys
import tempfile
import traceback

from eventlet import api

import simplejson


BLANK = ' ' * 16384


def handle_forever(wsgi_app, fromfile, tofile, envfile):
    while True:
        started = False
        while True:
            chunklen = int(fromfile.readline(), 16)
            if not started:
                envfile.seek(0)
                env = simplejson.loads(envfile.read(16384))
                inputfile = env['wsgi.input'] = StringIO.StringIO()
                started = True

            if not chunklen:
                fromfile.readline()
                break

            inputfile.write(fromfile.read(chunklen))
            fromfile.readline()

        def _start_response(status, headers, exc_info=None):
            envfile.seek(0)
            envfile.write(BLANK)
            envfile.seek(0)
            simplejson.dump([status, headers], envfile)

        for chunk in wsgi_app(env, _start_response):
            tofile.write("%x\r\n%s\r\n" % (len(chunk), chunk))
            tofile.flush()

        tofile.write('0\r\n\r\n')
        tofile.flush()


def main():
    parser = optparse.OptionParser()
    parser.add_option(
        "-e", "--environ", type="int",
        help="The memmapped file to find the pickled wsgi environment in.")
    parser.add_option(
        "-i", "--input", type="int",
        help="The fileno to read input from.")
    parser.add_option(
        "-o", "--output", type="int",
        help="The fileno to write output to.")

    options, args = parser.parse_args()

    if len(args) < 1:
        print "Usage: %s config" % (
            sys.argv[0], )
        sys.exit(1)

    config = simplejson.loads(args[0])

    handle_forever(
        api.named(config['app_factory'])(config),
        os.fdopen(options.input, 'r'),
        os.fdopen(options.output, 'w'),
        mmap.mmap(options.environ, 0))


if __name__ == '__main__':
    main()

