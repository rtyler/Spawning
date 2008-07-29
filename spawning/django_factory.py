

import os
import django.core.handlers.wsgi
from django.core.servers.basehttp import AdminMediaHandler


def config_factory(args):
    watch = args.get('watch', None)
    if watch is None:
        watch = []

    return {
        'dev': args.get('dev', False),
        'host': args.get('host', None),
        'port': args.get('port', None),
        'num_processes': args.get('num_processes', None),
        'threadpool_workers': args.get('threadpool_workers', None),
        'processpool_workers': args.get('processpool_workers', None),
        'watch': watch,
        'django_settings_module': args.get('args', [None])[0],
        'app_factory': 'spawning.django_factory.app_factory',
    }


def app_factory(config):
    os.environ['DJANGO_SETTINGS_MODULE'] = config['django_settings_module']

    app = django.core.handlers.wsgi.WSGIHandler()
    if config['dev']:
        app = AdminMediaHandler(app)
    return app

