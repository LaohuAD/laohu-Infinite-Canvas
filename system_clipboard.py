"""本机素材剪贴板：传递原文件与图片数据，不把网址伪装成素材。"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

_LOCK = threading.Lock()
_MAC_SCRIPT = r'''
ObjC.import('AppKit'); ObjC.import('Foundation');
function run(argv) {
    var data=JSON.parse(argv[0]), board=$.NSPasteboard.generalPasteboard, entries=[];
    if(data.text !== undefined) {
        var entry=$.NSPasteboardItem.alloc.init;
        entry.setStringForType($(data.text), $('public.utf8-plain-text'));
        entries.push(entry);
    } else data.paths.forEach(function(path) {
        var entry=$.NSPasteboardItem.alloc.init;
        entry.setStringForType($.NSURL.fileURLWithPath($(path)).absoluteString, $('public.file-url'));
        if(data.paths.length===1 && data.image) {
            var image=$.NSImage.alloc.initWithContentsOfFile($(path));
            if(!image.js) throw Error('Cannot decode image');
            entry.setDataForType(image.TIFFRepresentation, $('public.tiff'));
            var bitmap=$.NSBitmapImageRep.imageRepWithData(image.TIFFRepresentation);
            entry.setDataForType(bitmap.representationUsingTypeProperties($.NSPNGFileType,$({})), $('public.png'));
        }
        entries.push(entry);
    });
    board.clearContents;
    if(!board.writeObjects($(entries))) throw Error('Clipboard write failed');
    return 'ok';
}
'''
_WINDOWS_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$payload = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:LAOHU_CLIPBOARD_PAYLOAD)) | ConvertFrom-Json
$data = New-Object System.Windows.Forms.DataObject
$image = $null
try {
    if ($null -ne $payload.text) { $data.SetText([string]$payload.text) }
    else {
        $files = New-Object System.Collections.Specialized.StringCollection
        foreach ($path in $payload.paths) { [void]$files.Add([string]$path) }
        $data.SetFileDropList($files)
        if ($payload.image -and $files.Count -eq 1) {
            $image = [System.Drawing.Image]::FromFile([string]$payload.image_path)
            $data.SetImage($image)
        }
    }
    [System.Windows.Forms.Clipboard]::SetDataObject($data, $true, 5, 100)
    Write-Output 'ok'
} finally { if ($image) { $image.Dispose() } }
'''


def write_clipboard(paths=(), text=None):
    paths = [str(Path(path).resolve()) for path in paths]
    if text is None and (not paths or any(not Path(p).is_file() for p in paths)):
        raise ValueError('复制的素材文件不存在')
    image = len(paths) == 1 and Path(paths[0]).suffix.lower() in {'.png','.jpg','.jpeg','.webp','.bmp','.gif','.tif','.tiff'}
    payload = {'text':text} if text is not None else {'paths':paths,'image':image}
    if image:
        payload['image_path'] = paths[0]
        if sys.platform == 'win32' and Path(paths[0]).suffix.lower() == '.webp':
            import hashlib
            from PIL import Image
            source = Path(paths[0])
            key = hashlib.sha256((str(source)+str(source.stat().st_mtime_ns)).encode()).hexdigest()[:24]
            folder = Path(__file__).resolve().parent / 'cache' / 'clipboard'
            folder.mkdir(parents=True, exist_ok=True)
            png = folder / (key+'.png')
            if not png.exists():
                with Image.open(source) as bitmap:
                    bitmap.convert('RGBA').save(png)
            payload['image_path'] = str(png)
    serialized = json.dumps(payload, ensure_ascii=False)
    with _LOCK:
        if sys.platform == 'darwin':
            command=['/usr/bin/osascript','-l','JavaScript','-e',_MAC_SCRIPT,serialized]
            kwargs={}
        elif sys.platform == 'win32':
            # 数据经环境变量传递，不拼进 PowerShell 代码。
            env=dict(os.environ, LAOHU_CLIPBOARD_PAYLOAD=base64.b64encode(serialized.encode()).decode())
            command=['powershell.exe','-NoProfile','-NonInteractive','-STA','-EncodedCommand',base64.b64encode(_WINDOWS_SCRIPT.encode('utf-16le')).decode()]
            kwargs={'env':env,'creationflags':subprocess.CREATE_NO_WINDOW}
        else:
            raise RuntimeError('当前系统暂不支持原生素材剪贴板；请使用 macOS 或 Windows')
        result=subprocess.run(command,capture_output=True,text=True,timeout=20,**kwargs)
        if result.returncode or result.stdout.strip() != 'ok':
            raise RuntimeError('系统剪贴板写入失败：'+(result.stderr.strip() or result.stdout.strip())[:240])
    return {'ok':True,'count':1 if text is not None else len(paths),'format':'text' if text is not None else 'image' if image else 'files'}
