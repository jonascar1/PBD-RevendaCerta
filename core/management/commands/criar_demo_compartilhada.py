from django.core.management.base import BaseCommand
from django.db import connection
from core.demo_lifecycle import lifecycle_lock, provision
from core.demo_http_probe import schema_scope

class Command(BaseCommand):
    help = 'Cria uma base fictícia compartilhada para o serviço de consulta.'
    def handle(self, *args, **kwargs):
        with lifecycle_lock():
            name = provision()
            with schema_scope(name), connection.cursor() as cursor:
                cursor.execute("UPDATE demo_lifecycle SET expira_em = '2099-12-31 00:00:00+00' WHERE id=1")
            self.stdout.write(self.style.SUCCESS('DEMO_SCHEMA=' + name))
