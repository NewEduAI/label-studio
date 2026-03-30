"""Generate Label Studio label config XML from Langfuse score configs.

Maps Langfuse score config types to Label Studio annotation controls:
  - CATEGORICAL -> <Choices> with <Choice> per category
  - NUMERIC (range <= 10) -> <Rating>
  - NUMERIC (range > 10 or unbounded) -> <Number>
  - BOOLEAN -> <Choices> with Yes/No

Layout: left-right with two visual layers.
  Left (top layer): three floating cards — Input, Output, Metadata.
  Right (bottom layer): evaluation controls in a sticky sidebar.
"""

import html
import logging

logger = logging.getLogger(__name__)

_STYLE = """
.lf-root {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}
.lf-left {
  flex: 2;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lf-right {
  flex: 1;
  min-width: 220px;
}
.lf-card {
  border: 1px solid var(--color-neutral-border, #e0e0e0);
  border-radius: 12px;
  padding: 20px;
  background: var(--color-neutral-background, #fff);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}
.lf-card-title {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-neutral-content-subtle, #888);
}
.lf-meta-card {
  border: 1px solid var(--color-neutral-border, #e0e0e0);
  border-radius: 12px;
  padding: 16px 20px;
  background: var(--color-neutral-surface, #f8f8f8);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  font-size: 0.85em;
  color: var(--color-neutral-content-subtle, #666);
}
.lf-eval-panel {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
""".strip()

_DISPLAY_NAME = 'output_text'


def _xml_escape(text):
    return html.escape(str(text), quote=True)


def _generate_control(config):
    """Generate Label Studio control tag(s) from a Langfuse score config."""
    name = _xml_escape(config.get('name', 'score'))
    data_type = (config.get('dataType') or '').upper()
    label_text = _xml_escape(config.get('name', 'Score'))

    lines = []
    lines.append(f'        <Header value="{label_text}" size="5"/>')

    if data_type == 'CATEGORICAL':
        categories = config.get('categories') or []
        lines.append(f'        <Choices name="{name}" toName="{_DISPLAY_NAME}" choice="single" showInline="true">')
        for cat in categories:
            label = _xml_escape(cat.get('label', cat.get('value', '')))
            lines.append(f'          <Choice value="{label}"/>')
        if not categories:
            lines.append(f'          <Choice value="N/A"/>')
        lines.append(f'        </Choices>')

    elif data_type == 'BOOLEAN':
        lines.append(f'        <Choices name="{name}" toName="{_DISPLAY_NAME}" choice="single" showInline="true">')
        lines.append(f'          <Choice value="Yes"/>')
        lines.append(f'          <Choice value="No"/>')
        lines.append(f'        </Choices>')

    elif data_type == 'NUMERIC':
        min_val = config.get('minValue')
        max_val = config.get('maxValue')
        if min_val is not None and max_val is not None and (max_val - min_val) <= 10 and min_val >= 0:
            lines.append(f'        <Rating name="{name}" toName="{_DISPLAY_NAME}" maxRating="{int(max_val)}"/>')
        else:
            attrs = f'name="{name}" toName="{_DISPLAY_NAME}"'
            if min_val is not None:
                attrs += f' min="{min_val}"'
            if max_val is not None:
                attrs += f' max="{max_val}"'
            lines.append(f'        <Number {attrs}/>')

    else:
        lines.append(f'        <Choices name="{name}" toName="{_DISPLAY_NAME}" choice="single" showInline="true">')
        lines.append(f'          <Choice value="Pass"/>')
        lines.append(f'          <Choice value="Fail"/>')
        lines.append(f'        </Choices>')

    return '\n'.join(lines)


def generate_label_config(score_configs):
    """Generate a complete Label Studio label config XML from Langfuse score configs.

    Layout: left-right with two visual layers.
      Left (top layer): three floating cards — Input, Output, Metadata.
      Right (bottom layer): evaluation controls in a sticky sidebar.

    Args:
        score_configs: list of Langfuse score config dicts, each with keys:
            id, name, dataType, categories (optional), minValue/maxValue (optional)

    Returns:
        XML string suitable for project.label_config
    """
    if not score_configs:
        return '<View></View>'

    controls = '\n\n'.join(_generate_control(cfg) for cfg in score_configs)

    controls += f'''

        <Header value="备注" size="5"/>
        <TextArea name="annotation_comments" toName="{_DISPLAY_NAME}" rows="3" placeholder="补充说明..."/>'''

    xml = f'''<View>
  <Style>{_STYLE}</Style>

  <View className="lf-root">
    <View className="lf-left">
      <View className="lf-card">
        <View className="lf-card-title">Input</View>
        <Text name="input_text" value="$input"/>
      </View>

      <View className="lf-card">
        <View className="lf-card-title">Output</View>
        <Text name="{_DISPLAY_NAME}" value="$output"/>
      </View>

      <View className="lf-meta-card">
        <View className="lf-card-title">Metadata</View>
        <Text name="metadata_display" value="$metadata_text"/>
      </View>
    </View>

    <View className="lf-right">
      <View className="lf-eval-panel">
{controls}
      </View>
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
        }
        for cfg in score_configs
    ]
