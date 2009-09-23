# Copyright (c) 2008, Donovan Preston
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
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
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


from setuptools import find_packages, setup


setup(
    name='Spawning',
    description='Spawning is a wsgi server which supports multiple processes, multiple threads, non-blocking HTTP io, and automatic graceful upgrading of code.',
    long_description="""Spawning uses eventlet to do non-blocking IO for http requests and responses. This means the server will scale to a large number of keep-alive connections easily. However, it also delegates requests using other forms of multiprocessing and is configurable to be useful in a wide variety of situations. It supports multiple Python processes as well as a threadpool.

Single or Multiple Process
==========================

If your wsgi applications store state in memory, Spawning can be configured to run only one Python process. In this configuration your application state will be available to all requests but your application will not be able to take full advantage of multiple processors. Using multiple processes will take advantage of all processors and thus should be used for applications which do not share state.

Single or Multiple Worker Thread (or Worker Process)
================================================================

If your wsgi applications perform a certain subset of blocking calls which have been monkeypatched by eventlet to cooperate instead (such as operations in the socket module), you can configure each process to run only a single main thread and cooperate using greenlet microthreads instead. This can be useful if your application is very small and needs to scale to a large number of simultaneous requests, such as a COMET server or an application which uses AJAX polling. However, most existing wsgi applications will probably perform blocking operations (for example, calling database adapter libraries which perform blocking socket operations). Therefore, for most wsgi applications a combination of multiple processes and multiple threads will be ideal.

Graceful Code Reloading
=======================
By default, Spawning watches all Python files that are imported into sys.modules for changes and performs a graceful reload on change. Old processes are told to stop accepting requests and finish any outstanding requests they are servicing, and shutdown. Meanwhile, new processes are started and begin accepting requests and servicing them with the new code. At no point will users of your site see "connection refused" errors because the server is continuously listening during reload.

Running spawning
================

Spawning can be used to launch a wsgi application from the command line using the "spawn" script, or using Python Paste. To use with paste, specify use = egg:Spawning in the [server:main] section of a paste ini file.

Spawning can also be used to run a Django application by using --factory=spawning.django_factory.config_factory.

Examples of running spawning
============================

Run the wsgi application callable called "my_wsgi_application" inside the my_wsgi_module.py file::

  % spawn my_wsgi_module.my_wsgi_application

Run whatever is configured inside of the paste-style configuration file development.ini. Equivalent to using paster serve with an ini file configured to use Spawning as the server::

  % spawn --factory=spawning.paste_factory.config_factory development.ini

Run the Django app mysite::

  % spawn --factory=spawning.django_factory.config_factory mysite.settings

Run the wsgi application wrapped with some middleware. Pass as many middleware strings as desired after the wsgi application name::

  % spawn my_wsgi_module.my_wsgi_application other_wsgi_module.some_wsgi_middleware

Run the wsgi application on port 80, with 4 processes each using a threadpool of size 8::

  % sudo spawn --port=80 --processes=4 --threads=8 my_wsgi_module.my_wsgi_application

Use a threadpool of size 0, which indicates that eventlet monkeypatching should be performed and wsgi applications should all be called in the same thread. Useful for writing a comet-style application where a lot of requests are simply waiting on a server-side event or internal network io to complete::

  % spawn --processes=4 --threads=0 my_wsgi_module.my_comet_application

Additional Useful Arguments
===========================

-l ACCESS_LOG_FILE, --access-log-file=ACCESS_LOG_FILE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    The file to log access log lines to. If not given, log
    to stdout. Pass /dev/null to discard logs.

-c, --coverage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    If given, gather coverage data from the running
    program and make the coverage report available from
    the /_coverage url. See the figleaf docs for more
    info: http://darcs.idyll.org/~t/projects/figleaf/doc/

-m MAX_MEMORY, --max-memory=MAX_MEMORY
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    If given, the maximum amount of memory this instance
    of Spawning is allowed to use. If all of the processes
    started by this Spawning controller use more than this
    amount of memory, send a SIGHUP to the controller to
    get the children to restart.

-a MAX_AGE, --max-age=MAX_AGE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    If given, the maximum amount of time (in seconds) an
    instance of spawning_child is allowed to run. Once
    this time limit has expired a SIGHUP will be sent to
    spawning_controller, causing it to restart all of the
    child processes.
""",
    author='Donovan Preston',
    author_email='dsposx@mac.com',
    include_package_data = True,
    packages = find_packages('src'),
    package_dir = {'': 'src'},
    version='0.8.11',
    install_requires=['eventlet', 'simplejson', 'PasteDeploy'],
    entry_points={
        'console_scripts': [
            'spawn=spawning.spawning_controller:main',
        ],
        'paste.server_factory': [
            'main=spawning.paste_factory:server_factory'
        ]
    },
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Intended Audience :: Developers",
        "Development Status :: 4 - Beta"
    ]
)

