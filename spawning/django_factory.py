

import os
import django.core.handlers.wsgi
from django.core.servers.basehttp import AdminMediaHandler


def config_factory(args):
        args['django_settings_module'] = args.get('args', [None])[0]
        args['app_factory'] = 'spawning.django_factory.app_factory'


def app_factory(config):
    os.environ['DJANGO_SETTINGS_MODULE'] = config['django_settings_module']

    app = django.core.handlers.wsgi.WSGIHandler()
    if config['dev']:
        app = AdminMediaHandler(app)
    return app

