import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException, UploadFile
import main
from project_storage import ProjectStorage


class CanvasPackageTests(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip_names_media_history_settings_and_dedup(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            source=ProjectStorage(source_dir);source.ensure_layout()
            material=source.store_material_bytes(b'input picture','角色.png','temporary')
            path=Path(source_dir)/'音乐.wav';path.write_bytes(b'music output')
            result=source.store_result_file(path,'音乐.wav');source.update_result_metadata(result['id'],media_category='music')
            old_input=source.material_url(material['id']);old_result=source.result_url(result['id'])
            nodes=[{'id':'a','type':'smart-material','images':[{'url':old_input,'name':'角色.png'}]}, {'id':'b','type':'smart-material','sourceKind':'result','images':[{'url':old_result,'name':'音乐.wav'}],'resultVersions':[{'images':[{'url':old_result}],'runInputRefs':[{'url':old_input,'nodeId':'a'}]}],'promptDraftHtml':f'<span data-url="{old_input}">参考</span>'}]
            payload=main.CanvasWorkflowExportRequest(nodes=nodes,connections=[{'from':'a','to':'b'}],settings={'api_key':'not-exported','agentDefaults':{'image':{'model':'test'}}})
            with patch.object(main,'PROJECT_STORAGE',source):
                data,meta=main.build_canvas_workflow_archive(payload)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertIn('resources/角色.png',archive.namelist())
                self.assertIn('resources/音乐.wav',archive.namelist())
                self.assertNotIn('not-exported',archive.read('workflow.json').decode())
                self.assertEqual(len(meta['resources']),2)
            target=ProjectStorage(target_dir);target.ensure_layout()
            with patch.object(main,'PROJECT_STORAGE',target):
                imported=await main.import_canvas_workflow(UploadFile(filename='完整画布.zip',file=io.BytesIO(data)))
                again=await main.import_canvas_workflow(UploadFile(filename='完整画布.zip',file=io.BytesIO(data)))
            self.assertEqual(imported['nodes'],again['nodes'])
            self.assertEqual(len(target.list_materials()),1)
            self.assertEqual(len(target.list_results()),1)
            self.assertEqual(target.list_results()[0]['media_category'],'music')
            self.assertEqual(imported['connections'],[{'from':'a','to':'b'}])
            self.assertEqual(imported['settings']['agentDefaults']['image']['model'],'test')
            self.assertEqual(imported['nodes'][1]['resultVersions'][0]['runInputRefs'][0]['url'],imported['nodes'][0]['images'][0]['url'])

    async def test_legacy_canvas_zip_can_import(self):
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,'w') as z:
            z.writestr('canvas.json',json.dumps({'nodes':[{'id':'n','images':[{'url':'/assets/old.png'}]}],'connections':[]}))
            z.writestr('resources-manifest.json',json.dumps({'resources':[{'url':'/assets/old.png','file':'resources/原图.png'}]}))
            z.writestr('resources/原图.png',b'image')
        with tempfile.TemporaryDirectory() as directory:
            storage=ProjectStorage(directory);storage.ensure_layout()
            with patch.object(main,'PROJECT_STORAGE',storage):
                imported=await main.import_canvas_workflow(UploadFile(filename='旧包.zip',file=io.BytesIO(blob.getvalue())))
            self.assertTrue(imported['nodes'][0]['images'][0]['url'].startswith('/api/materials/'))

    async def test_missing_or_unsafe_resources_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            storage=ProjectStorage(directory);storage.ensure_layout()
            with patch.object(main,'PROJECT_STORAGE',storage):
                with self.assertRaises(HTTPException):
                    main.build_canvas_workflow_archive(main.CanvasWorkflowExportRequest(nodes=[{'images':[{'url':'/api/results/missing'}]}]))
                for name,body in [('resources/missing.png',None),('../escape.png',b'x')]:
                    blob=io.BytesIO()
                    with zipfile.ZipFile(blob,'w') as z:
                        z.writestr('workflow.json',json.dumps({'nodes':[],'resources':[{'url':'/assets/x.png','archive':name}]}))
                        if body:z.writestr(name,body)
                    with self.assertRaises(HTTPException):
                        await main.import_canvas_workflow(UploadFile(filename='bad.zip',file=io.BytesIO(blob.getvalue())))
                self.assertEqual(storage.list_materials(),[])
