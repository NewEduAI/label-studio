from django.db import migrations, models


def set_owner_role_for_creators(apps, schema_editor):
    """Set the 'owner' role for organization creators."""
    OrganizationMember = apps.get_model('organizations', 'OrganizationMember')
    Organization = apps.get_model('organizations', 'Organization')
    for org in Organization.objects.all():
        if org.created_by_id:
            OrganizationMember.objects.filter(
                user_id=org.created_by_id,
                organization=org,
            ).update(role='owner')


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0006_alter_organizationmember_deleted_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationmember',
            name='role',
            field=models.CharField(
                choices=[
                    ('owner', 'Owner'),
                    ('admin', 'Admin'),
                    ('manager', 'Manager'),
                    ('annotator', 'Annotator'),
                ],
                default='annotator',
                help_text='Role of the user in this organization',
                max_length=20,
                verbose_name='role',
            ),
        ),
        migrations.RunPython(set_owner_role_for_creators, migrations.RunPython.noop),
    ]
