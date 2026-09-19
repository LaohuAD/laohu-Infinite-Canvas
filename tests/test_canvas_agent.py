import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from canvas_agent import AgentMailbox, CommandRequest, CompleteRequest, create_agent_router
from model_capabilities import ai_money_profile_from_model_id, ModelCapabilityError
from laohu_protocols import validate_parameters, minimax_h3_body


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mail = AgentMailbox(self.tmp.name)
        self.payload = CommandRequest(request_id='request-1',action='run_node',args={'node_id':'a'})

    def test_duplicate_does_not_create_second_generation_and_survives_restart(self):
        first = self.mail.submit('canvas', self.payload)
        self.assertEqual(first, AgentMailbox(self.tmp.name).submit('canvas',self.payload))
        with self.assertRaises(HTTPException) as context:
            self.mail.submit('canvas', CommandRequest(request_id='request-1',action='delete_node'))
        self.assertEqual(context.exception.status_code,409)

    def test_two_pages_cannot_claim_the_same_paid_run(self):
        self.mail.submit('canvas',self.payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims=list(pool.map(lambda c:self.mail.claim('canvas',c),['tab1','tab2']))
        self.assertEqual(sum(bool(x) for x in claims),1)
        self.assertIsNone(AgentMailbox(self.tmp.name).claim('canvas','restarted'))

    def test_wrong_client_cannot_complete_and_token_is_not_public(self):
        public=self.mail.submit('canvas',self.payload)
        claim=self.mail.claim('canvas','tab')
        with self.assertRaises(HTTPException):
            self.mail.complete('canvas',public['id'],CompleteRequest(client_id='other',claim_token=claim['claim_token'],status='succeeded'))
        result=self.mail.complete('canvas',public['id'],CompleteRequest(client_id='tab',claim_token=claim['claim_token'],status='succeeded',result={'node_id':'result'}))
        self.assertEqual(result['status'],'succeeded')
        self.assertNotIn('claim_token',result)
        self.assertEqual(result,self.mail.complete('canvas',public['id'],CompleteRequest(client_id='tab',claim_token=claim['claim_token'],status='failed')))

    def test_rejects_code_and_traversal(self):
        for action in ['eval','shell','execute_js']:
            with self.assertRaises(HTTPException): self.mail.submit('canvas',CommandRequest(request_id='x',action=action))
        with self.assertRaises(HTTPException): self.mail.read('../outside')

    def test_node_context_reads_one_complete_note_without_other_segments_or_history(self):
        notes = '# 决定\n- 暂不露脸。\n' + '不截断的说明。' * 3000
        canvas = {'nodes': [{'id': 'p100', 'type': 'smart-material', 'title': 'E01_S01_P100_告别', 'creationDetails': notes, 'creationRevision': 7, 'images': [{'kind': 'text', 'text': '完整的当前段正文'}], 'resultVersions': [{'text': '历史冗余'}]}, {'id': 'p99', 'title': '上一段', 'images': [{'text': '不应自动返回的上一段正文'}]}], 'connections': [{'from': 'p99', 'to': 'p100', 'kind': 'story'}]}
        app = FastAPI(); app.include_router(create_agent_router(self.tmp.name, lambda _: canvas))
        with TestClient(app) as client:
            index = client.get('/api/agent/canvases/work/nodes').json()
            self.assertEqual([n['id'] for n in index['nodes']], ['p100', 'p99'])
            self.assertNotIn(notes, json.dumps(index, ensure_ascii=False))
            context = client.get('/api/agent/canvases/work/nodes/p100').json()
            self.assertEqual(context['node']['creationDetails'], notes)
            self.assertEqual(context['node']['creationRevision'], 7)
            self.assertEqual(context['node']['images'][0]['text'], '完整的当前段正文')
            self.assertNotIn('历史冗余', json.dumps(context, ensure_ascii=False))
            self.assertNotIn('不应自动返回的上一段正文', json.dumps(context, ensure_ascii=False))
            self.assertEqual(context['connections'], canvas['connections'])
            self.assertEqual(client.get('/api/agent/canvases/work/nodes/missing').status_code, 404)

    def test_cross_site_is_rejected_but_local_cli_connects(self):
        app=FastAPI(); app.include_router(create_agent_router(self.tmp.name,lambda _:{}))
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/agent/capabilities').status_code,200)
            self.assertEqual(client.get('/api/agent/capabilities',headers={'Origin':'https://evil.example'}).status_code,403)


class NewLaohuProtocolTests(unittest.TestCase):
    def test_image_25_exact_mapping_and_reference_limits(self):
        for variant,limit,count in [('flare',16,4),('sunburst',16,4),('lowprice',15,1)]:
            profile=ai_money_profile_from_model_id('laohu-image-g-v2.5-'+variant,'image_generation')
            self.assertEqual(profile['request_mapping']['resolution'],'resolution')
            self.assertEqual(profile['request_mapping']['aspect_ratio'],'size')
            self.assertEqual(profile['inputs']['reference']['max'],limit)
            self.assertEqual(profile['parameters']['count']['max'],count)
            self.assertEqual('quality' in profile['parameters'],variant!='lowprice')

    def test_image_format_constraints(self):
        for params in [{'output_compression':50},{'output_format':'jpeg','background':'transparent'}]:
            with self.assertRaises(ValueError): validate_parameters('laohu-image-g-v2.5-flare',params)
        validate_parameters('laohu-image-g-v2.5-flare',{'output_format':'webp','background':'transparent','output_compression':0})

    def test_minimax_is_video_and_preserves_roles_false_and_zero(self):
        with self.assertRaises(ModelCapabilityError): ai_money_profile_from_model_id('MiniMax-H3','text_generation')
        body=minimax_h3_body('说话',[{'url':'https://example.com/a.png','role':'first_frame'}],[],['https://example.com/a.mp3'],{'resolution':'480P','duration':30,'ratio':'adaptive','audio_role':'drive_audio','audio_control':{'mode':'remix_source','denoise_strength':0,'add_drive_as_reference':False}})
        self.assertEqual(body['content'][-1]['role'],'drive_audio')
        self.assertEqual(body['content'][1]['role'],'first_frame')
        self.assertFalse(body['audio_control']['add_drive_as_reference'])
        self.assertEqual(body['audio_control']['denoise_strength'],0)
        self.assertNotIn('audio_role',body)
        with self.assertRaises(ValueError): minimax_h3_body('x',[],[],[],{'duration':30,'resolution':'480P','ratio':'16:9'})

    def test_new_text_models_have_documented_vision(self):
        for model in ['laohu/g6-astra','laohu/g5.6-sol','laohu/g5.6-terra','laohu/g5.6-luna','laohu/gm-3.8-flash']:
            self.assertEqual(ai_money_profile_from_model_id(model,'text_generation')['inputs']['reference']['media_type'],'image')
        self.assertNotIn('reference',ai_money_profile_from_model_id('glm-5.3','text_generation')['inputs'])

    def test_suno_v6_and_new_audio_operations(self):
        for action in ['generation','upload-cover','upload-extend']:
            p=ai_money_profile_from_model_id('suno-'+action,'music_generation')
            self.assertEqual(p['parameters']['version']['options'],['v6','v6-wild','v6-mini'])
            self.assertNotIn('upstream_task_id',p['parameters'])
        p=ai_money_profile_from_model_id('suno-create-model','music_generation')
        self.assertEqual((p['inputs']['reference_audio']['min'],p['inputs']['reference_audio']['max']),(6,24))
        self.assertEqual(p['output']['media_type'],'text')

if __name__=='__main__': unittest.main()

class AgentAddressAndDefaultsTests(unittest.TestCase):
    def test_launcher_lan_address_is_local_but_other_lan_clients_are_not(self):
        from unittest.mock import patch
        from canvas_agent import is_local_client
        with patch('canvas_agent.local_addresses', return_value={'192.168.1.253'}):
            for address in ['127.0.0.1','::1','192.168.1.253','::ffff:192.168.1.253']:
                self.assertTrue(is_local_client(address))
            for address in ['192.168.1.20','8.8.8.8','malicious.example']:
                self.assertFalse(is_local_client(address))

    def test_defaults_are_scoped_to_the_saved_canvas_and_preserve_false_zero(self):
        defaults={'image':{'provider_id':'ai-money','model':'test','parameters':{'count':1,'watermark':False,'seed':0}}}
        app=FastAPI(); app.include_router(create_agent_router('.',lambda canvas_id:{'settings':{'agentDefaults':defaults if canvas_id=='one' else {}}}))
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/agent/canvases/one/defaults').json()['defaults'],defaults)
            self.assertEqual(client.get('/api/agent/canvases/two/defaults').json()['defaults'],{})

class NewAdapterTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_minimax_uncertain_acceptance_polls_original_task_without_resubmit(self):
        import main, httpx
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        client=AsyncMock()
        client.post.return_value=httpx.Response(503,headers={'X-Task-Id':'accepted-1'},request=httpx.Request('POST','https://api.lao-hu.com/v2/video_generation'))
        client.get.side_effect=[httpx.Response(429),httpx.Response(200,json={'task':{'status':'succeeded','content':{'url':'https://example.com/result.mp4'}}},request=httpx.Request('GET','https://api.lao-hu.com/'))]
        manager=AsyncMock();manager.__aenter__.return_value=client
        with patch.object(main.httpx,'AsyncClient',return_value=manager),patch.object(main,'api_headers',return_value={}),patch.object(main.asyncio,'sleep',new=AsyncMock()),patch.object(main,'save_remote_video_to_output',new=AsyncMock(return_value='/api/results/result')):
            result=await main.generate_laohu_minimax_h3(SimpleNamespace(prompt='山谷',images=[],videos=[],audios=[]),{'id':'ai-money'},{'resolution':'480P','duration':5,'ratio':'16:9'})
        self.assertEqual(client.post.await_count,1)
        self.assertEqual(client.get.await_count,2)
        self.assertTrue(all('/v2/query/video_generation/accepted-1' in call.args[0] for call in client.get.await_args_list))
        self.assertEqual(result['task_id'],'accepted-1')

    async def test_suno_training_uploads_all_references_and_keeps_model_id_result(self):
        import main,httpx
        from unittest.mock import AsyncMock,patch
        client=AsyncMock();client.post.return_value=httpx.Response(200,json={'data':[{'task_id':'train-1'}]},request=httpx.Request('POST','https://api.lao-hu.com/'))
        manager=AsyncMock();manager.__aenter__.return_value=client
        refs=[f'https://example.com/{i}.mp3' for i in range(6)]
        completed={'data':{'status':'completed','result':{'model_id':'custom-1','name':'声音'}}}
        with patch.object(main.httpx,'AsyncClient',return_value=manager),patch.object(main,'provider_env_key_value',return_value='test'),patch.object(main,'api_headers',return_value={}),patch.object(main,'ai_money_upload_reference',new=AsyncMock(side_effect=lambda client,provider,url,kind:url)),patch.object(main,'wait_for_ai_money_music_task',new=AsyncMock(return_value=completed)),patch.object(main,'save_comfy_text_output',return_value='/api/results/model'):
            result=await main.generate_ai_money_audio({'id':'ai-money'},'suno-create-model','',reference_audio_urls=refs,capability_parameters={'name':'声音'})
        body=client.post.await_args.kwargs['json']
        self.assertEqual(body['audio_urls'],refs)
        self.assertNotIn('audio_url',body)
        self.assertEqual(result['texts'][0]['kind'],'text')
        self.assertEqual(result['raw']['data']['result']['model_id'],'custom-1')

class RetiredSkillTests(unittest.TestCase):
    def test_migration_preserves_regular_prompts_history_and_a_deduplicated_backup(self):
        import main
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.object(main,'BASE_DIR',tmp):
            source={'textSystemSkillId':'old','textSystemSkillSnapshot':{'text':'skill body'},'textSystemPrompt':'skill body','textSystemEnabled':True}
            canvas={'id':'test','nodes':[{'id':'text-1','runSettings':source},{'id':'result','runSnapshot':{'skill':{'text':'skill body'}}}]}
            self.assertTrue(main.retire_canvas_skill_settings(canvas))
            self.assertFalse(source['textSystemEnabled'])
            self.assertNotIn('textSystemSkillSnapshot',source)
            self.assertEqual(canvas['nodes'][1]['runSnapshot']['skill']['text'],'skill body')
            self.assertFalse(main.retire_canvas_skill_settings(canvas))
            archive=json.loads((Path(tmp)/'backups/retired-skills.json').read_text())
            self.assertEqual(len(archive),1)
            self.assertEqual(next(iter(archive.values()))['data'][0][0],'text-1')
        library=main.normalize_prompt_libraries({'active_library_id':'skills','libraries':[{'id':'system','items':[{'id':'prompt','positive':'ordinary'}]},{'id':'skills','items':[{'id':'skill','positive':'skill body'}]}]})
        self.assertEqual([x['id'] for x in library['libraries']],['system'])
        self.assertEqual(library['libraries'][0]['items'][0]['positive'],'ordinary')
        self.assertEqual(library['active_library_id'],'system')

class AgentDefaultMergeTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_nodes_inherit_defaults_and_only_explicit_fields_override(self):
        import copy
        from threading import RLock
        from canvas_core.headless_canvas import HeadlessCanvas
        canvas = {'id':'test','nodes':[],'connections':[], 'settings':{'agentDefaults':{'image':{
            'provider_id':'test','model':'one','parameters':{'resolution':'2k','aspect_ratio':'16:9','flag':True,'seed':8}}}}}
        def save(value):
            canvas.clear()
            canvas.update(copy.deepcopy(value))
        def validate(kind, provider, model, parameters):
            return {'runnable':provider=='test','family_id':model,'parameters':{key:{} for key in ['resolution','aspect_ratio','flag','seed']}}
        executor = HeadlessCanvas(lambda _:copy.deepcopy(canvas),save,RLock(),lambda *_:None,lambda *_:None,validate,lambda *_:None)
        async def create(number, **changes):
            return (await executor.execute('test','create_node',{'kind':'image','title':'测试图片',**changes},str(number)))['node']
        first = await create(1,text='scene')
        self.assertEqual(first['runSettings']['capabilityParameters']['one'],{'resolution':'2k','aspect_ratio':'16:9','flag':True,'seed':8})
        second = await create(2,parameters={'aspect_ratio':'9:16','flag':False,'seed':0})
        self.assertEqual(second['runSettings']['capabilityParameters']['one'],{'resolution':'2k','aspect_ratio':'9:16','flag':False,'seed':0})
        changed = await create(3,model='two',parameters={'resolution':'1k'})
        self.assertEqual(changed['runSettings']['capabilityParameters']['two'],{'resolution':'1k'})
        reset = await create(4,parameters={'resolution':'__canvas_unset__'})
        self.assertEqual(reset['runSettings']['capabilityParameters']['one']['resolution'],'__canvas_unset__')
        del canvas['settings']['agentDefaults']['image']
        with self.assertRaises(ValueError):
            await create(5)
