from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0034_project_annotator_evaluation_enabled'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectmember',
            name='role',
            field=models.CharField(
                choices=[
                    ('annotator', 'Annotator'),
                    ('reviewer', 'Reviewer'),
                ],
                default='annotator',
                help_text='Role of the user in this project',
                max_length=20,
                verbose_name='role',
            ),
        ),
    ]
