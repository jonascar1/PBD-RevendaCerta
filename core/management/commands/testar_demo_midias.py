from tempfile import TemporaryDirectory
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from core.demo_storage import DemoStorage, demo_media_scope

class Command(BaseCommand):
    help = 'Testa isolamento de mídias em diretório temporário, sem acessar R2.'

    def handle(self, *args, **kwargs):
        a, b = 'demo_' + 'a'*32, 'demo_' + 'b'*32
        def blocked(fn):
            try:
                fn()
            except PermissionDenied:
                return
            raise CommandError('Operação indevida não bloqueada')
        with TemporaryDirectory() as tmp, override_settings(STORAGES={
            'default': {'BACKEND': 'core.demo_storage.DemoStorage'},
            'media_original': {'BACKEND': 'django.core.files.storage.FileSystemStorage', 'OPTIONS': {'location': tmp}},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        }):
            s = DemoStorage()
            original = s.save('veiculos/original.jpg', ContentFile(b'original'))
            with demo_media_scope(a):
                assert s.open(original).read() == b'original'
                blocked(lambda: s.delete(original))
                blocked(lambda: s.open('perfis/privado.jpg'))
                key = s.save('perfis/1/foto.jpg', ContentFile(b'A'), max_length=255)
                assert key.startswith('demos/' + a + '/')
                assert s.open(key).read() == b'A'
            with demo_media_scope(b):
                blocked(lambda: s.open(key))
                blocked(lambda: s.delete(key))
                other = s.save('perfis/1/foto.jpg', ContentFile(b'B'), max_length=255)
                assert s.open(other).read() == b'B'
            blocked(lambda: s.open(key))
            with demo_media_scope(a):
                s.delete(key)
                assert not s.exists(key)
            with demo_media_scope(b):
                assert s.open(other).read() == b'B'
            assert s.open(original).read() == b'original'
        self.stdout.write(self.style.SUCCESS('OK: mídia original preservada; uploads e exclusões isolados; perfis originais bloqueados.'))
