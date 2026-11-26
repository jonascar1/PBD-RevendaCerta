"""Media boundary for demo requests. Scope must be selected by trusted server code."""
import re
from pathlib import Path
from django.conf import settings
from contextvars import ContextVar
from contextlib import contextmanager
from django.core.exceptions import PermissionDenied
from django.core.files.storage import Storage, storages
from django.core.files.utils import validate_file_name

_scope = ContextVar('demo_media_scope', default=None)
_PATTERN = re.compile(r'demo_[0-9a-f]{32}\Z')

@contextmanager
def demo_media_scope(schema):
    if not _PATTERN.fullmatch(schema):
        raise ValueError('Schema inválido')
    token = _scope.set(schema)
    try:
        yield
    finally:
        _scope.reset(token)

class DemoStorage(Storage):
    @property
    def backend(self):
        return storages['media_original']

    def _check(self, name, write=False):
        validate_file_name(name, allow_relative_path=True)
        if '\\' in name or any(p in ('', '.', '..') for p in name.split('/')):
            raise PermissionDenied('Caminho inválido')
        scope = _scope.get()
        if scope:
            if name.startswith('demos/' + scope + '/'):
                return name
            if not write and name.startswith('veiculos/'):
                return name
            raise PermissionDenied('Mídia fora da demonstração')
        if name.startswith('demos/'):
            raise PermissionDenied('Mídia de demonstração')
        return name

    def save(self, name, content, max_length=None):
        scope = _scope.get()
        if scope:
            if not name.startswith(('veiculos/', 'avaliacoes_troca/', 'perfis/')):
                raise PermissionDenied('Destino inválido')
            size=getattr(content,'size',None)
            if size is None or size>5*1024**2: raise PermissionDenied('Arquivo excede 5 MiB.')
            folder=Path(settings.MEDIA_ROOT)/'demos'/scope
            if settings.DEBUG:
                used=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
            else:
                used=sum(obj.size for obj in self.backend.bucket.objects.filter(Prefix='demos/'+scope+'/'))
            if used+size>50*1024**2: raise PermissionDenied('Limite de 50 MiB atingido.')
            name = 'demos/' + scope + '/' + name
        return self.backend.save(self._check(name, True), content, max_length=max_length)

    def _open(self, name, mode='rb'):
        if mode not in ('r', 'rb'):
            raise PermissionDenied('Modo inválido')
        return self.backend.open(self._check(name), mode)

    def delete(self, name):
        return self.backend.delete(self._check(name, True))

    def exists(self, name):
        return self.backend.exists(self._check(name))

    def size(self, name):
        return self.backend.size(self._check(name))

    def url(self, name):
        checked = self._check(name)
        if _scope.get() and checked.startswith('demos/'):
            from urllib.parse import quote
            return '/media/' + quote(checked, safe='/')
        return self.backend.url(checked)
