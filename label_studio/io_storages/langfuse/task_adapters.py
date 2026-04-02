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

    def extract(self) -> Dict[str, Any]:
        """Extract chat data including snapshots and turns."""
        base_data = super().extract()

        initial_snapshot = self.metadata.get('initial_module_snapshot', {})
        final_snapshot = self.metadata.get('final_module_snapshot', {})

        # Generate PPT viewer HTML for snapshots
        base_data['ppt_viewer_initial_ppt'] = self._build_viewer_html(
            'initial', initial_snapshot
        )
        base_data['ppt_viewer_final_ppt'] = self._build_viewer_html(
            'final', final_snapshot
        )

        # Session history as readable text
        session_history = self.metadata.get('initial_session_history', [])
        base_data['session_history'] = self._format_session_history(session_history)

        return base_data

    def _build_viewer_html(self, field_id: str, snapshot: Dict) -> str:
        """Build HTML string with embedded iframe + postMessage for PPT viewer."""
        if not snapshot:
            return '<div style="padding:20px;color:#999;">无快照数据</div>'

        snapshot_json = json.dumps(snapshot, ensure_ascii=False)

        return (
            f'<div style="position:relative;width:100%;height:450px;border-radius:8px;overflow:hidden;">'
            f'<iframe id="ppt-{field_id}" src="/static/pptist/viewer.html" '
            f'style="width:100%;height:100%;border:none;"></iframe>'
            f'<script>'
            f'(function(){{'
            f'var data={snapshot_json};'
            f'var iframe=document.getElementById("ppt-{field_id}");'
            f'window.addEventListener("message",function(e){{'
            f'if(e.data&&e.data.type==="viewer-ready"&&e.source===iframe.contentWindow){{'
            f'iframe.contentWindow.postMessage({{type:"load-snapshot",snapshot:data}},"*");'
            f'}}'
            f'}});'
            f'}})();'
            f'</script>'
            f'</div>'
        )

    @staticmethod
    def _format_session_history(history: list) -> str:
        """Format session history as readable text."""
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


