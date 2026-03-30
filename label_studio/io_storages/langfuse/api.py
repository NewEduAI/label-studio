import logging
import os

from django.utils.decorators import method_decorator
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from io_storages.api import (
    ImportStorageDetailAPI,
    ImportStorageFormLayoutAPI,
    ImportStorageListAPI,
    ImportStorageSyncAPI,
    ImportStorageValidateAPI,
)
from io_storages.langfuse.models import LangfuseClient, LangfuseImportStorage, normalize_langfuse_trace
from io_storages.langfuse.serializers import LangfuseImportStorageSerializer
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _get_langfuse_env():
    host = os.environ.get('LANGFUSE_HOST', '')
    public_key = os.environ.get('LANGFUSE_PUBLIC_KEY', '')
    secret_key = os.environ.get('LANGFUSE_SECRET_KEY', '')
    return host, public_key, secret_key


def _get_langfuse_client():
    host, public_key, secret_key = _get_langfuse_env()
    if not all([host, public_key, secret_key]):
        return None
    return LangfuseClient(host=host, public_key=public_key, secret_key=secret_key)


class LangfuseStatusAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Langfuse'],
        summary='Get Langfuse connection status',
        description='Check if Langfuse env vars are configured and connection is healthy.',
    )
    def get(self, request):
        host, public_key, secret_key = _get_langfuse_env()
        configured = all([host, public_key, secret_key])
        if not configured:
            return Response({
                'configured': False,
                'connected': False,
                'host': '',
                'message': 'Langfuse environment variables not set (LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)',
            })
        try:
            client = LangfuseClient(host=host, public_key=public_key, secret_key=secret_key)
            client.health_check()
            return Response({
                'configured': True,
                'connected': True,
                'host': host,
                'message': 'Connected to Langfuse',
            })
        except Exception as e:
            return Response({
                'configured': True,
                'connected': False,
                'host': host,
                'message': f'Connection failed: {e}',
            })


class LangfuseQueuesAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Langfuse'],
        summary='List Langfuse annotation queues',
        description='Get all annotation queues from the connected Langfuse instance.',
    )
    def get(self, request):
        client = _get_langfuse_client()
        if not client:
            return Response(
                {'detail': 'Langfuse not configured'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = client.list_annotation_queues()
            return Response(result)
        except Exception as e:
            logger.error(f'Failed to list Langfuse queues: {e}', exc_info=True)
            return Response(
                {'detail': f'Failed to fetch queues: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class LangfuseQueueImportAPI(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Langfuse'],
        summary='Import traces from a Langfuse annotation queue',
        description='Fetch pending items from a queue, resolve traces, and create Label Studio tasks.',
    )
    def post(self, request):
        queue_id = request.data.get('queue_id')
        project_id = request.data.get('project')
        if not queue_id or not project_id:
            return Response(
                {'detail': 'queue_id and project are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = _get_langfuse_client()
        if not client:
            return Response(
                {'detail': 'Langfuse not configured'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from projects.models import Project
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response(
                {'detail': 'Project not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fetch queue details and score configs
        score_configs = []
        score_config_summary = []
        label_config_generated = False
        try:
            queue_data = client.get_annotation_queue(queue_id)
            config_ids = queue_data.get('scoreConfigIds') or []
            for cid in config_ids:
                try:
                    cfg = client.get_score_config(cid)
                    score_configs.append(cfg)
                except Exception as e:
                    logger.warning(f'Failed to fetch score config {cid}: {e}')
        except Exception as e:
            logger.warning(f'Failed to fetch queue details for {queue_id}: {e}')

        if score_configs:
            from io_storages.langfuse.template_generator import (
                extract_score_config_summary,
                generate_label_config,
            )
            score_config_summary = extract_score_config_summary(score_configs)

            default_configs = {'<View></View>', '<View/>', '', None}
            if project.label_config in default_configs:
                try:
                    xml = generate_label_config(score_configs)
                    project.label_config = xml
                    project.save()
                    label_config_generated = True
                    logger.info(f'Auto-generated label config for project {project_id} from {len(score_configs)} score configs')
                except Exception as e:
                    logger.error(f'Failed to auto-generate label config: {e}', exc_info=True)

        try:
            items = client.list_queue_items(queue_id, status_filter='PENDING')
            queue_items = [
                {'trace_id': item['objectId'], 'queue_item_id': item['id']}
                for item in items if item.get('objectType') == 'TRACE'
            ]
        except Exception as e:
            logger.error(f'Failed to fetch queue items: {e}', exc_info=True)
            return Response(
                {'detail': f'Failed to fetch queue items: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        from tasks.models import Task
        created = 0
        skipped = 0
        errors = []
        for qi in queue_items:
            trace_id = qi['trace_id']
            existing = Task.objects.filter(
                project=project,
                data__trace_id=trace_id,
            ).exists()
            if existing:
                skipped += 1
                continue
            try:
                trace = client.get_trace(trace_id)
                observations = client.list_observations(trace_id)
                task_data = normalize_langfuse_trace(trace, observations)
                task_data['langfuse_queue_id'] = queue_id
                task_data['langfuse_queue_item_id'] = qi['queue_item_id']
                if score_config_summary:
                    task_data['langfuse_score_configs'] = score_config_summary
                Task.objects.create(
                    project=project,
                    data=task_data,
                    overlap=project.maximum_annotations,
                )
                created += 1
            except Exception as e:
                errors.append(f'Trace {trace_id}: {e}')
                logger.warning(f'Failed to import trace {trace_id}: {e}')

        return Response({
            'created': created,
            'skipped': skipped,
            'total': len(queue_items),
            'label_config_generated': label_config_generated,
            'score_configs_count': len(score_configs),
            'errors': errors[:10],
        })


# --- Storage-based APIs (kept for backward compatibility) ---

@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='List Langfuse import storage',
        description='Get a list of all Langfuse import storage connections.',
        parameters=[
            OpenApiParameter(
                name='project',
                type=OpenApiTypes.INT,
                location='query',
                description='Project ID',
                required=True,
            ),
        ],
    ),
)
@method_decorator(
    name='post',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='Create Langfuse import storage',
        description='Create a new Langfuse import storage connection to sync traces as tasks.',
    ),
)
class LangfuseImportStorageListAPI(ImportStorageListAPI):
    queryset = LangfuseImportStorage.objects.all()
    serializer_class = LangfuseImportStorageSerializer


@method_decorator(
    name='get',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='Get Langfuse import storage',
        description='Get a specific Langfuse import storage connection.',
    ),
)
@method_decorator(
    name='patch',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='Update Langfuse import storage',
        description='Update a specific Langfuse import storage connection.',
    ),
)
@method_decorator(
    name='delete',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='Delete Langfuse import storage',
        description='Delete a specific Langfuse import storage connection.',
    ),
)
class LangfuseImportStorageDetailAPI(ImportStorageDetailAPI):
    queryset = LangfuseImportStorage.objects.all()
    serializer_class = LangfuseImportStorageSerializer


@method_decorator(
    name='post',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='Sync Langfuse import storage',
        description='Sync traces from a Langfuse import storage connection.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location='path',
                description='Storage ID',
            ),
        ],
        request=None,
    ),
)
class LangfuseImportStorageSyncAPI(ImportStorageSyncAPI):
    serializer_class = LangfuseImportStorageSerializer


@method_decorator(
    name='post',
    decorator=extend_schema(
        tags=['Storage: Langfuse'],
        summary='Validate Langfuse import storage',
        description='Validate a specific Langfuse import storage connection.',
        responses={200: OpenApiResponse(description='Validation successful')},
    ),
)
class LangfuseImportStorageValidateAPI(ImportStorageValidateAPI):
    serializer_class = LangfuseImportStorageSerializer


class LangfuseImportStorageFormLayoutAPI(ImportStorageFormLayoutAPI):
    pass
