# coding=utf-8

from httpd import run as httpd_run

def run(application, addr='127.0.0.1', port=8080):
    print 'start run weby'
    httpd_run(application, addr, port)

