#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import os

from setuptools import find_packages, setup

NAME = 'polar_rcx5_datalink'
DESCRIPTION = 'Polar RCX5 training session exporter'
URL = 'https://github.com/purpledot/polar-rcx5-datalink'
EMAIL = 'getinax@gmail.com'
AUTHOR = 'purpledot'
REQUIRES_PYTHON = '>=3.7.0'
VERSION = None

REQUIRED = [
    'click>=7',
    'flask>=1.0.2',
    'geopy>=1.17.0',
    'pytz>=2018.7',
    'pyusb>=1.0.2',
    'requests>=2.20.1',
    'timezonefinder>=3.3.0',
    'tzlocal>=1.5.1',
]

here = os.path.abspath(os.path.dirname(__file__))

try:
    with io.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = '\n' + f.read()
except FileNotFoundError:
    long_description = DESCRIPTION

about = {}
if VERSION is None:
    with open(os.path.join(here, NAME, '__version__.py')) as f:
        exec(f.read(), about)
else:
    about['__version__'] = VERSION

setup(
    name=NAME,
    version=about['__version__'],
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=AUTHOR,
    author_email=EMAIL,
    python_requires=REQUIRES_PYTHON,
    url=URL,
    install_requires=REQUIRED,
    include_package_data=True,
    license='Unlicense',
    packages=find_packages(),
    entry_points={'console_scripts': ['rcx5=polar_rcx5_datalink.cli:main']},
    classifiers=[
        'License :: Public Domain',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
    ],
)
