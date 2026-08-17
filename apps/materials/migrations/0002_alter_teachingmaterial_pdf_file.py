from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='teachingmaterial',
            name='pdf_file',
            field=models.FileField(blank=True, max_length=500, upload_to='materials/pdfs/'),
        ),
    ]
