
Spawning is a flexible web server written in Python. It marries different concurrency styles (single process non-blocking i/o, multithreaded, multiprocess) and is configurable for use in many situations, from plain old WSGI applications to COMET-style applications. It also supports transparent code reloading.

The code reloading is graceful; that is to say, any requests which are currently in progress when the code reloading is initiated are handled to completion by the old processes, and new processes are started up to handle any new incoming requests.
