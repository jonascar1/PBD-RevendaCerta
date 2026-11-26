from django.conf import settings
from urllib.parse import urlsplit


def demo_link(request):
    url = settings.DEMO_PUBLIC_URL
    parsed = urlsplit(url)
    return {'demo_public_url': url if parsed.scheme == 'https' and parsed.hostname and not parsed.username else ''}
