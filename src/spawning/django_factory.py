

import inspect
import os
import django.core.handlers.wsgi
from django.core.servers.basehttp import AdminMediaHandler

from eventlet import api


def config_factory(args):
    args['django_settings_module'] = args.get('args', [None])[0]
    args['app_factory'] = 'spawning.django_factory.app_factory'

    ## TODO More directories
    ## INSTALLED_APPS (list of quals)
    ## ROOT_URL_CONF (qual)
    ## MIDDLEWARE_CLASSES (list of quals)
    ## TEMPLATE_CONTEXT_PROCESSORS (list of quals)
    settings_module = api.named(args['django_settings_module'])

    dirs = [os.path.split(
        inspect.getfile(
            inspect.getmodule(
                settings_module)))[0]]
    args['source_directories'] = dirs

    return args


def app_factory(config):
    os.environ['DJANGO_SETTINGS_MODULE'] = config['django_settings_module']

    app = django.core.handlers.wsgi.WSGIHandler()
    if config['dev']:
        app = AdminMediaHandler(app)
    return app

