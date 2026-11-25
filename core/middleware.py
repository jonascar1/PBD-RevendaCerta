"""Prevent caching of private HTML without changing view permissions."""
from django.utils.cache import add_never_cache_headers


class PrivateNavigationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        private = path.startswith(("/painel/", "/accounts/", "/admin/")) or path in ("/painel", "/login/", "/login")
        authenticated = request.user.is_authenticated
        response = self.get_response(request)
        if private or authenticated or request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
