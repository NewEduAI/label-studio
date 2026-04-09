"""Task adapters for converting Langfuse traces to Label Studio format.

Each adapter extracts task-specific data for template rendering.
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class BaseTaskAdapter:
    """Base adapter for task data extraction."""

    def __init__(self, trace: Dict[str, Any], observations: List[Dict[str, Any]]):
        self.trace = trace
        self.observations = observations
        self.trace_id = trace.get('id') or trace.get('traceId')
        self.metadata = trace.get('metadata', {})

    def extract(self) -> Dict[str, Any]:
        """Extract data for Label Studio template."""
        return {
            'trace_id': str(self.trace_id),
            'input': self._extract_input(),
            'output': self._extract_output(),
            'metadata_text': self._extract_metadata_text(),
        }

    def _extract_input(self) -> str:
        """Extract input text."""
        return self._extract_content(self.trace.get('input'))

    def _extract_output(self) -> str:
        """Extract output text."""
        return self._extract_content(self.trace.get('output'))

    def _extract_metadata_text(self) -> str:
        """Extract metadata as JSON string."""
        meta = {
            'trace_id': str(self.trace_id),
            'session_id': str(self.trace.get('sessionId') or self.trace_id),
            'source': 'langfuse',
            'name': self.trace.get('name'),
            'tags': self.trace.get('tags') or [],
            'start_time': self.trace.get('timestamp') or self.trace.get('createdAt') or '',
        }
        return json.dumps(meta, indent=2, default=str, ensure_ascii=False)

    @staticmethod
    def _extract_content(obj):
        """Extract content from various object types."""
        if obj is None:
            return ''
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            for key in ('content', 'text', 'input', 'output', 'result'):
                if isinstance(obj.get(key), str) and obj[key].strip():
                    return obj[key]
            return json.dumps(obj, indent=2, default=str, ensure_ascii=False)
        if isinstance(obj, list):
            parts = [BaseTaskAdapter._extract_content(item) for item in obj]
            return '\n'.join(p for p in parts if p.strip())
        return str(obj)


class LecgenGenerateAdapter(BaseTaskAdapter):
    """Adapter for lecgen_generate task."""

    def _extract_input(self) -> str:
        """Extract PPT page text content."""
        trace_input = self.trace.get('input') or {}
        images = trace_input.get('kwargs', {}).get('request', {}).get('images', [])
        texts = [img.get('text_content', '') for img in images if img.get('text_content')]
        if not texts:
            return self._extract_content(trace_input)
        return '\n\n'.join(f'第{i+1}页：{t}' for i, t in enumerate(texts))

    def _extract_output(self) -> str:
        """Extract generated slides scripts."""
        trace_output = self.trace.get('output') or {}
        slides = trace_output.get('slides', {})
        if not slides:
            return self._extract_content(trace_output)
        return '\n\n'.join(f'第{k}页讲稿：{v}' for k, v in slides.items())


class ChatAdapter(BaseTaskAdapter):
    """Adapter for chat task with snapshots and conversation."""

    _CHAT_STYLES = """
    <style>
    .chat-history { display:flex; flex-direction:column; gap:8px; font-size:13px; line-height:1.5; }
    .chat-msg { max-width:85%; padding:8px 12px; border-radius:10px; word-break:break-word; }
    .chat-user { align-self:flex-end; background:#e3f2fd; color:#1a1a1a; border-bottom-right-radius:2px; }
    .chat-assistant { align-self:flex-start; background:#f5f5f5; color:#333; border-bottom-left-radius:2px; }
    .chat-role { font-size:11px; font-weight:600; color:#888; margin-bottom:2px; }
    .chat-tool { align-self:flex-start; max-width:90%; }
    .chat-tool summary { cursor:pointer; font-size:12px; color:#888; padding:4px 8px; background:#fafafa; border:1px solid #eee; border-radius:6px; user-select:none; }
    .chat-tool summary:hover { background:#f0f0f0; }
    .chat-tool pre { margin:6px 0 0 0; padding:8px; background:#f8f8f8; border:1px solid #eee; border-radius:4px; font-size:11px; max-height:200px; overflow:auto; white-space:pre-wrap; word-break:break-all; }
    .chat-system { align-self:center; font-size:11px; color:#999; font-style:italic; padding:4px 12px; background:#fff8e1; border-radius:10px; }
    </style>
    """.strip()

    def extract(self) -> Dict[str, Any]:
        """Extract chat data including snapshots and turns."""
        base_data = super().extract()

        initial_snapshot = self.metadata.get('initial_module_snapshot', {})
        final_snapshot = self.metadata.get('final_module_snapshot', {})

        base_data['ppt_viewer_initial_ppt'] = self._build_viewer_html(
            'initial', initial_snapshot
        )
        base_data['ppt_viewer_final_ppt'] = self._build_viewer_html(
            'final', final_snapshot
        )

        session_history = self.metadata.get('initial_session_history', [])
        base_data['session_history'] = self._format_session_history_text(session_history)
        base_data['session_history_html'] = self._format_session_history_html(session_history)

        return base_data

    def _build_viewer_html(self, field_id: str, snapshot: Dict) -> str:
        """Build HTML string with embedded iframe for PPT viewer."""
        if not snapshot:
            return '<div style="padding:20px;color:#999;">无快照数据</div>'

        import base64
        snapshot_b64 = base64.b64encode(
            json.dumps(snapshot, ensure_ascii=False).encode('utf-8')
        ).decode('ascii')

        return (
            f'<div style="position:relative;width:100%;aspect-ratio:16/9;border-radius:8px;overflow:hidden;">'
            f'<iframe src="/static/pptist/viewer.html#snapshot={snapshot_b64}" '
            f'style="width:100%;height:100%;border:none;"></iframe>'
            f'</div>'
        )

    @staticmethod
    def _format_session_history_text(history: list) -> str:
        """Format session history as plain text fallback."""
        if not history:
            return ''
        lines = []
        for msg in history:
            if not isinstance(msg, dict):
                continue
            role = msg.get('role', 'unknown')
            content = msg.get('content') or ''
            if isinstance(content, list):
                content = ' '.join(
                    p.get('text', '') if isinstance(p, dict) else str(p) for p in content
                )
            if not isinstance(content, str):
                content = str(content)
            lines.append(f'[{role}] {content[:500]}')
        return '\n\n'.join(lines)

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters."""
        import html
        return html.escape(str(text))

    @classmethod
    def _format_session_history_html(cls, history: list) -> str:
        """Format session history as styled HTML with chat bubbles."""
        if not history:
            return '<div style="color:#999;">无会话历史</div>'

        bubbles = []
        for msg in history:
            if not isinstance(msg, dict):
                continue
            role = msg.get('role', 'unknown')
            content = msg.get('content') or ''

            if isinstance(content, list):
                content = ' '.join(
                    p.get('text', '') if isinstance(p, dict) else str(p) for p in content
                )
            if not isinstance(content, str):
                content = str(content)

            if role == 'tool':
                bubbles.append(cls._render_tool_bubble(content))
            elif role == 'system':
                bubbles.append(
                    f'<div class="chat-msg chat-system">{cls._escape_html(content[:300])}</div>'
                )
            elif role == 'user':
                escaped = cls._escape_html(content).replace('\n', '<br/>')
                bubbles.append(
                    f'<div class="chat-msg chat-user">'
                    f'<div class="chat-role">用户</div>'
                    f'{escaped}</div>'
                )
            else:
                # assistant or other roles
                escaped = cls._escape_html(content).replace('\n', '<br/>')
                bubbles.append(
                    f'<div class="chat-msg chat-assistant">'
                    f'<div class="chat-role">助手</div>'
                    f'{escaped}</div>'
                )

        return f'{cls._CHAT_STYLES}<div class="chat-history">{"".join(bubbles)}</div>'

    @classmethod
    def _render_tool_bubble(cls, content: str) -> str:
        """Render tool message as a collapsible summary."""
        summary = '工具调用结果'
        detail_content = content

        # Try to parse JSON and extract a meaningful summary
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                success = data.get('success')
                name = data.get('name') or data.get('tool') or ''
                if success is True:
                    summary = f'&#10003; {name} 执行成功' if name else '&#10003; 工具执行成功'
                elif success is False:
                    error = data.get('error') or data.get('message') or '未知错误'
                    summary = f'&#10007; {name} 执行失败' if name else f'&#10007; 工具执行失败'
                elif name:
                    summary = f'&#9881; {name}'
                detail_content = json.dumps(data, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

        escaped_detail = cls._escape_html(detail_content)
        return (
            f'<details class="chat-tool">'
            f'<summary>{summary}</summary>'
            f'<pre>{escaped_detail}</pre>'
            f'</details>'
        )

    def _extract_input(self) -> str:
        """Extract user message."""
        return self.metadata.get('user_input', {}).get('message', '')

    def _extract_output(self) -> str:
        """Extract AI responses."""
        turns = self._extract_turns()
        return '\n'.join(t['content'] for t in turns if t['role'] == 'assistant')

    def _extract_turns(self) -> List[Dict[str, str]]:
        """Extract conversation turns from observations."""
        obs_sorted = sorted(
            self.observations,
            key=lambda o: o.get('startTime') or o.get('createdAt') or ''
        )
        turns = []
        for obs in obs_sorted:
            otype = (obs.get('type') or '').upper()
            if otype == 'GENERATION':
                out = obs.get('output', {})
                if isinstance(out, dict):
                    content = out.get('content', '')
                    if content:
                        turns.append({'role': 'assistant', 'content': str(content)})
        return turns


class LecgenPolishAdapter(BaseTaskAdapter):
    """Adapter for lecgen_polish task."""

    def _extract_input(self) -> str:
        """Extract current script + PPT content for context."""
        trace_input = self.trace.get('input') or {}
        req = trace_input.get('kwargs', {}).get('request', {})
        parts = []
        if req.get('ppt_content'):
            parts.append(f'PPT内容：{req["ppt_content"]}')
        if req.get('current_script'):
            parts.append(f'当前讲稿：{req["current_script"]}')
        if req.get('previous_script'):
            parts.append(f'上一页讲稿：{req["previous_script"]}')
        if req.get('user_prompt'):
            parts.append(f'用户要求：{req["user_prompt"]}')
        return '\n\n'.join(parts) if parts else self._extract_content(trace_input)

    def _extract_output(self) -> str:
        """Extract polished script."""
        trace_output = self.trace.get('output') or {}
        return trace_output.get('polished_script') or self._extract_content(trace_output)


class LecgenTopicAdapter(BaseTaskAdapter):
    """Adapter for lecgen_topic task."""

    def _extract_input(self) -> str:
        """Extract user message/requirements."""
        trace_input = self.trace.get('input') or {}
        req = trace_input.get('kwargs', {}).get('request', {})
        return req.get('message') or req.get('requirements') or self._extract_content(trace_input)

    def _extract_output(self) -> str:
        """Extract generated title."""
        trace_output = self.trace.get('output') or {}
        return trace_output.get('title') or self._extract_content(trace_output)


class ModuleContentAdapter(BaseTaskAdapter):
    """Adapter for module_content / canvas_generate task."""

    def _extract_input(self) -> str:
        """Extract lesson plan or requirements."""
        trace_input = self.trace.get('input') or {}
        req = trace_input.get('kwargs', {}).get('request', trace_input.get('kwargs', {}))
        return req.get('lesson_plan') or req.get('requirements') or self._extract_content(trace_input)

    def _extract_output(self) -> str:
        """Extract generated content."""
        trace_output = self.trace.get('output') or {}
        return self._extract_content(trace_output)


# Adapter registry
TASK_ADAPTERS = {
    'lecgen_generate': LecgenGenerateAdapter,
    'lecgen_polish': LecgenPolishAdapter,
    'lecgen_topic': LecgenTopicAdapter,
    'chat': ChatAdapter,
    'module_content': ModuleContentAdapter,
    'canvas_generate': ModuleContentAdapter,
}


def get_adapter(trace: Dict[str, Any], observations: List[Dict[str, Any]]) -> BaseTaskAdapter:
    """Get appropriate adapter for task type."""
    task_type = trace.get('metadata', {}).get('task_type')
    adapter_class = TASK_ADAPTERS.get(task_type, BaseTaskAdapter)
    return adapter_class(trace, observations)


def normalize_trace_for_labeling(trace: Dict[str, Any], observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Main entry point: normalize trace data for Label Studio."""
    adapter = get_adapter(trace, observations)
    return adapter.extract()


