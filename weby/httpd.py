# coding=utf-8
import csv

import sys
import json
import logging
import time

from django.core.servers.basehttp import WSGIServer, WSGIRequestHandler
from django.core.handlers.wsgi import WSGIHandler
#from django.core import urlresolvers
from django.core import signals
from django import http
from django.core import exceptions
from django.http import (HttpResponse, HttpResponseRedirect,
                         HttpResponseServerError)
from webx.url import RegexURLResolver
from webx.result import JsonResult, TemplateResult, RedirectResult, CSVFileResult, SimpleResult
from webx.url import Http404 as webxHttp404
from webx import settings as webx_settings
from webx.utils.importlib import import_module

from utils import format_value

DEBUG = True
ROOT_URLCONF = 'urls'
logger = logging.getLogger(__name__)

#logger_performance = logging.getLogger()
#logFormatter = logging.Formatter('%(asctime)s [%(levelname)s]  %(name)s -  %(message)s')
#logHandler.setFormatter(logFormatter)
#logger_performance.propagate = 0
#logger_performance.setLevel(logging.INFO)


class MockRequest(object):

    def set_status(self, status):
        self.status = status


def _adjust_request(request):

    def _set_cookie(key, value='', max_age=-1, path='/',
                    domain=None, secure=False, httponly=False):
        if not hasattr(request, '_weby_cookies'):
            request._weby_cookies = []
        request._weby_cookies.append({
            'key': key,
            'value': value,
            'max_age': max_age,
            'domain': domain,
            'path': path,
            'secure': secure,
            'httponly': httponly,
        })

    def _get_views_path():
        return request._view_path

    def _redirect(target):
        return RedirectResult(target)

    def _forward(target):
        # FIXME
        return RedirectResult(target)

    request._view_path = None
    request.REQUEST0 = request.REQUEST
    request.set_cookie = _set_cookie
    request.get_views_path = _get_views_path
    request.redirect = _redirect
    request.forward = _forward
    request.response = MockRequest()


def _adjust_response(response):
    def _set_cookie(key, value, max_age, domain, path, secure, httponly):
        if not hasattr(response, '_weby_cookies'):
            response._weby_cookies = []

        response._weby_cookies.append({
            'key': key,
            'value': value,
            'max_age': max_age,
            'domain': domain,
            'path': path,
            'secure': secure,
            'httponly': httponly,
        })

    response.set_cookie = _set_cookie

