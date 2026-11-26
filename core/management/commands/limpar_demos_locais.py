from django.core.management.base import BaseCommand
from core.demo_lifecycle import lifecycle_lock, cleanup, schemas, expiry
from django.utils import timezone
class Command(BaseCommand):
    def add_arguments(self,parser): parser.add_argument('--confirmar',action='store_true')
    def handle(self,*args,**opts):
        with lifecycle_lock():
            names=cleanup() if opts['confirmar'] else [n for n in schemas() if expiry(n)<=timezone.now()]
            self.stdout.write(f'{"Removidas" if opts["confirmar"] else "Expiradas (simulação)"}: {names}')
