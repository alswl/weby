#!/usr/bin/env python

from distutils.core import setup

setup(
    name='weby',
    version='0.1.1',
    description='WSGI Server for Donkey',
    author='ddd',
    author_email='jingchao.di@duitang.com',
    url='http://www.duitang.com/',
    packages=['weby'],
    install_requires=[
        'django>=1.5',
    ],
)
