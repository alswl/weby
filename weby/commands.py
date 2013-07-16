# coding=utf-8

from django.conf import settings
from django.core.servers.basehttp import WSGIServer

from httpd import run as httpd_run

def run(application):
    print 'start run weby'
    httpd_run(application)

