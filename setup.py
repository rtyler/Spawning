

from setuptools import find_packages, setup


setup(
    name='Spawning',
    author='Donovan Preston',
    author_email='dsposx@mac.com',
    packages=find_packages(),
    version='0.5',
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

