/* Mac/Windows 浏览器回归。对测试服务运行；所有生图请求由本脚本拦截，禁止付费外网调用。需要 Playwright 与 Chrome。 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');const fs=require('node:fs');
(async()=>{
 const base=process.env.CANVAS_TEST_URL || 'http://127.0.0.1:3001';
 const output=require('node:path').resolve('cache/maintenance'); fs.mkdirSync(output,{recursive:true});
 process.env.TMPDIR=output; process.env.TMP=output; process.env.TEMP=output;
 const generated=new Set();
 const api=async(path,body,method)=>{const r=await fetch(base+path,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(JSON.stringify(d));return d;};
 const made=await api('/api/canvases',{title:'融合创作自动验收_临时',kind:'smart'});const cid=made.id||made.canvas?.id;
 const browser=await chromium.launch({...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{channel:'chrome'}),headless:true});
 const page=await browser.newPage({viewport:{width:1600,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let num=0;
 await page.route('**/api/canvas-image-tasks',async route=>{if(route.request().method()==='POST')return route.fulfill({json:{task_id:`fake_${++num}`}});return route.abort();});
 await page.route('**/api/canvas-image-tasks/*',route=>route.fulfill({json:{status:'succeeded',result:{images:[`/static/images/logo.png?fixture=${route.request().url().split('/').pop()}`]}}}));
 await page.route('**/api/canvas-runs/*/results',route=>route.fulfill({json:{results:[]}}));
 await page.route('**/*',route=>{if(!route.request().url().startsWith(base)&&!route.request().url().startsWith('data:'))return route.abort();return route.fallback();});
 await page.goto(`${base}/static/smart-canvas.html?id=${cid}`);await page.waitForFunction(()=>typeof canvas!=='undefined' && canvas && typeof CanvasCreation!=='undefined' && apiProviders.length>0).catch(async e=>{console.log('load errors',errors);throw e});
 const cmd=async(action,args)=>{await page.keyboard.press('Escape');await page.evaluate(()=>document.activeElement?.blur());const q=await api(`/api/agent/canvases/${cid}/commands`,{request_id:`fixture_${Date.now()}_${Math.random()}`,action,args});for(let i=0;i<100;i++){await new Promise(r=>setTimeout(r,200));const d=await api(`/api/agent/canvases/${cid}/commands/${q.id}`);if(d.status==='failed')throw Error(d.error);if(d.status==='succeeded')return d.result;}throw Error(`timeout ${action}`);};
 try{
 const a=(await cmd('create_node',{kind:'image',title:'林澈_妆造_正常',text:'验收占位',provider_id:'modelscope',model:'Tongyi-MAI/Z-Image-Turbo',x:100,y:120})).node_id;
 const b=(await cmd('duplicate_node',{node_id:a,dx:500,dy:0})).node_id;
 let state=await cmd('snapshot',{});let ns=state.canvas.nodes;assert.equal(ns.find(n=>n.id===a).creationId,ns.find(n=>n.id===b).creationId,'duplicate identity');
 for(const owner of [a,a,b,a]){
  const result=await cmd('run_node',{node_id:owner});
  assert.equal(result.tasks[0].runStatus,'succeeded'); const temp=(await cmd('snapshot',{})).canvas.nodes;const aa=temp.find(n=>n.id===a),bb=temp.find(n=>n.id===b);if(num<3) assert.equal(aa.images[0].url,bb.images[0].url);
 }
 state=await cmd('snapshot',{});ns=state.canvas.nodes;const A=ns.find(n=>n.id===a),B=ns.find(n=>n.id===b);

 assert.equal(ns.length,2,'no standalone result nodes');assert.equal(A.resultVersions.length,3);assert.equal(B.resultVersions.length,3);assert.notEqual(A.creationId,B.creationId);assert.notEqual(A.images[0].url,B.images[0].url);
 await page.keyboard.press('Escape');await page.screenshot({path:'cache/maintenance/creation-browser.png'});
 await page.reload();await page.waitForFunction(()=>typeof canvas!=='undefined'&&canvas&&nodes.length===2);
 state=await cmd('snapshot',{});assert.equal(state.canvas.nodes.find(n=>n.id===a).resultVersions.length,3);
 const t=(await cmd('create_node',{kind:'material',title:'E01_S01_P01_交剑',text:'# 分段正文\n林澈交出旧剑。',x:100,y:500,creation_details:'# 已确认的结论\n- 林澈主动交剑。\n- 复用 林澈_妆造_正常。'})).node_id;
 await page.locator(`.image-node[data-id="${t}"] .image-wrap`).dblclick();await page.locator('[data-text-editor-input]').fill('# 分段正文\n林澈缓慢交出旧剑。');await page.locator('[data-creation-notes]').fill('# 这一段的结论\n- 先看守门人，再交剑。\n- 不要演成被迫投降。\n\n<img src=x onerror=alert(1)>'); await page.locator('[data-creation-notes-toggle]').click(); assert.equal(await page.locator('[data-creation-notes-preview] h1').textContent(),'这一段的结论'); assert.equal(await page.locator('[data-creation-notes-preview] img').count(),0);await page.screenshot({path:'cache/maintenance/creation-editor.png'});await page.evaluate(()=>StudioTheme.apply('dark'));await page.waitForTimeout(300);await page.screenshot({path:'cache/maintenance/creation-editor-dark.png'});await page.locator('[data-text-editor-save]').click();await page.waitForFunction(()=>!document.querySelector('#smartTextEditorModal').classList.contains('open'));
 state=await cmd('snapshot',{});const text=state.canvas.nodes.find(n=>n.id===t); text.images.forEach(item=>{if(item.resultId)generated.add(item.resultId)});assert.equal(text.resultVersions.length,2);assert.ok(text.creationDetails.includes('先看守门人，再交剑。')); const context=await api(`/api/agent/canvases/${cid}/nodes/${t}`); assert.equal(context.node.creationDetails,text.creationDetails); assert.ok(!context.node.resultVersions); const records=await api(`/api/results/${text.images[0].resultId}/creation`); assert.ok(records.recipes.some(record=>record.creationDetails===text.creationDetails)); await page.reload();await page.waitForFunction(()=>typeof canvas!=='undefined'&&canvas&&nodes.length===3); await page.locator(`.image-node[data-id="${t}"] .image-wrap`).dblclick();assert.equal(await page.locator('[data-creation-notes]').inputValue(),text.creationDetails); await page.keyboard.press('Escape'); const cleared=await cmd('update_node',{node_id:t,expected_revision:text.creationRevision,creation_details:''});assert.equal(cleared.node.creationDetails,'');

 const full=(await cmd('create_node',{kind:'material',title:'E01_完整剧本',text:'# 分段正文\n林澈缓慢交出旧剑。',x:-600,y:500,production:{role:'script'},creation_details:'## 故事背景\n城门分别。不是逐段讲戏。'})).node_id;
 const voice=(await cmd('create_node',{kind:'audio',title:'林澈_音色_正常',defer_configuration:true,x:1600,y:500,creation_details:'中音区，清楚咬字。尚未生成音频。'})).node_id;
 const video=(await cmd('create_node',{kind:'video',title:'E01_S01_P01_视频',defer_configuration:true,x:2600,y:500})).node_id;
 await cmd('update_node',{node_id:t,production:{role:'segment',order:1,sourceNodeId:full,imageNodeIds:[a],audioNodeIds:[voice],videoNodeIds:[video]}});
 const copy=(await cmd('duplicate_node',{node_id:a,dx:700,dy:600})).node_id;
 const t2=(await cmd('create_node',{kind:'material',title:'E01_S01_P02_交剑',text:'林澈缓慢交出旧剑。',x:100,y:1200,production:{role:'segment',order:2,sourceNodeId:full,imageNodeIds:[copy],audioNodeIds:[voice]}})).node_id;
 let progress=await cmd('production_status',{});assert.equal(progress.rows.length,2);assert.equal(progress.rows[0].audio[0].status,'not_generated');assert.equal(progress.rows[0].videos[0].status,'not_generated');assert.equal(progress.rows[0].sourceStatus,'current');
 await cmd('run_node',{node_id:a}); progress=await cmd('production_status',{});assert.equal(progress.rows[0].images[0].media.url,progress.rows[1].images[0].media.url);
 const voiceSettings=JSON.stringify((await cmd('snapshot',{})).canvas.nodes.find(n=>n.id===voice).runSettings);
 await page.locator(`.canvas-production-panel [data-node-id="${voice}"]`).first().click();await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>shell.classList.contains('smart-focus-transition')),true);await page.waitForTimeout(350);
 const layout=await page.evaluate(id=>{const r=document.querySelector(`.image-node[data-id="${id}"]`).getBoundingClientRect(),panel=document.querySelector('.canvas-production-panel').getBoundingClientRect();return {bottom:r.bottom,panelTop:panel.top};},voice);assert.ok(layout.bottom<=layout.panelTop+4,JSON.stringify(layout));assert.equal(JSON.stringify((await cmd('snapshot',{})).canvas.nodes.find(n=>n.id===voice).runSettings),voiceSettings,'Navigation must not configure the model');
 await page.screenshot({path:'cache/maintenance/production-browser.png'});
 await page.reload();await page.waitForFunction(()=>typeof canvas!=='undefined'&&canvas&&nodes.some(n=>n.production?.role==='segment'));progress=await cmd('production_status',{});assert.equal(progress.rows.length,2);assert.equal(progress.rows[0].audio[0].id,voice);
 // 浏览器内录制小型彩色视频夹具，验证真实解码首帧；不读取用户媒体，不调用模型。
 const fixture=await page.evaluate(async()=>{const c=document.createElement('canvas');c.width=96;c.height=64;const ctx=c.getContext('2d');ctx.fillStyle='#35b98a';ctx.fillRect(0,0,96,64);const stream=c.captureStream(10),rec=new MediaRecorder(stream,{mimeType:'video/webm'}),parts=[];return new Promise(resolve=>{rec.ondataavailable=e=>parts.push(e.data);rec.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());const bytes=new Uint8Array(await new Blob(parts).arrayBuffer());resolve(Array.from(bytes));};rec.start();setTimeout(()=>{ctx.fillStyle='#5089d0';ctx.fillRect(0,0,48,64);},100);setTimeout(()=>rec.stop(),400);});});
 await page.route('**/__test__/preview.webm',route=>route.fulfill({contentType:'video/webm',body:Buffer.from(fixture)}));
 const footage=(await cmd('create_node',{kind:'material',title:'首帧验收',media:[{kind:'video',url:'/__test__/preview.webm',name:'首帧验收.webm'}],x:2700,y:1100})).node_id;
 await cmd('update_node',{node_id:t,production:{videoNodeIds:[video,footage]}});
 await page.waitForFunction(id=>{const img=document.querySelector(`.canvas-production-panel [data-node-id="${id}"] img`);return img&&img.naturalWidth>0&&img.src.startsWith('data:image/');},footage);
 assert.equal((await cmd('production_status',{})).rows[0].videos[1].status,'ready');
 assert.ok(await page.locator(`.canvas-production-panel [data-node-id="${voice}"] svg`).count());
 await page.evaluate(()=>StudioI18n.set('en'));await page.waitForFunction(()=>document.querySelector('.canvas-production-panel [data-heading]').textContent==='Production');
 await page.setViewportSize({width:800,height:750});
 const narrow=await page.locator('.canvas-production-panel').boundingBox();assert.ok(narrow.x>=0&&narrow.x+narrow.width<=800);assert.equal(await page.locator('.canvas-production-panel thead th').count(),5);
 await page.screenshot({path:'cache/maintenance/production-browser-narrow-en.png'});
 await page.setViewportSize({width:1600,height:1000});await page.evaluate(()=>{StudioI18n.set('zh');StudioTheme.apply('dark')});
 await page.waitForTimeout(400);
 const visual=await page.evaluate(()=>({label:getComputedStyle(document.querySelector('.production-script')).color,panel:getComputedStyle(document.querySelector('.canvas-production-panel')).color,progressRight:document.querySelector('#canvasProductionToggle').getBoundingClientRect().right,agentLeft:document.querySelector('#canvasAgentToggle').getBoundingClientRect().left}));assert.equal(visual.label,visual.panel);assert.ok(visual.agentLeft-visual.progressRight>=6,JSON.stringify(visual));
 await page.screenshot({path:'cache/maintenance/production-browser.png'});
 assert.deepEqual(errors,[]);console.log('通过：共用资产同步、副本分支、刷新保留、自由 Markdown、定向上下文、原文分段登记、五列创作进度、音色占位、真实视频首帧、平滑定位避让、窄屏及中英文。');
 }finally{await browser.close();await api(`/api/canvases/${cid}/purge`,null,'DELETE');if(generated.size)await api('/api/results/delete',{ids:[...generated]});}
})().catch(e=>{console.error(e);process.exit(1)});