class MyWSGIHandler(WSGIHandler):

    def __init__(self, *args, **kwargs):
        super(MyWSGIHandler, self).__init__(*args, **kwargs)
        self._request_middleware = []
        self._response_middleware = []
        self._view_middleware = []
        self._exception_middleware = []
        self.init_middleware()

    def init_middleware(self):
        for middleware_path in webx_settings.MIDDLEWARE_CLASSES:
            try:
                mw_module, mw_classname = middleware_path.rsplit('.', 1)
            except ValueError:
                raise ValueError('%s isn\'t a middleware module' % middleware_path)
            try:
                mod = import_module(mw_module)
            except ImportError, e:
                raise ImportError('Error importing middleware %s: "%s"' % (mw_module, e))
            try:
                mw_class = getattr(mod, mw_classname)
            except AttributeError:
                raise AttributeError('Middleware module "%s" does not define a "%s" class' % (mw_module, mw_classname))
            try:
                mw_instance = mw_class()
            except exceptions.MiddlewareNotUsed:
                continue

            if hasattr(mw_instance, 'process_request'):
                self._request_middleware.append(mw_instance.process_request)
            if hasattr(mw_instance, 'process_response'):
                self._response_middleware.insert(0, mw_instance.process_response)

    def get_response(self, request):
        "Returns an HttpResponse object for the given HttpRequest"
        _adjust_request(request)
        start = time.time()
        try:
            # Setup default url resolver for this thread, this code is outside
            # the try/except so we don't get a spurious "unbound local
            # variable" exception in the event an exception is raised before
            # resolver is set
            request.user_id = None # fix for japa
            urlconf = ROOT_URLCONF
            urls = __import__(urlconf)
            #urlpatterns = urls.urlpatterns
            host_url_patterns_map = urls.host_url_patterns_map
            #urlresolvers.set_urlconf(urlconf)
            #resolver = urlresolvers.RegexURLResolver(r'^/', urlconf)
            resolver_map = {
                k: RegexURLResolver(v) for k, v in host_url_patterns_map.items()
            }
            resolver = resolver_map[request.META.get('HTTP_HOST', 'default')]
            try:
                response = None
                # Apply request middleware

                resolver_match = resolver.resolve(request.path_info)
                callback_name, callback, callback_args, callback_kwargs = resolver_match
                request._view_path = callback_name

                for middleware_method in self._request_middleware:
                    #response = middleware_method(request)
                    middleware_method(request)
                    if response:
                        break

                if response is None:
                    #if hasattr(request, 'urlconf'):
                        # Reset url resolver with a custom urlconf.
                        #urlconf = request.urlconf
                        #urlresolvers.set_urlconf(urlconf)
                        #resolver = urlresolvers.RegexURLResolver(r'^/', urlconf)
                        #resolver = RegexURLResolver(r'^/', urlconf)

                    #request.resolver_match = resolver_match

                    # Apply view middleware
                    for middleware_method in self._view_middleware:
                        response = middleware_method(request, callback, callback_args, callback_kwargs)
                        if response:
                            break

                if response is None:
                    try:
                        response = callback(request, *callback_args, **callback_kwargs)
                        _adjust_response(response)
                    except Exception as e:
                        # If the view raised an exception, run it through exception
                        # middleware, and if the exception middleware returns a
                        # response, use that. Otherwise, reraise the exception.
                        for middleware_method in self._exception_middleware:
                            response = middleware_method(request, e)
                            if response:
                                break
                        if response is None:
                            raise

                # Complain if the view returned None (a common error).
                if response is None:
                    if isinstance(callback, types.FunctionType):    # FBV
                        view_name = callback.__name__
                    else:                                           # CBV
                        view_name = callback.__class__.__name__ + '.__call__'
                    raise ValueError("The view %s.%s didn't return an HttpResponse object." % (callback.__module__, view_name))

                # If the response supports deferred rendering, apply template
                # response middleware and the render the response
                if hasattr(response, 'render') and callable(response.render):
                    for middleware_method in self._template_response_middleware:
                        response = middleware_method(request, response)
                    response = response.render()


            except http.Http404 as e:
                logger.warning('Not Found: %s', request.path,
                            extra={
                                'status_code': 404,
                                'request': request
                            })
                if DEBUG:
                    pass
                    #response = debug.technical_404_response(request, e)
                else:
                    try:
                        callback, param_dict = resolver.resolve404()
                        response = callback(request, **param_dict)
                    except:
                        signals.got_request_exception.send(sender=self.__class__, request=request)
                        response = self.handle_uncaught_exception(request, resolver, sys.exc_info())
            except webxHttp404 as e:
                logger.warning('Not Found: %s', request.path,
                            extra={
                                'status_code': 404,
                                'request': request
                            })
                if DEBUG:
                    #response = debug.technical_404_response(request, e)
                    try:
                        resolver_match = resolver.resolve('/404/')
                        callback_name, callback, callback_args, callback_kwargs = resolver_match
                        response = callback(request, *callback_args, **callback_kwargs)
                    except:
                        signals.got_request_exception.send(sender=self.__class__, request=request)
                        response = self.handle_uncaught_exception(request, resolver, sys.exc_info())
                else:
                    try:
                        resolver_match = resolver.resolve('/404/')
                        callback_name, callback, callback_args, callback_kwargs = resolver_match
                        response = callback(request, *callback_args, **callback_kwargs)
                    except:
                        signals.got_request_exception.send(sender=self.__class__, request=request)
                        response = self.handle_uncaught_exception(request, resolver, sys.exc_info())
            except exceptions.PermissionDenied:
                logger.warning(
                    'Forbidden (Permission denied): %s', request.path,
                    extra={
                        'status_code': 403,
                        'request': request
                    })
                try:
                    callback, param_dict = resolver.resolve403()
                    response = callback(request, **param_dict)
                except:
                    signals.got_request_exception.send(
                            sender=self.__class__, request=request)
                    response = self.handle_uncaught_exception(request,
                            resolver, sys.exc_info())
            except SystemExit:
                # Allow sys.exit() to actually exit. See tickets #1023 and #4701
                raise
            except: # Handle everything else, including SuspiciousOperation, etc.
                # Get the exception info now, in case another exception is thrown later.
                #signals.got_request_exception.send(sender=self.__class__, request=request)
                response = self.handle_uncaught_exception(request, resolver, sys.exc_info())
        finally:
            # Reset URLconf for this thread on the way out for complete
            # isolation of request.urlconf
            #urlresolvers.set_urlconf(None)
            pass

        try:
            # Apply response middleware, regardless of the response
            for middleware_method in self._response_middleware:
                #response = middleware_method(request, response)
                middleware_method(request, response)
            #response = self.apply_response_fixes(request, response)
        except: # Any exception should be gathered and handled
            signals.got_request_exception.send(sender=self.__class__, request=request)
            response = self.handle_uncaught_exception(request, resolver, sys.exc_info())

        _response = response
        if isinstance(_response, SimpleResult):
            response = HttpResponse(
                _response.get_content(),
                content_type=(_response.get_content_type()),
                status=(_response.get_status())
            )
            headers = _response.get_headers()
            if headers:
                for k, v in headers:
                    response[k] = v

        elif isinstance(response, JsonResult):
            data = json.dumps(format_value(response.context))
            response_kwargs = {'content_type': 'application/json'}
            response = HttpResponse(data, **response_kwargs)
        elif isinstance(response, TemplateResult):
            from webx import tiny; t=tiny.Tiny()
            data = t.render(response.template, response.context, request)
            response_kwargs = {'content_type': 'text/html'}
            response = HttpResponse(data, **response_kwargs)
        elif isinstance(response, RedirectResult):
            target = response.target
            response = HttpResponse("", status=302)
            response['Location'] = target
        elif isinstance(response, CSVFileResult):
            rows = response.rows
            name = response.name
            response_kwargs = {'content_type': 'text/csv'}
            response = HttpResponse("", **response_kwargs)
            response['Content-Disposition'] = 'attachment; filename="%s.csv"' % (name)
            writer = csv.writer(response, delimiter='\t')
            for row in rows:
                writer.writerow(row)

        elif isinstance(response, HttpResponseServerError):
            pass
        else:
            raise NotImplementedError()

        if hasattr(request, '_weby_cookies'):  # fix for japa session
            for cookie in request._weby_cookies:
                response.set_cookie(**cookie)
        if hasattr(_response, '_weby_cookies'):  # fix for japa session
            for cookie in _response._weby_cookies:
                response.set_cookie(**cookie)
        if hasattr(request.response, 'status'):  # fix for japa status
            response.status_code = request.response.status
            
        logger.info('This request take %f ms' %((time.time() - start) * 1000))
        return response

def run(application, addr, port):
    httpd = WSGIServer((addr, port), WSGIRequestHandler, ipv6=False)
    httpd.set_app(application)
    httpd.serve_forever()
