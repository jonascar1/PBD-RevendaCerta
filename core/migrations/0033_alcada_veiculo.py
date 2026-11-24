from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0032_metamensal_historicometa_metaindividual')]
    operations = [
        migrations.AddField(model_name='veiculo', name='tipo_alcada', field=models.CharField(max_length=20, choices=[('PERCENTUAL', 'Percentual (%)'), ('VALOR', 'Valor (R$)')], default='PERCENTUAL')),
        migrations.AddField(model_name='veiculo', name='valor_alcada', field=models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='Limite máximo de desconto permitido para o veículo.')),
        migrations.RemoveField(model_name='perfilvendedor', name='tipo_alcada'),
        migrations.RemoveField(model_name='perfilvendedor', name='valor_alcada'),
    ]
