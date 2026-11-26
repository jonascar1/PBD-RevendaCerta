from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0035_usuario_foto_perfil')]
    operations = [
        migrations.AddField(model_name='avaliacaotroca', name='tipo', field=models.CharField(max_length=12, blank=True, default='', choices=[('HATCH','Hatch'),('SEDA','Sedã'),('SUV','SUV'),('PICAPE','Picape'),('UTILITARIO','Utilitário'),('MOTO','Motocicleta'),('OUTRO','Outro')])),
        migrations.AddField(model_name='avaliacaotroca', name='cambio', field=models.CharField(max_length=12, blank=True, default='', choices=[('MANUAL','Manual'),('AUTOMATICO','Automático'),('OUTRO','Outro')])),
    ]
