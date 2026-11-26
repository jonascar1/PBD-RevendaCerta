from django.conf import settings
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def demo_link(request):
    url = request.build_absolute_uri("/demo/perfil/") if getattr(request, "demo_shared", False) else settings.DEMO_PUBLIC_URL
    parsed = urlsplit(url)
    valid = url if (parsed.scheme == 'https' or (settings.DEBUG and parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))) and parsed.hostname and not parsed.username else ''
    roles = []
    if valid:
        for role, label in [('gerente', 'Gerente'), ('vendedor', 'Vendedor'), ('administrativo', 'Administrativo')]:
            query = dict(parse_qsl(parsed.query)); query['perfil'] = role
            roles.append({'icon': {'gerente': 'chart-no-axes-combined', 'vendedor': 'handshake', 'administrativo': 'clipboard-list'}[role], 'label': label, 'url': urlunsplit(parsed._replace(query=urlencode(query)))})
    return {'demo_public_url': valid, 'demo_roles': roles}
