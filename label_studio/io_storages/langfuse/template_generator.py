"""Generate Label Studio label config XML from Langfuse score configs.

Maps Langfuse score config types to Label Studio annotation controls:
  - CATEGORICAL -> <Choices> with <Choice> per category
  - NUMERIC (range <= 10) -> <Rating>
  - NUMERIC (range > 10 or unbounded) -> <Number>
  - BOOLEAN -> <Choices> with Yes/No
"""

import html
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Inline styles as constants for consistency
_S_TASK_TITLE = 'font-size:16px;font-weight:700;color:#1a1a1a;margin:0 0 2px 0'
_S_TASK_DESC = 'font-size:12px;font-weight:400;color:#888;margin:0 0 8px 0'
_S_SECTION_TITLE = 'font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#999;margin:0;padding:0'
_S_FIELD_LABEL = 'font-size:12px;font-weight:500;color:#666;margin:0 0 4px 0'
_S_DIM_TITLE = 'font-size:13px;font-weight:600;color:#333;margin:0'
_S_DIM_DESC = 'font-size:11px;font-weight:400;color:#999;margin:2px 0 6px 0'
_S_EVAL_HEADER = 'font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#666;margin:0;padding:0'

_STYLE = """
.lf-root {
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 0;
}
.lf-card {
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}
.lf-card-head {
  padding: 10px 16px;
  background: #fafafa;
  border-bottom: 1px solid #eee;
}
.lf-field {
  padding: 12px 16px;
}
.lf-field + .lf-field {
  border-top: 1px solid #f2f2f0;
}
.lf-eval-section {
  border-top: 2px solid #e5e5e5;
  padding-top: 16px;
}
.lf-eval-grid {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.lf-eval-dim {
  padding: 12px 16px;
  border: 1px solid #eee;
  border-radius: 6px;
  background: #fafafa;
}
.lf-notes {
  padding: 0;
}
.lf-meta {
  border: 1px solid #eee;
  border-radius: 6px;
  background: #f8f8f8;
  padding: 10px 16px;
  font-size: 11px;
  color: #999;
}
""".strip()

_DISPLAY_NAME = 'output_text'


def _load_langfuse_template(task_type=None):
    """Load Langfuse annotation template by task type."""
    template_dir = Path(__file__).parent.parent.parent / 'annotation_templates' / 'langfuse'

    if task_type:
        template_file = template_dir / f'{task_type}.json'
        if template_file.exists():
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f'Failed to load template {task_type}: {e}')

    default_file = template_dir / 'default.json'
    if default_file.exists():
        try:
            with open(default_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f'Failed to load default template: {e}')

    return None


def _xml_escape(text):
    return html.escape(str(text), quote=True)


def _generate_control(config):
    return _generate_control_with_toname(config, _DISPLAY_NAME)


def _generate_control_with_toname(config, to_name):
    """Generate Label Studio control tag(s) for a score dimension, wrapped in a card."""
    name = _xml_escape(config.get('name', 'score'))
    data_type = (config.get('dataType') or '').upper()
    label_text = _xml_escape(config.get('name', 'Score'))
    description = config.get('description') or ''

    lines = []
    lines.append(f'        <View className="lf-eval-dim">')
    lines.append(f'          <Header value="{label_text}" size="5" style="{_S_DIM_TITLE}"/>')
    if description:
        lines.append(f'          <Header value="{_xml_escape(description)}" size="6" style="{_S_DIM_DESC}"/>')

    if data_type == 'CATEGORICAL':
        categories = config.get('categories') or []
        lines.append(f'          <Choices name="{name}" toName="{to_name}" choice="single" showInline="true">')
        for cat in categories:
            label = _xml_escape(cat.get('label', cat.get('value', '')))
            lines.append(f'            <Choice value="{label}"/>')
        if not categories:
            lines.append(f'            <Choice value="N/A"/>')
        lines.append(f'          </Choices>')

    elif data_type == 'BOOLEAN':
        lines.append(f'          <Choices name="{name}" toName="{to_name}" choice="single" showInline="true">')
        lines.append(f'            <Choice value="Yes"/>')
        lines.append(f'            <Choice value="No"/>')
        lines.append(f'          </Choices>')

    elif data_type == 'NUMERIC':
        min_val = config.get('minValue')
        max_val = config.get('maxValue')
        if min_val is not None and max_val is not None and (max_val - min_val) <= 10 and min_val >= 0:
            lines.append(f'          <Rating name="{name}" toName="{to_name}" maxRating="{int(max_val)}"/>')
        else:
            attrs = f'name="{name}" toName="{to_name}"'
            if min_val is not None:
                attrs += f' min="{min_val}"'
            if max_val is not None:
                attrs += f' max="{max_val}"'
            lines.append(f'          <Number {attrs}/>')

    else:
        lines.append(f'          <Choices name="{name}" toName="{to_name}" choice="single" showInline="true">')
        lines.append(f'            <Choice value="Pass"/>')
        lines.append(f'            <Choice value="Fail"/>')
        lines.append(f'          </Choices>')

    lines.append(f'        </View>')
    return '\n'.join(lines)


