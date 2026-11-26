from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0034_historicoalcada")]
    operations = [migrations.AddField(
        model_name="usuario", name="foto_perfil",
        field=models.ImageField(blank=True, max_length=255, upload_to="perfis/"),
    )]
