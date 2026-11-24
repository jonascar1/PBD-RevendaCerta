
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ReservaVeiculo


class Command(BaseCommand):
    help = "Encerra reservas vencidas e processa a fila de espera."

    def handle(self, *args, **options):
        agora = timezone.now()

        reservas_vencidas = list(
            ReservaVeiculo.objects.filter(
                cancelada=False,
                expira_em__lte=agora,
            ).values_list("pk", flat=True)
        )

        total_expiradas = 0
        total_erros = 0

        for reserva_id in reservas_vencidas:
            try:
                reserva = ReservaVeiculo.objects.get(pk=reserva_id)

                if reserva.expirar():
                    total_expiradas += 1

            except Exception as erro:
                total_erros += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Erro na reserva #{reserva_id}: {erro}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Processamento concluído. "
                f"Expiradas: {total_expiradas}. "
                f"Erros: {total_erros}."
            )
        )

        if total_erros:
            raise RuntimeError(
                f"Falha ao processar {total_erros} reserva(s)."
            )