def _build_section(section_title, fields):
    """Build a card section (Input/Output) with grouped fields."""
    field_blocks = []
    for field in fields:
        field_name = _xml_escape(field['name'])
        field_label = _xml_escape(field.get('label', ''))
        field_source = _xml_escape(field['source'])
        field_type = field.get('type', 'text')

        if field_type == 'iframe':
            inner = f'<HyperText name="{field_name}" value="$ppt_viewer_{field_name}"/>'
        elif field_type == 'hypertext':
            inner = f'<HyperText name="{field_name}" value="${field_source}"/>'
        else:
            inner = f'<Text name="{field_name}" value="${field_source}"/>'

        label_line = ''
        if field_label:
            label_line = f'\n          <Header value="{field_label}" size="6" style="{_S_FIELD_LABEL}"/>'

        block = f'''        <View className="lf-field">{label_line}
          {inner}
        </View>'''
        field_blocks.append(block)

    return f'''      <View className="lf-card">
        <View className="lf-card-head">
          <Header value="{_xml_escape(section_title)}" size="6" style="{_S_SECTION_TITLE}"/>
        </View>
{chr(10).join(field_blocks)}
      </View>'''


def generate_label_config(score_configs, task_type=None, queue_name=None, queue_description=None):
    """Generate a complete Label Studio label config XML.

    Uses a single-column flowing layout: header → input → output → eval → notes → metadata.
    """
    if not score_configs:
        return '<View></View>'

    template = _load_langfuse_template(task_type)

    # Task header
    header_block = ''
    if queue_name:
        header_block = f'''
      <Header value="{_xml_escape(queue_name)}" size="3" style="{_S_TASK_TITLE}"/>'''
        if queue_description:
            header_block += f'''
      <Header value="{_xml_escape(queue_description)}" size="6" style="{_S_TASK_DESC}"/>'''

    # Build sections from template
    sections = []
    first_text_name = _DISPLAY_NAME

    if template and template.get('display_config'):
        dc = template['display_config']

        input_fields = dc.get('input_fields', [])
        if input_fields:
            sections.append(_build_section('INPUT', input_fields))
            for f in input_fields:
                if f.get('type', 'text') in ('text', 'hypertext'):
                    first_text_name = _xml_escape(f['name'])
                    break

        output_fields = dc.get('output_fields', [])
        if output_fields:
            sections.append(_build_section('OUTPUT', output_fields))
            if first_text_name == _DISPLAY_NAME:
                for f in output_fields:
                    if f.get('type', 'text') in ('text', 'hypertext'):
                        first_text_name = _xml_escape(f['name'])
                        break
    else:
        sections.append(_build_section('INPUT', [{'name': 'input_text', 'source': 'input'}]))
        sections.append(_build_section('OUTPUT', [{'name': _DISPLAY_NAME, 'source': 'output'}]))

    # Score controls — each wrapped in its own eval-dim card
    controls = '\n'.join(_generate_control_with_toname(cfg, first_text_name) for cfg in score_configs)

    # Notes dim
    notes_block = f'''        <View className="lf-eval-dim">
          <Header value="备注" size="5" style="{_S_DIM_TITLE}"/>
          <TextArea name="annotation_comments" toName="{first_text_name}" rows="3" placeholder="补充说明..."/>
        </View>'''

    xml = f'''<View>
  <Style>{_STYLE}</Style>

  <View className="lf-root">{header_block}

{chr(10).join(sections)}

      <View className="lf-eval-section">
        <Header value="评估" size="5" style="{_S_EVAL_HEADER}"/>
        <View className="lf-eval-grid">
{controls}
{notes_block}
        </View>
      </View>

      <View className="lf-meta">
        <Header value="METADATA" size="6" style="{_S_SECTION_TITLE}"/>
        <Text name="metadata_display" value="$metadata_text"/>
      </View>
  </View>
</View>'''

    return xml


def extract_score_config_summary(score_configs):
    """Extract minimal score config info for storing in task data."""
    return [
        {
            'id': cfg.get('id'),
            'name': cfg.get('name'),
            'dataType': cfg.get('dataType'),
            'description': cfg.get('description'),
        }
        for cfg in score_configs
    ]
