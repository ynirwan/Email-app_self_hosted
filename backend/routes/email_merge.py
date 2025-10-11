import re

def merge_template(template_json, field_map):
    html = template_json.get('html', '')
    for key, value in field_map.items():
        html = re.sub(r'{{\s*' + re.escape(key) + r'\s*}}', value, html)
    return html

