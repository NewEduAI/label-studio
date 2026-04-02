import base64
import json
import logging
from typing import Iterator

import requests
from django.db import models
from django.utils.translation import gettext_lazy as _
from io_storages.base_models import ImportStorage, ImportStorageLink, ProjectStorageMixin
from io_storages.utils import StorageObject

logger = logging.getLogger(__name__)


class LangfuseClient:
    """Lightweight HTTP client for the Langfuse public API."""

    def __init__(self, host: str, public_key: str, secret_key: str, timeout: int = 30):
        self.host = host.rstrip('/')
        self.timeout = timeout
        token = base64.b64encode(f'{public_key}:{secret_key}'.encode()).decode()
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
        })

    def list_traces(self, limit: int = 50, page: int = 1, from_ts: str = None, to_ts: str = None):
        params = {'limit': limit, 'page': page}
        if from_ts:
            params['fromTimestamp'] = from_ts
        if to_ts:
            params['toTimestamp'] = to_ts
        r = self.session.get(f'{self.host}/api/public/traces', params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_trace(self, trace_id: str):
        r = self.session.get(f'{self.host}/api/public/traces/{trace_id}', timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def list_observations(self, trace_id: str, limit: int = 200):
        results = []
        page = 1
        page_size = min(max(limit, 1), 100)
        while True:
            r = self.session.get(
                f'{self.host}/api/public/observations',
                params={'traceId': trace_id, 'page': page, 'limit': page_size},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json().get('data') or []
            results.extend(data)
            if len(data) < page_size:
                break
            page += 1
        return results

    def health_check(self):
        r = self.session.get(f'{self.host}/api/public/traces', params={'limit': 1}, timeout=self.timeout)
        r.raise_for_status()

    def list_annotation_queues(self):
        r = self.session.get(f'{self.host}/api/public/annotation-queues', params={'limit': 50}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_annotation_queue(self, queue_id: str):
        r = self.session.get(f'{self.host}/api/public/annotation-queues/{queue_id}', timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_score_config(self, config_id: str):
        r = self.session.get(f'{self.host}/api/public/score-configs/{config_id}', timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def create_score(self, trace_id: str, name: str, value=None,
                     comment=None, data_type=None, observation_id=None,
                     config_id=None, queue_id=None):
        """Create a score on a trace.

        Per Langfuse API: CATEGORICAL scores pass the string label as `value`,
        NUMERIC scores pass the number as `value`.
        """
        payload = {'traceId': trace_id, 'name': name}
        if value is not None:
            payload['value'] = value
        if comment is not None:
            payload['comment'] = comment
        if data_type is not None:
            payload['dataType'] = data_type
        if observation_id is not None:
            payload['observationId'] = observation_id
        if config_id is not None:
            payload['configId'] = config_id
        if queue_id is not None:
            payload['queueId'] = queue_id
        r = self.session.post(f'{self.host}/api/public/scores', json=payload, timeout=self.timeout)
        if not r.ok:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise ValueError(f'{r.status_code} {r.reason}: {detail} (payload: {payload})')
        return r.json()

    def update_queue_item(self, queue_id: str, item_id: str, status: str = 'COMPLETED'):
        r = self.session.patch(
            f'{self.host}/api/public/annotation-queues/{queue_id}/items/{item_id}',
            json={'status': status},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def list_queue_items(self, queue_id: str, status_filter: str = None, limit: int = 200):
        results = []
        page = 1
        while True:
            params = {'limit': min(limit, 50), 'page': page}
            if status_filter:
                params['status'] = status_filter
            r = self.session.get(
                f'{self.host}/api/public/annotation-queues/{queue_id}/items',
                params=params,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json().get('data') or []
            results.extend(data)
            if len(data) < params['limit'] or len(results) >= limit:
                break
            page += 1
        return results[:limit]


def normalize_langfuse_trace(trace, observations):
    """Convert a Langfuse trace + observations into Label Studio task data.

    Uses task adapters for type-specific extraction.
    """
    from io_storages.langfuse.task_adapters import normalize_trace_for_labeling
    return normalize_trace_for_labeling(trace, observations)


class LangfuseStorageMixin(models.Model):
    langfuse_host = models.TextField(
        _('langfuse host'), null=False, blank=False,
        help_text='Langfuse instance URL (e.g. https://cloud.langfuse.com)',
    )
    langfuse_public_key = models.TextField(
        _('langfuse public key'), null=False, blank=False,
        help_text='Langfuse public API key',
    )
    langfuse_secret_key = models.TextField(
        _('langfuse secret key'), null=False, blank=False,
        help_text='Langfuse secret API key',
    )
    trace_limit = models.PositiveIntegerField(
        _('trace limit'), default=100,
        help_text='Maximum number of traces to sync per batch',
    )
    trace_name_filter = models.TextField(
        _('trace name filter'), null=True, blank=True,
        help_text='Only sync traces matching this name (optional)',
    )
    trace_tag_filter = models.TextField(
        _('trace tag filter'), null=True, blank=True,
        help_text='Only sync traces with this tag (optional)',
    )

    def get_client(self) -> LangfuseClient:
        return LangfuseClient(
            host=self.langfuse_host,
            public_key=self.langfuse_public_key,
            secret_key=self.langfuse_secret_key,
        )

    def validate_connection(self, client=None):
        if client is None:
            client = self.get_client()
        client.health_check()

    @property
    def path_full(self):
        return f'langfuse://{self.langfuse_host}'

    @property
    def type_full(self):
        return 'Langfuse'

    class Meta:
        abstract = True


class LangfuseImportStorageBase(LangfuseStorageMixin, ImportStorage):
    url_scheme = 'langfuse'

    def iter_objects(self) -> Iterator:
        client = self.get_client()
        page = 1
        fetched = 0
        while fetched < self.trace_limit:
            batch_size = min(50, self.trace_limit - fetched)
            result = client.list_traces(limit=batch_size, page=page)
            traces = result.get('data') or result.get('traces') or []
            if not traces:
                break
            for trace in traces:
                if self.trace_name_filter and trace.get('name') != self.trace_name_filter:
                    continue
                if self.trace_tag_filter:
                    trace_tags = trace.get('tags') or []
                    if self.trace_tag_filter not in trace_tags:
                        continue
                yield trace
                fetched += 1
                if fetched >= self.trace_limit:
                    break
            page += 1

    def iter_keys(self) -> Iterator[str]:
        for trace in self.iter_objects():
            yield trace.get('id') or trace.get('traceId')

    def get_unified_metadata(self, obj):
        return {
            'key': obj.get('id') or obj.get('traceId'),
            'last_modified': obj.get('updatedAt') or obj.get('createdAt'),
            'size': 0,
        }

    def get_data(self, key) -> list[StorageObject]:
        client = self.get_client()
        trace = client.get_trace(key)
        observations = client.list_observations(key)
        task_data = normalize_langfuse_trace(trace, observations)
        return [StorageObject(key=key, task_data=task_data)]

    def scan_and_create_links(self):
        return self._scan_and_create_links(LangfuseImportStorageLink)

    def generate_http_url(self, url):
        return url

    class Meta:
        abstract = True


class LangfuseImportStorage(ProjectStorageMixin, LangfuseImportStorageBase):
    class Meta:
        abstract = False


class LangfuseImportStorageLink(ImportStorageLink):
    storage = models.ForeignKey(LangfuseImportStorage, on_delete=models.CASCADE, related_name='links')
