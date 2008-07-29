

from setuptools import find_packages, setup


setup(
    name='Spawning',
    description='Spawning is a wsgi server which supports multiple processes, multiple threads, non-blocking HTTP io, and automatic graceful upgrading of code.',
    long_description="""Spawning uses eventlet to do non-blocking IO for http requests and responses. This means the server will scale to a large number of keep-alive connections easily. However, it also delegates requests using other forms of multiprocessing and is configurable to be useful in a wide variety of situations. It supports multiple Python processes as well as a threadpool.

Single or Multiple Process
==========================

If your wsgi applications store state in memory, Spawning can be configured to run only one Python process. In this configuration your application state will be available to all requests but your application will not be able to take full advantage of multiple processors. Using multiple processes will take advantage of all processors and thus should be used for applications which do not share state.

Single or Multiple Thread
=========================

If your wsgi applications perform a certain subset of blocking calls which have been monkeypatched by eventlet to cooperate instead (such as operations in the socket module), you can configure each process to run only a single main thread and cooperate using greenlet microthreads instead. This can be useful if your application is very small and needs to scale to a large number of simultaneous requests, such as a COMET server or an application which uses AJAX polling. However, most existing wsgi applications will probably perform blocking operations (for example, calling database adapter libraries which perform blocking socket operations). Therefore, for most wsgi applications a combination of multiple processes and multiple threads will be ideal.

Graceful Code Reloading
=======================
By default, Spawning watches all Python files that are imported into sys.modules for changes and performs a graceful reload on change. Old processes are told to stop accepting requests and finish any outstanding requests they are servicing, and shutdown. Meanwhile, new processes are started and begin accepting requests and servicing them with the new code. At no point will users of your site see "connection refused" errors because the server is continuously listening during reload.

Running spawning
================

Spawning can be used to launch a wsgi application from the command line using the "spawn" script, or using Python Paste. To use with paste, specify use = egg:Spawning in the [server:main] section of a paste ini file.

Spawning can also be used to run a Django application by using --factory=spawning.django_factory.config_factory.

Examples of running spawning:

% spawn my_wsgi_module.my_wsgi_application

This will run the wsgi application callable called "my_wsgi_application" inside the my_wsgi_module.py file.

% spawn --factory=spawning.paste_factory.config_factory development.ini

Run whatever is configured inside of development.ini. Equivalent to using paster serve with an ini file configured to use Spawning as the server.

% spawn --factory=spawning.django_factory.config_factory mysite.settings

Run the Django app mysite.

% spawn my_wsgi_module.my_wsgi_application other_wsgi_module.some_wsgi_middleware

Run the wsgi application wrapped with some middleware. Pass as many middleware strings as desired after the wsgi application name.

% sudo spawn --port=80 --processes=4 --threads=8 my_wsgi_module.my_wsgi_application

Run the wsgi application on port 80, with 4 processes each using a threadpool of size 8.

% spawn --processes=4 --threads=0 my_wsgi_module.my_comet_application

Use a threadpool of size 0, which indicates that eventlet monkeypatching should be performed and wsgi applications should all be called in the same thread. Useful for writing a comet-style application where a lot of requests are simply waiting on a server-side event or internal network io to complete.
""",
    author='Donovan Preston',
    author_email='dsposx@mac.com',
    packages=find_packages(),
    version='0.7',
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

