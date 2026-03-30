import logging
import os

from core.permissions import all_permissions
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from projects.models import Project
from rest_framework import generics, status
from rest_framework.response import Response
from tasks.models import Task

logger = logging.getLogger(__name__)


def _annotation_result_to_scores(result_item):
    """Map a single annotation result item to Langfuse score parameters.

    Per Langfuse API:
    - CATEGORICAL: string label goes in `value`
    - NUMERIC: number goes in `value`
    - TextArea: text goes in `comment`, not as a separate score
    """
    from_name = result_item.get('from_name', 'label')
    result_type = result_item.get('type', '')
    value = result_item.get('value', {})

    if result_type == 'choices':
        choices = value.get('choices', [])
        if len(choices) == 1:
            return {
                'name': from_name,
                'value': choices[0],
                'data_type': 'CATEGORICAL',
            }
        return [
            {
                'name': from_name,
                'value': choice,
                'data_type': 'CATEGORICAL',
            }
            for choice in choices
        ]
    elif result_type == 'rating':
        return {
            'name': from_name,
            'value': value.get('rating', 0),
            'data_type': 'NUMERIC',
        }
    elif result_type == 'number':
        return {
            'name': from_name,
            'value': value.get('number', 0),
            'data_type': 'NUMERIC',
        }
    elif result_type == 'textarea':
        texts = value.get('text', [])
        text_str = '\n'.join(texts) if isinstance(texts, list) else str(texts)
        return {
            'name': from_name,
            'value': text_str,
            'comment': text_str,
            'data_type': 'CATEGORICAL',
        }
    elif result_type == 'taxonomy':
        taxonomy = value.get('taxonomy', [])
        flat = [' > '.join(path) if isinstance(path, list) else str(path) for path in taxonomy]
        return [
            {
                'name': from_name,
                'value': item,
                'data_type': 'CATEGORICAL',
            }
            for item in flat
        ] if flat else {
            'name': from_name,
            'value': '',
            'data_type': 'CATEGORICAL',
        }
    else:
        import json
        return {
            'name': from_name,
            'value': json.dumps(value, ensure_ascii=False, default=str),
            'comment': json.dumps(value, ensure_ascii=False, default=str),
            'data_type': 'CATEGORICAL',
        }


def _get_langfuse_client_for_project(project):
    """Resolve LangfuseClient: try project's import storage first, then env vars."""
    from io_storages.langfuse.models import LangfuseClient, LangfuseImportStorage

    storage = LangfuseImportStorage.objects.filter(project=project).first()
    if storage:
        return storage.get_client()

    host = os.environ.get('LANGFUSE_HOST', '')
    public_key = os.environ.get('LANGFUSE_PUBLIC_KEY', '')
    secret_key = os.environ.get('LANGFUSE_SECRET_KEY', '')
    if all([host, public_key, secret_key]):
        return LangfuseClient(host=host, public_key=public_key, secret_key=secret_key)

    return None


class LangfuseExportAPI(generics.GenericAPIView):
    permission_required = all_permissions.projects_change

    def get_queryset(self):
        return Project.objects.filter(organization=self.request.user.active_organization)

    @extend_schema(
        tags=['Export'],
        summary='Check if Langfuse export is available for this project',
        description='Returns whether the project has Langfuse traces and a valid connection.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project.',
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        project = self.get_object()
        client = _get_langfuse_client_for_project(project)
        has_traces = Task.objects.filter(
            project=project,
            data__trace_id__isnull=False,
        ).exists()
        return Response({
            'available': client is not None and has_traces,
            'has_connection': client is not None,
            'has_traces': has_traces,
        })

    @extend_schema(
        tags=['Export'],
        summary='Export annotations to Langfuse as scores',
        description='Write annotation results back to Langfuse as scores on the original traces.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='A unique integer value identifying this project.',
            ),
        ],
    )
    def post(self, request, *args, **kwargs):
        project = self.get_object()
        client = _get_langfuse_client_for_project(project)
        if not client:
            return Response(
                {'detail': 'No Langfuse connection found. Configure a Langfuse import storage or set LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY environment variables.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tasks = Task.objects.filter(
            project=project,
            annotations__isnull=False,
        ).filter(
            data__trace_id__isnull=False,
        ).distinct().prefetch_related('annotations')

        exported = 0
        skipped = 0
        queue_completed = 0
        errors = []

        for task in tasks:
            trace_id = task.data.get('trace_id')
            if not trace_id:
                skipped += 1
                continue

            queue_id = task.data.get('langfuse_queue_id')
            queue_item_id = task.data.get('langfuse_queue_item_id')

            config_lookup = {}
            for sc in task.data.get('langfuse_score_configs') or []:
                config_lookup[sc['name']] = sc['id']

            task_exported = False

            for annotation in task.annotations.all():
                if not annotation.result:
                    continue
                for result_item in annotation.result:
                    score_entries = _annotation_result_to_scores(result_item)
                    if not isinstance(score_entries, list):
                        score_entries = [score_entries]

                    for score_params in score_entries:
                        score_name = score_params.get('name', 'label')
                        try:
                            client.create_score(
                                trace_id=trace_id,
                                name=score_name,
                                value=score_params.get('value'),
                                comment=score_params.get('comment'),
                                data_type=score_params.get('data_type'),
                                config_id=config_lookup.get(score_name),
                                queue_id=queue_id,
                            )
                            exported += 1
                            task_exported = True
                        except Exception as e:
                            errors.append(f'Trace {trace_id}, annotation {annotation.id}: {e}')
                            logger.warning(f'Failed to export score for trace {trace_id}: {e}')

            if task_exported and queue_id and queue_item_id:
                try:
                    client.update_queue_item(queue_id, queue_item_id, status='COMPLETED')
                    queue_completed += 1
                except Exception as e:
                    errors.append(f'Queue item {queue_item_id}: {e}')
                    logger.warning(f'Failed to complete queue item {queue_item_id}: {e}')

        return Response({
            'exported': exported,
            'skipped': skipped,
            'queue_completed': queue_completed,
            'errors': errors[:20],
        })
