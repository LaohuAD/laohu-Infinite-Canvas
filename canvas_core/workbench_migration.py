"""工作台数据的单向迁移；备份成功后才允许修改作品。"""
import copy
import mimetypes

from canvas_core.json_store import write_json


RETIRED_DIRECTORS = {'smart-video-director', 'smart-minimax-director'}


def assign_node_numbers(canvas):
    nodes = canvas.get('nodes') or []
    valid = [n.get('displayNumber') for n in nodes if isinstance(n.get('displayNumber'), int)
             and not isinstance(n.get('displayNumber'), bool) and n['displayNumber'] > 0]
    counter = max([int(canvas.get('nextNodeNumber') or 1), *[value+1 for value in valid]])
    used = set()
    changed = False
    for node in nodes:
        value = node.get('displayNumber')
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value in used:
            node['displayNumber'] = counter
            counter += 1
            changed = True
        used.add(node['displayNumber'])
    if canvas.get('nextNodeNumber') != counter:
        canvas['nextNodeNumber'] = counter
        changed = True
    return changed


def retire_directors(canvas, backup_root):
    retired = [node for node in canvas.get('nodes', []) if node.get('type') in RETIRED_DIRECTORS]
    if not retired:
        return False
    backup = backup_root / f"{canvas['id']}-directors.json"
    if not backup.exists():
        write_json(backup, copy.deepcopy(canvas))
    for node in retired:
        # 原始结构完整保存在备份；画布保留同一节点 ID、媒体、位置、标题和可读文本。
        body = []
        for key in ('promptDraftText', 'prompt', 'description', 'script'):
            if isinstance(node.get(key), str) and node[key].strip():
                body.append(node[key].strip())
        for index, segment in enumerate(node.get('clips') or node.get('segments') or []):
            if not isinstance(segment, dict):
                continue
            heading = str(segment.get('title') or f'{index+1}')
            parts = [str(segment[key]) for key in ('prompt', 'text', 'description', 'script')
                     if isinstance(segment.get(key), str) and segment[key].strip()]
            if parts:
                body.append('## ' + heading + '\n\n' + '\n\n'.join(dict.fromkeys(parts)))
        # 未识别的历史字段留在迁移备份，正常画布不继续执行旧结构。
        images = copy.deepcopy(node.get('images') or [])
        seen = {item.get('url') for item in images if isinstance(item, dict) and item.get('url')}
        def keep_media(value, fallback=''):
            if isinstance(value, list):
                for item in value:
                    keep_media(item, fallback)
            elif isinstance(value, dict):
                url = value.get('url')
                if isinstance(url, str) and url and url not in seen:
                    mime = value.get('mime') or mimetypes.guess_type(url.split('?')[0])[0] or ''
                    kind = value.get('kind') or value.get('type') or mime.split('/')[0] or fallback
                    if kind in {'image', 'video', 'audio', 'text'}:
                        images.append({**copy.deepcopy(value), 'kind': kind})
                        seen.add(url)
                for key, item in value.items():
                    if isinstance(item, (list, dict)):
                        keep_media(item, key if key in {'image', 'video', 'audio'} else fallback)
        # 原生导演台同时存在 clips/results 与早期 segments/result 两种保存结构。
        for key in ('clips', 'segments', 'assets', 'libraryRefs'):
            keep_media(node.get(key), 'video' if key in {'clips', 'segments'} else '')
        text = '\n\n'.join(dict.fromkeys(body))
        if text:
            images.append({'kind': 'text', 'name': f"{node.get('title') or '历史创作'}.md", 'text': text, 'content': text})
        node.update(type='smart-material', sourceKind='input', images=images, retiredDirector=True,
                    creationDetails=str(node.get('creationDetails') or ''))
        for key in ('segments', 'clips', 'assets', 'libraryRefs', 'adapter', 'directorKind',
                    'selectedClipId', 'selectedSegmentId', 'runSettings', 'running',
                    'pending', 'isRunPlaceholder', 'timelinePlaying'):
            node.pop(key, None)
    return True
