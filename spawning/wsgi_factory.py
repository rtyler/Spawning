
import time

from eventlet import api


def config_factory(args):
    args['app_factory'] = 'spawning.wsgi_factory.app_factory'
    args['app'] = args['args'][0]
    args['middleware'] = args['args'][1:]

    return args


def app_factory(config):
    app = api.named(config['app'])
    for mid in config['middleware']:
        app = api.named(mid)(app)
    return app


def hello_world(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    return ['Hello, World!\r\n']


def really_long(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    time.sleep(180)
    return ['Goodbye, World!\r\n']

