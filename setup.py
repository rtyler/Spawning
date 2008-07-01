

from setuptools import find_packages, setup


setup(
    name='Spawning',
    description='Spawning is a wsgi server plugin for paste which uses eventlet to do non-blocking IO '
        'for http requests and responses. It supports multiple Python processes as well as a threadpool. '
        'It supports graceful reloading on code change; outstanding requests are given a chance to '
        'finish while new requests are handled in new Python processes. It plugs into Python Paste.',
    author='Donovan Preston',
    author_email='dsposx@mac.com',
    packages=find_packages(),
    version='0.7pre',
    install_requires=['eventlet', 'simplejson', 'PasteDeploy'],
    entry_points={
        'paste.server_factory': [
            'main=spawning.spawning_controller:server_factory'
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

