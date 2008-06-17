
This is a mash-up of Python Paste and eventlet. It implements the server_factory from Paste using the eventlet.wsgi server. It also has some nice features such as the ability to be multiprocess (not exposed yet) and code reloading based on either watching the filesystem for changes or watching the svn revision for changes.

The code reloading is graceful; that is to say, any requests which are currently in progress when the code reloading is initiated are handled to completion by the old processes, and new processes are started up to handle any new incoming requests.

Donovan Preston
June 16, 2008
