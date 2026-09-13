"""供素材库恢复创作配方的公开记录；不保存凭据或执行态。"""
import re
from copy import deepcopy

_FIELDS = ('type', 'title', 'creationId', 'creationOwnerNodeId', 'creationDetails',
           'runSettings', 'promptDraftText', 'promptDraftHtml', 'manualInputRefs',
           'runInputRefs', 'runPromptRefs', 'runPrompt', 'runModelPrompt', 'outputKind')
_SECRET = re.compile(r'^(?:api[_-]?key|access[_-]?key|private[_-]?key|key|.*token|.*secret|password|authorization|cookie|credentials?)$', re.I)

def creation_record(node):
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if not _SECRET.search(k)}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return deepcopy(value)
    return clean({k: node[k] for k in _FIELDS if k in node})


def records_for_nodes(nodes):
    """同文件多配方分别登记，不以文件相同推断配方相同。"""
    result = {}
    for node in nodes:
        if not node.get('creationId'):
            continue
        versions = node.get('resultVersions') or [node]
        for version in versions:
            record = creation_record({**node, **version, 'type': node.get('type')})
            record['recordId'] = str(version.get('id') or node['id'])
            for media in version.get('images') or []:
                result_id = str(media.get('resultId') or media.get('result_id') or '')
                if not result_id and str(media.get('url') or '').startswith('/api/results/'):
                    result_id = media['url'].split('/')[-1]
                if result_id:
                    result.setdefault(result_id, {})[record['recordId']] = record
    return result
