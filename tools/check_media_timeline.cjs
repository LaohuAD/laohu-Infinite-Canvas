/* 本地真实媒体验收：不调用模型，结束后清理本轮测试画布和结果。 */
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const base=process.env.CANVAS_TEST_URL||'http://127.0.0.1:3001',dir=path.resolve('cache/maintenance');process.env.TMPDIR=dir;
 const api=async(p,body,method)=>{const r=await fetch(base+p,{method:method||(body?'POST':'GET'),headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(JSON.stringify(d));return d;};
 const made=await api('/api/canvases',{title:'媒体时间轴验收_临时',kind:'smart'}),cid=made.id||made.canvas.id;
 const inputs=[],outputs=[];let browser;
 try{
 for(const ext of ['wav','mp4']){const form=new FormData();form.append('files',new Blob([fs.readFileSync(path.join(dir,'timeline-source.'+ext))]),'时间轴验收_'+Date.now()+'.'+ext);const data=await(await fetch(base+'/api/local-assets/upload',{method:'POST',body:form})).json();inputs.push(data.files[0]);}
 const caps=await api('/api/canvas-media-capabilities');assert.ok(caps.media_transform);assert.ok(caps.capabilities.ffmpeg.path);
 browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async r=>{if(r.url().endsWith('/api/canvas-media-transform')&&r.ok()){const d=await r.json();outputs.push(d.id);}});
 await page.goto(base+'/static/smart-canvas.html?id='+cid);await page.waitForFunction(()=>typeof canvas!=='undefined'&&canvas);
 const ids=await page.evaluate(items=>{nodes=[];canvas.connections=[];viewport={x:0,y:0,scale:1};applyViewport();return items.map((item,i)=>{const n=createNode(100+i*650,160,[{...item,name:i?'测试视频.mp4':'测试音频.wav'}],{select:false});render();return n.id;});},inputs);
 await page.evaluate(id=>openAudioMaterialPreview(id),ids[0]);const modal=page.locator('#smartAudioPreviewModal');
 await page.waitForFunction(()=>document.querySelector('[data-audio-timeline] .studio-timeline-bars').children.length===200);
 await modal.locator('audio').evaluate(el=>el.pause());
 const audioButtons=await modal.locator('[data-audio-toolbar] button').evaluateAll(els=>els.map(el=>{const r=el.getBoundingClientRect();return {y:r.y,h:r.height,w:r.width};}));assert.ok(audioButtons.every(r=>r.w>0&&r.h===32&&Math.abs(r.y-audioButtons[0].y)<1),JSON.stringify(audioButtons));
 const timeline=modal.locator('.studio-timeline'),track=timeline.locator('.studio-timeline-track'),box=await track.boundingBox();
 // 播放头放到中段，避免起点与开始手柄重合；在真实波形上拖动选区两端。
 await track.click({position:{x:box.width*.4,y:box.height*.6}});
 async function drag(handle,fraction){const r=await handle.boundingBox();await page.mouse.move(r.x+r.width/2,r.y+r.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width*fraction,box.y+box.height/2,{steps:8});await page.mouse.up();}
 await drag(timeline.locator('[data-time-handle=start]'),.2);await drag(timeline.locator('[data-time-handle=end]'),.7);
 let values=await page.evaluate(()=>mediaTransformValues());assert.ok(Math.abs(values.start-1)<.07&&Math.abs(values.end-3.5)<.07,JSON.stringify(values));
 await timeline.locator('[data-time-handle=end]').press('ArrowLeft');values=await page.evaluate(()=>mediaTransformValues());assert.ok(Math.abs(values.end-3.4)<.1);
 await modal.locator('[data-time-selection]').click();await page.waitForTimeout(300);assert.ok(await modal.locator('audio').evaluate(el=>el.currentTime>1));
 await modal.locator('audio').evaluate(el=>el.pause());
 for(const theme of ['dark','light']){await page.evaluate(t=>StudioTheme.apply(t),theme);await page.screenshot({path:path.join(dir,'media-timeline-audio-'+theme+'.png')});}
 await page.setViewportSize({width:620,height:900});await page.screenshot({path:path.join(dir,'media-timeline-audio-narrow.png')});assert.ok(await modal.locator('[data-time-handle=end]').evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;}));await page.setViewportSize({width:1440,height:1100});
 await modal.locator('[data-audio-transform=trim]').click();await page.waitForFunction(()=>nodes.length===3);assert.equal(await page.evaluate(()=>canvas.connections[0].kind),'story');
 const audioResult=await page.evaluate(()=>nodes[2].images[0]);assert.ok(audioResult.name.includes('s-'));assert.equal(audioResult.kind,'audio');
 assert.ok((await fetch(base+audioResult.url)).ok);
 await page.evaluate(id=>openImageEditor(id,0),ids[1]);await page.waitForFunction(()=>smartMediaTransformState?.timeline?.values().duration>4);
 assert.equal(await page.locator('#previewCurrentVideo').getAttribute('controls'),null);
 const videoTrack=page.locator('#videoMediaTimeline .studio-timeline-track');const vb=await videoTrack.boundingBox();
 await videoTrack.click({position:{x:vb.width*.5,y:vb.height*.7}});assert.ok(await page.locator('#previewCurrentVideo').evaluate(el=>el.currentTime>2));
 const vh=page.locator('#videoMediaTimeline [data-time-handle=end]');await vh.focus();await vh.press('ArrowLeft');await page.waitForFunction(()=>{const v=document.getElementById('previewCurrentVideo');return !v.seeking&&v.readyState>=2;});await page.screenshot({path:path.join(dir,'media-timeline-video.png')});
 assert.equal(await page.locator('#mediaLastFrameBtn').count(),1);assert.equal(await page.locator('[onclick="exportVideoFrame(\'last\')"]').count(),0);assert.equal(await page.locator('#imageEditCancelBtn').isVisible(),false);const videoButtons=await page.locator('#videoMediaToolbar button').evaluateAll(els=>els.map(el=>{const r=el.getBoundingClientRect();return {y:r.y,h:r.height,w:r.width};}));assert.ok(videoButtons.every(r=>r.w>0&&r.h>=28&&Math.abs(r.h-videoButtons[0].h)<1&&Math.abs(r.y-videoButtons[0].y)<1),JSON.stringify(videoButtons));
 await page.locator('#mediaTrimBtn').click();await page.waitForFunction(()=>nodes.length===4);assert.equal(await page.evaluate(()=>canvas.connections.at(-1).kind),'story');
 await page.evaluate(id=>runSmartNodeToolbarAction(id,'extract_audio'),ids[1]);await page.waitForFunction(()=>nodes.length===5);assert.equal(await page.evaluate(()=>nodes.at(-1).images[0].kind),'audio');
 await page.evaluate(id=>runSmartNodeToolbarAction(id,'last_frame'),ids[1]);await page.waitForFunction(()=>nodes.length===6);assert.equal(await page.evaluate(()=>nodes.at(-1).images[0].kind),'image');assert.ok(await page.evaluate(()=>nodes.at(-1).title.includes('尾帧')));
 assert.ok(await page.evaluate(()=>canvas.connections.every(c=>c.kind==='story')));
 assert.ok(await page.evaluate(ids=>nodes.filter(n=>!ids.includes(n.id)).every(n=>n.x>nodes.find(s=>s.id===canvas.connections.find(c=>c.to===n.id).from).x),ids));
 await page.evaluate(()=>saveCanvas());await page.reload();await page.waitForFunction(()=>typeof canvas!=='undefined'&&canvas&&nodes.length===6);assert.ok(await page.evaluate(()=>canvas.connections.every(c=>c.kind==='story')));
 // 独立检查成品时长和尾帧像素，而不只检查接口返回成功。
 const resultItems=await page.evaluate(()=>nodes.slice(2).map(n=>n.images[0]));
 for(let i=0;i<resultItems.length;i++){
  const item=resultItems[i],ext=i===3?'png':i===1?'mp4':'m4a',target=path.join(dir,'timeline-output-'+i+'.'+ext);
  fs.writeFileSync(target,Buffer.from(await(await fetch(base+item.url)).arrayBuffer()));
  if(i<3){const duration=Number(execFileSync(caps.capabilities.ffprobe.path,['-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',target],{encoding:'utf8'}));assert.ok(Math.abs(duration-[2.4,4.9,5][i])<.12,`${i}: ${duration}`);}
 }
 const expected=path.join(dir,'timeline-expected-tail.png');execFileSync(caps.capabilities.ffmpeg.path,['-v','error','-y','-i',path.join(dir,'timeline-source.mp4'),'-vf','select=eq(n\\,124)','-frames:v','1',expected]);
 execFileSync(path.resolve('.venv/bin/python'),['-c','from PIL import Image,ImageChops; import sys; assert ImageChops.difference(Image.open(sys.argv[1]),Image.open(sys.argv[2])).getbbox() is None',expected,path.join(dir,'timeline-output-3.png')]);
 for(let i=0;i<inputs.length;i++)assert.deepEqual(Buffer.from(await(await fetch(base+inputs[i].url)).arrayBuffer()),fs.readFileSync(path.join(dir,'timeline-source.'+(i?'mp4':'wav'))));
 for(const [index,frame] of ['First','Current'].entries()){
  await page.evaluate(id=>openImageEditor(id,0),ids[1]);await page.waitForFunction(()=>smartMediaTransformState?.timeline?.values().duration>4);
  if(frame==='Current'){await page.locator('#previewCurrentVideo').evaluate(v=>{v.pause();v.currentTime=2;});await page.waitForFunction(()=>!document.getElementById('previewCurrentVideo').seeking);}
  await page.locator('#media'+frame+'FrameBtn').click();await page.waitForFunction(count=>nodes.length===count,7+index);
  assert.equal(await page.evaluate(()=>canvas.connections.at(-1).kind),'story');assert.equal(await page.evaluate(()=>nodes.at(-1).images[0].kind),'image');
  assert.ok(await page.evaluate(label=>nodes.at(-1).title.includes(label),frame==='First'?'首帧':'当前帧'));
 }
 assert.deepEqual(errors,[]);console.log('通过：真实波形/拖选/定位/试听/键盘、明暗主题、统一工具栏与唯一尾帧入口、音视频实际裁剪、首帧/当前帧/尾帧和音频提取、名称/原素材保留/右侧虚线、保存重开。',JSON.stringify({inputs:inputs.map(i=>i.id),outputs}));
 }finally{if(browser)await browser.close();await api('/api/canvases/'+cid+'/purge',null,'DELETE');if(outputs.length)await api('/api/results/delete',{ids:outputs});if(inputs.length)await api('/api/local-assets/delete',{names:inputs.map(i=>i.id)});}
})().catch(e=>{console.error(e);process.exitCode=1;});
