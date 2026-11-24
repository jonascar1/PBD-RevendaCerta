from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('core','0033_alcada_veiculo')]
    operations = [migrations.CreateModel(name='HistoricoAlcada', fields=[
        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('tipo_anterior', models.CharField(max_length=20)),
        ('valor_anterior', models.DecimalField(max_digits=12, decimal_places=2)),
        ('tipo_novo', models.CharField(max_length=20)),
        ('valor_novo', models.DecimalField(max_digits=12, decimal_places=2)),
        ('criado_em', models.DateTimeField(auto_now_add=True)),
        ('veiculo', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='core.veiculo')),
        ('gerente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
    ])]
