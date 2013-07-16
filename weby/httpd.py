# coding=utf-8

import sys
import json

from django.core.servers.basehttp import WSGIServer, WSGIRequestHandler
from django.core.handlers.wsgi import WSGIHandler
from django.conf import settings
#from django.core import urlresolvers
from django.core import signals
from django import http
from django.core import exceptions
from django.http import HttpResponse

from webx.url import RegexURLResolver
from webx.result import JsonResult, TemplateResult


class MyWSGIHandler(WSGIHandler):

    def get_response(self, request):
        "Returns an HttpResponse object for the given HttpRequest"
        try:
            # Setup default url resolver for this thread, this code is outside
            # the try/except so we don't get a spurious "unbound local
            # variable" exception in the event an exception is raised before
            # resolver is set
            urlconf = settings.ROOT_URLCONF
            urls = __import__(urlconf)
            urlpatterns = urls.urlpatterns
            #urlresolvers.set_urlconf(urlconf)
            #resolver = urlresolvers.RegexURLResolver(r'^/', urlconf)
            resolver = RegexURLResolver(urlpatterns)
            try:
                response = None
                # Apply request middleware
                for middleware_method in self._request_middleware:
                    response = middleware_method(request)
                    if response:
                        break

                if response is None:
                    #if hasattr(request, 'urlconf'):
                        # Reset url resolver with a custom urlconf.
                        #urlconf = request.urlconf
                        #urlresolvers.set_urlconf(urlconf)
                        #resolver = urlresolvers.RegexURLResolver(r'^/', urlconf)
                        #resolver = RegexURLResolver(r'^/', urlconf)

                    resolver_match = resolver.resolve(request.path_info)
                    callback_name, callback, callback_args, callback_kwargs = resolver_match
                    #request.resolver_match = resolver_match

                    # Apply view middleware
                    for middleware_method in self._view_middleware:
                        response = middleware_method(request, callback, callback_args, callback_kwargs)
                        if response:
                            break

                if response is None:
                    try:
                        response = callback(request, *callback_args, **callback_kwargs)
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

                if isinstance(response, JsonResult) or isinstance(response, TemplateResult):
                    data = json.dumps(response.context)
                    response_kwargs = {'content_type': 'application/json'}
                    response = HttpResponse(data, **response_kwargs)
                else:
                    raise NotImplmentedError()

            except http.Http404 as e:
                logger.warning('Not Found: %s', request.path,
                            extra={
                                'status_code': 404,
                                'request': request
                            })
                if settings.DEBUG:
                    response = debug.technical_404_response(request, e)
                else:
                    try:
                        callback, param_dict = resolver.resolve404()
                        response = callback(request, **param_dict)
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
                #response = self.handle_uncaught_exception(request, resolver, sys.exc_info())
                pass
        finally:
            # Reset URLconf for this thread on the way out for complete
            # isolation of request.urlconf
            #urlresolvers.set_urlconf(None)
            pass

        try:
            # Apply response middleware, regardless of the response
            for middleware_method in self._response_middleware:
                response = middleware_method(request, response)
            #response = self.apply_response_fixes(request, response)
        except: # Any exception should be gathered and handled
            signals.got_request_exception.send(sender=self.__class__, request=request)
            response = self.handle_uncaught_exception(request, resolver, sys.exc_info())

        return response

def run(application):
    httpd = WSGIServer(('127.0.0.1', 8080), WSGIRequestHandler,
                      ipv6=False)
    httpd.set_app(application)
    httpd.serve_forever()