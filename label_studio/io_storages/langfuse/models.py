import base64
import json
import logging
from datetime import datetime
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


def _to_str(x):
    if x is None:
        return ''
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(x)


def _extract_content(obj):
    if obj is None:
        return ''
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for key in ('content', 'text', 'input', 'output', 'result'):
            if isinstance(obj.get(key), str) and obj[key].strip():
                return obj[key]
        return _to_str(obj)
    if isinstance(obj, list):
        parts = [_extract_content(item) for item in obj if _extract_content(item).strip()]
        return '\n'.join(parts) if parts else _to_str(obj)
    return str(obj)


def _normalize_usage(obs):
    raw = obs.get('usageDetails') or obs.get('usage')
    if not isinstance(raw, dict):
        return None
    return {
        'input_tokens': raw.get('inputTokens') or raw.get('input_tokens') or raw.get('input') or 0,
        'output_tokens': raw.get('outputTokens') or raw.get('output_tokens') or raw.get('output') or 0,
    }


def _duration_ms(start_str, end_str):
    if not start_str or not end_str:
        return None
    try:
        def _parse(s):
            return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        return int((_parse(end_str) - _parse(start_str)).total_seconds() * 1000)
    except (ValueError, TypeError):
        return None


def normalize_langfuse_trace(trace, observations):
    """Convert a Langfuse trace + observations into Label Studio task data.

    Produces two formats simultaneously:
    - 'turns' array for chat-eval / trace-review templates (Paragraphs component)
    - 'input' / 'output' strings for generic-eval template (Text component)
    """
    trace_id = trace.get('id') or trace.get('traceId')
    obs_sorted = sorted(observations, key=lambda o: o.get('startTime') or o.get('createdAt') or '')
    turns = []
    turn_counter = 0
    seen_user_messages = set()

    def add_turn(role, content, **kwargs):
        nonlocal turn_counter
        if not content or not content.strip():
            return
        turn = {
            'turn_id': f'turn_{turn_counter}',
            'role': role,
            'content': content.strip(),
        }
        for k in ('model', 'usage', 'tool_calls', 'tool_name', 'tool_input', 'duration_ms'):
            if kwargs.get(k) is not None:
                turn[k] = kwargs[k]
        turns.append(turn)
        turn_counter += 1

    for obs in obs_sorted:
        otype = (obs.get('type') or '').upper()
        ts = obs.get('startTime') or obs.get('createdAt') or ''
        duration = _duration_ms(obs.get('startTime') or obs.get('createdAt'), obs.get('endTime'))
        inp, out = obs.get('input'), obs.get('output')

        if otype == 'GENERATION':
            if isinstance(inp, list):
                for msg in inp:
                    if isinstance(msg, dict) and msg.get('role') == 'user':
                        content = msg.get('content', '')
                        if isinstance(content, list):
                            content = ' '.join(
                                p.get('text', '') if isinstance(p, dict) else str(p) for p in content
                            )
                        if content and content.strip():
                            msg_key = content[:200]
                            if msg_key not in seen_user_messages:
                                seen_user_messages.add(msg_key)
                                add_turn('user', content)

            if isinstance(out, dict):
                raw_content = out.get('content', '')
                tool_calls = []
                for tc in out.get('tool_calls', []):
                    if isinstance(tc, dict):
                        tool_calls.append({
                            'tool_name': tc.get('name', 'unknown'),
                            'input': _to_str(tc.get('args', tc.get('input', ''))),
                            'call_id': tc.get('id', ''),
                        })

                assistant_content = raw_content if isinstance(raw_content, str) else _extract_content(raw_content)
                if assistant_content and assistant_content.strip():
                    add_turn(
                        'assistant', assistant_content,
                        model=obs.get('model') or obs.get('providedModelName'),
                        usage=_normalize_usage(obs),
                        tool_calls=tool_calls if tool_calls else None,
                        duration_ms=duration,
                    )

        elif otype == 'TOOL':
            tool_name = obs.get('name') or 'unknown'
            tool_output = _extract_content(out) if out else ''
            if tool_output:
                add_turn(
                    'tool', f'[{tool_name}] {tool_output}',
                    tool_name=tool_name,
                    tool_input=_to_str(inp) if inp else '',
                    duration_ms=duration,
                )

    if not turns:
        if trace_input := _extract_content(trace.get('input')):
            add_turn('user', trace_input)
        if trace_output := _extract_content(trace.get('output')):
            add_turn('assistant', trace_output)

    input_text = _extract_content(trace.get('input')) or (
        '\n'.join(t['content'] for t in turns if t['role'] == 'user')
    )
    output_text = _extract_content(trace.get('output')) or (
        '\n'.join(t['content'] for t in turns if t['role'] == 'assistant')
    )

    metadata = {
        'trace_id': str(trace_id),
        'session_id': str(trace.get('sessionId') or trace_id),
        'source': 'langfuse',
        'name': trace.get('name'),
        'tags': trace.get('tags') or [],
        'start_time': trace.get('timestamp') or trace.get('createdAt') or '',
    }

    return {
        'trace_id': str(trace_id),
        'input': input_text,
        'output': output_text,
        'turns': turns,
        'context': trace.get('name') or '',
        'metadata_text': json.dumps(metadata, indent=2, default=str, ensure_ascii=False),
        'trace_summary': (
            f"Trace: {str(trace_id)[:12]}... | "
            f"Session: {metadata['session_id'][:20]} | "
            f"Source: langfuse | Turns: {len(turns)}"
        ),
    }


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
