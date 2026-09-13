"""laohu 新协议的参数组合校验与 MiniMax V2 请求编码。"""
from copy import deepcopy


def validate_parameters(model, parameters, counts=None, roles=None, metadata=None):
    p = parameters or {}
    counts, roles, metadata = counts or {}, roles or {}, metadata or {}
    if model.startswith('laohu-image-g-v2.5-') and not model.endswith('lowprice'):
        fmt = p.get('output_format', 'png')
        if 'output_compression' in p and fmt == 'png':
            raise ValueError('PNG 不支持压缩率；请选择 JPEG 或 WebP')
        if p.get('background') == 'transparent' and fmt == 'jpeg':
            raise ValueError('透明背景只支持 PNG 或 WebP')
    if model == 'MiniMax-H3':
        drive = p.get('audio_role') == 'drive_audio'
        audio_count = counts.get('audio', roles.get('reference_audio', 0))
        if drive and not audio_count:
            raise ValueError('驱动音频模式需要连接音频素材')
        if audio_count > (4 if drive else 3):
            raise ValueError('最多 3 条参考音频；驱动模式可额外接收 1 条驱动音频')
        if int(p.get('duration', 5)) > 15 and not drive:
            raise ValueError('超过 15 秒的 MiniMax-H3 视频必须提供驱动音频')
        if p.get('aspect_ratio') in {'adaptive', 'auto'} and not (roles.get('first_frame') or roles.get('last_frame')):
            raise ValueError('自适应比例仅支持首帧或尾帧模式')
        if p.get('audio_mode') in {'lock_source', 'remix_source', 'reference_only'} and not drive:
            raise ValueError('当前音轨模式需要驱动音频')
        if p.get('audio_mode') == 'lock_source' and p.get('denoise_strength', 0) != 0:
            raise ValueError('保留原音轨模式的降噪强度必须为 0')
        if p.get('audio_mode') == 'reference_only' and p.get('add_drive_as_reference') is False:
            raise ValueError('仅参考模式不能关闭驱动音频参考')
        offset = p.get('start_time_seconds', 0)
        for item in metadata.get('source_video', []):
            if offset and item.get('duration_seconds', 0) - offset < 2:
                raise ValueError('参考视频起点之后必须至少保留 2 秒')
    if model == 'suno-upload-extend' and 'continue_at' in p:
        for item in metadata.get('reference_audio', []):
            duration = item.get('duration_seconds')
            if duration is not None and p['continue_at'] >= duration:
                raise ValueError('续写起点必须小于源音频时长')


def minimax_h3_body(prompt, images, videos, audios, parameters):
    p = deepcopy(parameters or {})
    audio_role = p.pop('audio_role', 'reference_audio')
    offset = p.pop('start_time_seconds', None)
    roles = {key:sum(1 for item in images if item.get('role') == key) for key in ['first_frame', 'last_frame']}
    semantic = {**p, 'aspect_ratio':p.get('ratio'), 'audio_role':audio_role, 'audio_mode':p.get('audio_control', {}).get('mode'), **p.get('audio_control', {})}
    validate_parameters('MiniMax-H3', semantic, {'audio':len(audios)}, roles)
    content = [{'type':'text', 'text':prompt}]
    for item in images:
        role = item.get('role')
        content.append({'type':'image_url', 'image_url':{'url':item['url']}, 'role':role if role in {'first_frame','last_frame'} else 'reference_image'})
    for url in videos:
        content.append({'type':'video_url', 'video_url':{'url':url}, 'role':'reference_video', **({'start_time_seconds':offset} if offset is not None else {})})
    for index, url in enumerate(audios):
        content.append({'type':'audio_url', 'audio_url':{'url':url}, 'role':'drive_audio' if index == 0 and audio_role == 'drive_audio' else 'reference_audio'})
    return {'model':'MiniMax-H3', 'content':content, **p}
