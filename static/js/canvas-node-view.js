/* 节点标题编辑：草稿独立于画布数据，重渲染可恢复，提交只修改节点名称。 */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.CanvasNodeView=api;})(globalThis,function(){
    const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function createTitleEditor({getNode,commit,render,text}){
        const drafts=new Map();
        function markup(node,fallback=''){
            if(drafts.has(node.id))return `<input class="node-title-editor" data-node-title-input="${escape(node.id)}" type="text" maxlength="160" value="${escape(drafts.get(node.id))}" aria-label="${escape(text('节点名称','Node name'))}">`;
            return `<div class="node-title" data-creation-title="${escape(node.id)}" title="${escape(text('双击修改名称','Double-click to rename'))}">${escape(node.title||fallback)}</div>`;
        }
        function bind(root){
            root.querySelectorAll('[data-creation-title]').forEach(label=>{
                label.addEventListener('click',e=>e.stopPropagation());
                label.addEventListener('dblclick',e=>{
                    if(e.shiftKey)return;
                    e.preventDefault();e.stopPropagation();
                    const node=getNode(label.dataset.creationTitle);if(!node)return;
                    drafts.set(node.id,node.title||label.textContent||'');render();
                    const input=document.querySelector(`[data-node-title-input="${CSS.escape(node.id)}"]`);input?.focus();input?.select();
                });
            });
            root.querySelectorAll('[data-node-title-input]').forEach(input=>{
                const id=input.dataset.nodeTitleInput;
                let composing=false,finished=false;
                const finish=save=>{
                    if(finished||!input.isConnected)return;finished=true;
                    const name=input.value.trim();drafts.delete(id);
                    const node=getNode(id);if(save&&name&&node&&name!==node.title)commit(node,name);
                    render();
                };
                input.addEventListener('input',()=>drafts.set(id,input.value));
                input.addEventListener('compositionstart',()=>composing=true);
                input.addEventListener('compositionend',()=>composing=false);
                ['click','dblclick','mousedown','pointerdown'].forEach(type=>input.addEventListener(type,e=>e.stopPropagation()));
                input.addEventListener('keydown',e=>{e.stopPropagation();if(composing||e.isComposing)return;if(e.key==='Enter'){e.preventDefault();finish(true);}if(e.key==='Escape'){e.preventDefault();finish(false);}});
                // DOM 替换也触发 blur；下一拍确认编辑框仍存在，避免重入 render。
                input.addEventListener('blur',()=>setTimeout(()=>{if(document.hasFocus()&&input.isConnected&&document.activeElement!==input)finish(true);},0));
            });
        }
        return {markup,bind};
    }
    function layoutOverlays(root,scale,screenWidth){
        const inverse=1/Math.max(.01,scale);
        root.querySelectorAll('.image-node.creation-node').forEach(el=>{
            const head=el.querySelector(':scope > .node-head'),rail=el.querySelector(':scope > .result-version-switcher');
            if(head){
                const width=Math.min(Math.max(60,el.offsetWidth*scale),Math.max(280,screenWidth-28),760);
                Object.assign(head.style,{width:width+'px',left:(el.offsetWidth-width*inverse)/2+'px',top:-30*inverse+'px',height:'24px',minHeight:'24px',transform:`scale(${inverse})`,transformOrigin:'0 0'});
                const actions=head.querySelector('.node-actions');
                if(actions&&el.classList.contains('selected')){
                    actions.style.width='max-content';actions.style.maxWidth=Math.max(280,screenWidth-28)+'px';
                    const w=actions.offsetWidth,headRect=head.getBoundingClientRect();
                    const ideal=headRect.left+width/2-w/2;
                    actions.style.left=(Math.max(14,Math.min(ideal,screenWidth-w-14))-headRect.left)+'px';
                }
            }
            if(rail)Object.assign(rail.style,{left:(el.offsetWidth+18*inverse)+'px',top:'0px',height:Math.max(42,el.offsetHeight*scale)+'px',transform:`scale(${inverse})`,transformOrigin:'0 0'});
        });
    }
    // 世界坐标宫格：保留原布局，只把中心就近吸附到一个或多个格子的中心。
    function alignToGrid(items, obstacles=[], {width=316,height=194,gapX=80,gapY=72}={}){
        const pitchX=width+gapX,pitchY=height+gapY;
        const overlaps=(a,b,pad=0)=>a.x<b.x+b.width+pad&&a.x+a.width+pad>b.x&&a.y<b.y+b.height+pad&&a.y+a.height+pad>b.y;
        const describe=item=>{
            const cols=Math.max(1,Math.round(item.width/width)),rows=Math.max(1,Math.round(item.height/height));
            const cx=item.x+item.width/2,cy=item.y+item.height/2;
            const col=Math.round(cx/pitchX-cols/2),row=Math.round(cy/pitchY-rows/2);
            return {...item,cols,rows,cx,cy,col,row,distance:((col+cols/2)*pitchX-cx)**2+((row+rows/2)*pitchY-cy)**2};
        };
        const occupied=[],fixed=obstacles.map(r=>({...r})),result=[];
        // 已经就位的节点优先，避免第二次整理把第一次排好的布局再次挪动。
        const ordered=items.map(describe).sort((a,b)=>a.distance-b.distance||a.y-b.y||a.x-b.x||String(a.id).localeCompare(String(b.id)));
        for(const item of ordered){
            let best=null;
            for(let radius=0; ;radius++){
                for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){
                    if(Math.max(Math.abs(dx),Math.abs(dy))!==radius)continue;
                    const col=item.col+dx,row=item.row+dy;
                    const x=Math.round((col+item.cols/2)*pitchX-item.width/2),y=Math.round((row+item.rows/2)*pitchY-item.height/2);
                    const score=(x+item.width/2-item.cx)**2+(y+item.height/2-item.cy)**2;
                    if(best&&score>=best.score)continue;
                    const block={x:col,y:row,width:item.cols,height:item.rows},rect={x,y,width:item.width,height:item.height};
                    if(occupied.some(b=>overlaps(block,b))||fixed.some(r=>overlaps(rect,r,24)))continue;
                    best={id:item.id,x,y,score,block,rect};
                }
                // 下一圈任何位置都不可能更近时停止，避免把冲突节点搬到远处。
                if(best&&((radius+.5)*Math.min(pitchX,pitchY)-1)**2>best.score)break;
            }
            occupied.push(best.block);fixed.push(best.rect);result.push({id:best.id,x:best.x,y:best.y});
        }
        return result;
    }
    // 动效属于任务，不属于 render。保留 DOM 和 WAAPI 实例，节点重绘不重置播放时间。
    const runningEffects=new Map();
    let motionPreference;
    function syncRunningEffects(root){
        if(!motionPreference){
            motionPreference=matchMedia('(prefers-reduced-motion: reduce)');
            motionPreference.addEventListener('change',()=>{
                runningEffects.forEach(({animations})=>animations.forEach(a=>motionPreference.matches?a.pause():a.play()));
            });
        }
        const live=new Set();
        root.querySelectorAll('[data-running-effect]').forEach(slot=>{
            const key=JSON.stringify([slot.closest('[data-id]').dataset.id,slot.dataset.runningEffect]);
            live.add(key);
            let record=runningEffects.get(key);
            if(!record){
                let seed=2166136261;
                for(const c of slot.dataset.runningEffect)seed=Math.imul(seed^c.charCodeAt(0),16777619);
                seed=seed||1;
                const random=()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>>0)/4294967296;};
                const animations=[];
                for(let i=0;i<3;i++){
                    const mover=document.createElement('div');mover.className='creation-running-mover';
                    const light=document.createElement('div');light.className='creation-running-light';
                    for(let dot=0;dot<16;dot++){
                        const point=document.createElement('i');
                        point.style.opacity=String(.18+random()*.65);light.appendChild(point);
                    }
                    mover.appendChild(light);slot.appendChild(mover);
                    // 有界随机路径，慢速淡入淡出；使用 transform 避免每帧布局和画布重绘。
                    const frames=Array.from({length:33},()=>({
                        transform:`translate(${(random()-.5)*66}%,${(random()-.5)*48+8}%) scale(${.8+random()*.4})`,
                        opacity:.18+random()*.64,easing:'ease-in-out'
                    }));
                    frames.push({...frames[0]});
                    const animation=mover.animate(frames,{duration:165000+i*17000,iterations:Infinity});
                    animation.currentTime=Math.max(0,Date.now()-(Number(slot.dataset.runningStarted)||Date.now()))+i*11000;
                    if(motionPreference.matches)animation.pause();
                    animations.push(animation);
                }
                record={element:slot,animations};runningEffects.set(key,record);
            }else if(slot!==record.element){
                record.element.className=slot.className;
                slot.replaceWith(record.element);
            }
        });
        for(const [key,record] of runningEffects){
            if(live.has(key))continue;
            record.animations.forEach(a=>a.cancel());record.element.remove();runningEffects.delete(key);
        }
    }
    return {createTitleEditor,layoutOverlays,alignToGrid,syncRunningEffects};
});
