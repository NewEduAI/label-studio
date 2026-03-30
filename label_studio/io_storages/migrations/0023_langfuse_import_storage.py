import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0001_squashed_0065_auto_20210223_2014'),
        ('tasks', '0001_squashed_0041_taskcompletionhistory_was_cancelled'),
        ('io_storages', '0022_normalize_localfiles_paths'),
    ]

    operations = [
        migrations.CreateModel(
            name='LangfuseImportStorage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_sync', models.DateTimeField(blank=True, help_text='Last sync finished time', null=True, verbose_name='last sync')),
                ('last_sync_count', models.PositiveIntegerField(blank=True, help_text='Count of tasks synced last time', null=True, verbose_name='last sync count')),
                ('last_sync_job', models.CharField(blank=True, help_text='Last sync job ID', max_length=256, null=True, verbose_name='last_sync_job')),
                ('status', models.CharField(choices=[('initialized', 'Initialized'), ('queued', 'Queued'), ('in_progress', 'In progress'), ('failed', 'Failed'), ('completed', 'Completed'), ('completed_with_errors', 'Completed with errors')], default='initialized', max_length=64)),
                ('traceback', models.TextField(blank=True, help_text='Traceback report for the last failed sync', null=True)),
                ('meta', models.JSONField(default=dict, help_text='Meta and debug information about storage processes', null=True, verbose_name='meta')),
                ('title', models.CharField(blank=True, help_text='Cloud storage title', max_length=256, null=True, verbose_name='title')),
                ('description', models.TextField(blank=True, help_text='Cloud storage description', null=True, verbose_name='description')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='Creation time', verbose_name='created at')),
                ('synchronizable', models.BooleanField(default=True, help_text='If storage can be synced', verbose_name='synchronizable')),
                ('langfuse_host', models.TextField(help_text='Langfuse instance URL (e.g. https://cloud.langfuse.com)', verbose_name='langfuse host')),
                ('langfuse_public_key', models.TextField(help_text='Langfuse public API key', verbose_name='langfuse public key')),
                ('langfuse_secret_key', models.TextField(help_text='Langfuse secret API key', verbose_name='langfuse secret key')),
                ('trace_limit', models.PositiveIntegerField(default=100, help_text='Maximum number of traces to sync per batch', verbose_name='trace limit')),
                ('trace_name_filter', models.TextField(blank=True, help_text='Only sync traces matching this name (optional)', null=True, verbose_name='trace name filter')),
                ('trace_tag_filter', models.TextField(blank=True, help_text='Only sync traces with this tag (optional)', null=True, verbose_name='trace tag filter')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='io_storages_langfuseimportstorages', to='projects.project')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='LangfuseImportStorageLink',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.TextField(help_text='External link key', verbose_name='key')),
                ('object_exists', models.BooleanField(default=True, help_text='Whether object under external link still exists', verbose_name='object exists')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='Creation time', verbose_name='created at')),
                ('row_group', models.IntegerField(blank=True, help_text='Parquet row group', null=True)),
                ('row_index', models.IntegerField(blank=True, help_text='Parquet row index, or JSON[L] object index', null=True)),
                ('storage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='links', to='io_storages.langfuseimportstorage')),
                ('task', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='io_storages_langfuseimportstoragelink', to='tasks.task')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
