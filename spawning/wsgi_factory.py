
from eventlet import api


def config_factory(args):
    return {
        'dev': args.get('dev', False),
        'host': args.get('host', None) or '',
        'port': args.get('port', None) or 8080,
        'num_processes': args.get('num_processes', 1),
        'threadpool_workers': args.get('threadpool_workers', 0),
        'watch': args.get('watch', []),

        'app_factory': 'spawning.wsgi_factory.app_factory',
        'app': args['args'][0],
        'middleware': args['args'][1:]
    }


def app_factory(config):
    app = api.named(config['app'])
    for mid in config['middleware']:
        app = api.named(mid)(app)
    return app


def hello_world(env, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    return ['Hello, World!\r\n']

