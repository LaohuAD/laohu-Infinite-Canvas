"""融合创作：真实状态转换测试，不调用付费平台。"""
import json
import subprocess
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class CanvasCreationTests(unittest.TestCase):
    def run_js(self, body):
        source = "const assert=require('node:assert/strict'); const fs=require('fs'); assert.ok(fs.existsSync('static/js/canvas-creation.js'),'creation module missing'); const c=require('./static/js/canvas-creation.js'); let seq=0; const id=()=> 'c'+(++seq); const n=()=>({id:id(),type:'smart-image-generator',promptDraftText:'角色',runSettings:{model:'m'},images:[]});" + body
        result=subprocess.run(['node','-e',source],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_first_result_shared_then_rerun_forks_without_copying_file(self):
        self.run_js("""const a=n(); c.ensure(a,id); const b=structuredClone(a); b.id='b'; const ns=[a,b]; const t=c.begin(ns,a,id); c.publish(ns,t,[{url:'/api/results/r1',resultId:'r1'}]); assert.equal(b.images[0].resultId,'r1'); const t2=c.begin(ns,b,id); c.publish(ns,t2,[{url:'/api/results/r2',resultId:'r2'}]); assert.equal(a.images[0].resultId,'r1'); assert.equal(b.images[0].resultId,'r2'); assert.equal(b.resultVersions.length,2); assert.notEqual(a.creationId,b.creationId);""")
    def test_edit_forks_and_late_run_does_not_overwrite_draft(self):
        self.run_js("""const a=n(); c.ensure(a,id); const b=structuredClone(a); b.id='b'; const ns=[a,b]; const t=c.begin(ns,a,id); a.promptDraftText='受伤'; c.reconcile(ns,id); c.publish(ns,t,[{url:'/a'}]); assert.equal(a.images.length,0); assert.equal(a.promptDraftText,'受伤'); assert.equal(b.images[0].url,'/a');""")
    def test_parallel_results_accumulate_and_cancel_discards_late_result(self):
        self.run_js("""const a=n(); const ns=[a]; const t=c.begin(ns,a,id), u=c.begin(ns,a,id); c.publish(ns,u,[{url:'/u'}]); c.publish(ns,t,[{url:'/t'}]); c.publish(ns,t,[{url:'/t'}]); assert.equal(a.resultVersions.length,2); const v=c.begin(ns,a,id); v.runStatus='cancelled'; assert.equal(c.publish(ns,v,[{url:'/late'}]),false); assert.equal(a.resultVersions.length,2);""")
    def test_migration_preserves_old_results_pinned_connections_and_is_idempotent(self):
        self.run_js("""const a=n(); a.id='run'; const r1={id:'r1',type:'smart-material',sourceExecutionNodeId:'run',sourceKind:'result',images:[{url:'/one'}]}; const r2={...structuredClone(r1),id:'r2',images:[{url:'/two'}]}; const v=n(); v.id='video'; const old=[a,r1,r2,v]; const links=[{from:'run',to:'r1',kind:'result'},{from:'run',to:'r2',kind:'result'},{from:'r1',to:'video',kind:'input'}]; const m=c.migrate(old,links,id); assert.equal(m.nodes.length,2); assert.equal(m.nodes[0].resultVersions.length,2); assert.equal(m.connections[0].from,'run'); assert.deepEqual(c.references(m.nodes[0],m.connections[0]).map(x=>x.url),['/one']); const twice=c.migrate(m.nodes,m.connections,id); assert.deepEqual(twice.nodes,m.nodes); assert.deepEqual(twice.connections,m.connections); assert.equal(old.length,4);""")
    def test_same_file_does_not_merge_different_recipes(self):
        self.run_js("""const a=n(), b=n(); a.images=b.images=[{url:'/same'}]; b.promptDraftText='另一个配方'; c.reconcile([a,b],id); assert.notEqual(a.creationId,b.creationId);""")
    def test_free_markdown_notes_and_stale_agent_revision(self):
        self.run_js("""const a=n(); c.ensure(a,id); const rev=a.creationRevision, identity=a.creationId; const notes='# 此段结论\\n- 她故意隐瞒身份。\\n\\n自由记录，不要求任何字段。'+ '长说明'.repeat(10000); c.updateDetails(a,notes,rev); assert.equal(a.creationDetails,notes); assert.equal(a.creationId,identity); assert.throws(()=>c.updateDetails(a,'过时',rev)); assert.throws(()=>c.updateDetails(a,{duration:31},a.creationRevision)); c.updateDetails(a,'',a.creationRevision); assert.equal(a.creationDetails,'');""")
    def test_legacy_notes_convert_once_without_losing_unknown_content(self):
        self.run_js("""const a=n(); a.creationDetails={segment_id:'E01_S01_P01',direction:'低声说话',duration:31,assets:[{name:'林澈',node_id:'hero',state:'正常'}],custom:{decision:'暂不露脸',approved:false},notes:'保留结论'}; c.ensure(a,id); assert.equal(typeof a.creationDetails,'string'); for(const word of ['E01_S01_P01','低声说话','31','林澈','hero','正常','暂不露脸','false','保留结论']) assert.ok(a.creationDetails.includes(word),word); const before=a.creationDetails; c.ensure(a,id); assert.equal(a.creationDetails,before); const saved=JSON.parse(JSON.stringify(a)); assert.equal(saved.creationDetails,before);""")
    def test_fused_outputs_connect_to_next_creation_and_script_materials(self):
        self.run_js("""const contract=require('./static/js/smart-node-contract.js'); const a=n(), b=n(); assert.equal(contract.canConnectNodes(a,b),true); assert.equal(contract.connectionKindForNodes(a,b),'input'); assert.equal(contract.canConnectNodes({id:'s',type:'smart-material',images:[{kind:'text',text:'剧本'}]},{id:'p',type:'smart-material',images:[{kind:'text',text:'分段'}]}),true);""")
    def test_owner_rerun_updates_followers_until_follower_runs(self):
        self.run_js("""const a=n(); c.ensure(a,id); const b=structuredClone(a); b.id='b'; const ns=[a,b]; c.publish(ns,c.begin(ns,a,id),[{url:'/first'}]); c.publish(ns,c.begin(ns,a,id),[{url:'/better'}]); assert.equal(b.images[0].url,'/better'); c.publish(ns,c.begin(ns,b,id),[{url:'/branch'}]); c.publish(ns,c.begin(ns,a,id),[{url:'/owner-third'}]); assert.equal(b.images[0].url,'/branch'); assert.equal(a.images[0].url,'/owner-third');""")
    def test_input_copy_keeps_identity_and_rewiring_forks_only_copy(self):
        self.run_js("""const src=n(),a=n(); const ns=[src,a]; const links=[{from:src.id,to:a.id,kind:'input',targetFieldKey:'1::image'}]; c.reconcile(ns,id,links); const b=structuredClone(a); b.id='b'; ns.push(b); links.push({...links[0],to:b.id}); c.reconcile(ns,id,links); assert.equal(a.creationId,b.creationId); links[1].targetFieldKey='2::image'; c.reconcile(ns,id,links); assert.notEqual(a.creationId,b.creationId);""")
    def test_stale_saved_state_cannot_undo_fork_or_lose_completed_task(self):
        self.run_js("""const a=n(); const ns=[a]; const t=c.begin(ns,a,id); const old=structuredClone(a); c.publish(ns,t,[{url:'/one'}]); t.runStatus='succeeded'; const merged=c.merge(a,old); assert.equal(merged.images[0].url,'/one'); assert.equal(merged.creationTasks[0].runStatus,'succeeded'); assert.equal(merged.resultVersions.length,1); a.promptDraftText='新配方'; c.reconcile(ns,id); assert.equal(c.merge(a,old).creationId,a.creationId);""")
    def test_task_preflight_includes_creator_upstream_graph(self):
        self.run_js("""const contract=require('./static/js/smart-node-contract.js'); const a=n(),s=n(); const t=c.begin([a,s],a,id); const r=contract.createCanvasPreflightRequest({node:t,graphNode:a,nodeId:t.id,graphNodes:[s,a],graphConnections:[{from:s.id,to:a.id,kind:'input'}]}); assert.equal(r.node_id,t.id); assert.equal(r.nodes.length,2); assert.equal(r.connections.length,1);""")
    def test_lan_http_without_random_uuid_can_create_distinct_identities(self):
        self.run_js("""const vm=require('node:vm');const ctx={};vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/js/canvas-creation.js','utf8'),ctx);const a=n(),b=n();ctx.CanvasCreation.ensure(a);ctx.CanvasCreation.ensure(b);assert.ok(a.creationId);assert.notEqual(a.creationId,b.creationId);""")

class CreationRecordTests(unittest.TestCase):
    def test_recipe_export_never_contains_credentials_or_mutates_source(self):
        import importlib.util
        spec=importlib.util.find_spec('canvas_core.creation_records')
        self.assertIsNotNone(spec,'creation records module missing')
        from canvas_core.creation_records import creation_record
        source={'id':'n','type':'smart-image-generator','title':'林澈_妆造_正常','creationId':'c','runSettings':{'model':'m','apiKey':'secret','nested':{'authorization':'secret','count':0}},'images':[{'url':'/api/results/r'}]}
        record=creation_record(source)
        self.assertNotIn('secret',json.dumps(record))
        self.assertEqual(record['runSettings']['nested']['count'],0)
        self.assertEqual(source['runSettings']['apiKey'],'secret')
    def test_record_preserves_official_field_mapping_and_version_identity(self):
        from canvas_core.creation_records import records_for_nodes
        node={'id':'n','type':'smart-ai-app','creationId':'new','creationOwnerNodeId':'n','runSettings':{'targetFieldKey':'2::image'},'resultVersions':[{'id':'v1','creationId':'old','images':[{'url':'/api/results/res_one'}]}]}
        record=records_for_nodes([node])['res_one']['v1']
        self.assertEqual(record['creationId'],'old')
        self.assertEqual(record['runSettings']['targetFieldKey'],'2::image')


class GridAlignmentTests(unittest.TestCase):
    def run_js(self, body):
        source="const assert=require('node:assert/strict');const {alignToGrid:align}=require('./static/js/canvas-node-view.js');"+body
        result=subprocess.run(['node','-e',source],cwd=ROOT,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_nearby_cells_preserve_regions_and_original_sizes(self):
        self.run_js("""const input=[{id:'a',x:61,y:51,width:316,height:194},{id:'b',x:4100,y:-2200,width:100,height:90}];const copy=structuredClone(input),out=align(input);assert.deepEqual(input,copy);for(let i=0;i<2;i++){assert.ok(Math.abs(out[i].x-input[i].x)<=198);assert.ok(Math.abs(out[i].y-input[i].y)<=133);}assert.ok(Math.abs(out[0].x-out[1].x)>3000);""")

    def test_small_one_cell_large_four_cells_and_majority_threshold(self):
        self.run_js("""const one=align([{id:'a',x:110,y:80,width:100,height:80}])[0];assert.equal(one.x+50,198);assert.equal(one.y+40,133);const big=align([{id:'b',x:65,y:76,width:632,height:388}])[0];assert.equal(big.x+316,396);assert.equal(big.y+194,266);const slight=align([{id:'c',x:0,y:0,width:330,height:200}])[0];assert.equal(slight.x+165,198);assert.equal(slight.y+100,133);""")

    def test_collision_avoidance_is_local_stable_and_order_independent(self):
        self.run_js("""const input=Array.from({length:20},(_,i)=>({id:String(i),x:40+i,y:36+i,width:316,height:194}));const a=align(input),b=align([...input].reverse());assert.deepEqual(a,b);const placed=a.map(p=>({...input.find(n=>n.id===p.id),...p}));for(const x of placed)for(const y of placed)if(x.id!==y.id)assert.ok(x.x+x.width<=y.x||y.x+y.width<=x.x||x.y+x.height<=y.y||y.y+y.height<=x.y);const again=align(placed);for(const p of again)assert.deepEqual(p,a.find(n=>n.id===p.id));""")

    def test_unselected_obstacles_do_not_move(self):
        self.run_js("""const obstacle={id:'fixed',x:40,y:36,width:316,height:194};const out=align([{id:'a',x:41,y:37,width:316,height:194}],[obstacle]);assert.deepEqual(obstacle,{id:'fixed',x:40,y:36,width:316,height:194});assert.ok(out[0].x!==40||out[0].y!==36);assert.ok(Math.hypot(out[0].x-41,out[0].y-37)<400);""")
