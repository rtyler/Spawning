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

import os
import mmap
import signal
import sys
import tempfile

from eventlet import greenio
from eventlet import pools
from eventlet import processes

from spawning import processpool_child

import simplejson


CHUNK_SIZE = 16384
TEMPFILENO = 0
BLANK = ' ' * 16384

class Worker(object):
    """In soviet russia, subprocess processes YOU!
    """
    def __init__(self, config, tempdir):
        envfileno = os.open(
            os.path.join(tempdir, 'envfile_%s' % (TEMPFILENO, )),
            os.O_RDWR | os.O_CREAT)

        os.write(envfileno, BLANK)
        self.mmap = mmap.mmap(envfileno, 0)
        r_i, w_i = os.pipe()
        r_o, w_o = os.pipe()

        self.child_pid = os.fork()
        if not self.child_pid:
            args = [sys.executable,
                processpool_child.__file__,
                '--environ=%s' % (envfileno, ),
                '--input=%s' % (r_i, ),
                '--output=%s' % (w_o, ),
                simplejson.dumps(config)]
            os.execv(sys.executable, args)
            ## Never gets here

        self.reader = greenio.GreenPipe(os.fdopen(r_o, 'r'))
        self.writer = greenio.GreenPipe(os.fdopen(w_i, 'w'))

    def __call__(self, env, start_response):
        self.mmap.seek(0)
        self.mmap.write(BLANK)
        self.mmap.seek(0)
        simplejson.dump(
            dict([(k, v) for (k, v) in env.iteritems()
            if isinstance(v, basestring)]),
            self.mmap)

        chunk = env['wsgi.input'].read()
        while chunk:            
            self.writer.write("%x\r\n%s\r\n" % (len(chunk), chunk))
            self.writer.flush()
        self.writer.write('0\r\n\r\n')
        self.writer.flush()

        started = False
        while True:
            chunklen = int(self.reader.readline(), 16)
            if not started:
                self.mmap.seek(0)
                status, headers = simplejson.loads(self.mmap.read(16384))
                start_response(status, headers)
                started = True

            if not chunklen:
                self.reader.readline()
                break

            chunk = self.reader.read(chunklen)
            self.reader.readline()
            yield chunk

    def kill(self):
        os.kill(self.child_pid, signal.SIGTERM)


class WorkerPool(pools.Pool):
    def __init__(self, config):
        self.tempdir = tempfile.mkdtemp()
        self.config = config
        pools.Pool.__init__(self, min_size=config['processpool_workers'])

    def create(self):
        return Worker(self.config, self.tempdir)


class ExecuteInProcessPool(object):
    def __init__(self, config):
        self.pool = WorkerPool(config)

    def __call__(self, env, start_response):
        worker = self.pool.get()
        for chunk in worker(env, start_response):
            yield chunk
        self.pool.put(worker)

    def kill(self):
        for sub in self.pool.free_items:
            sub.kill()

