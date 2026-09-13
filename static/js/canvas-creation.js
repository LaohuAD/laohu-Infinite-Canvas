/* 创作身份、任务与版本：纯数据模块，不依赖 DOM、平台或全局画布。 */
(function(root, factory){
    const api=factory();
    if(typeof module==='object' && module.exports) module.exports=api;
    if(root) root.CanvasCreation=api;
})(typeof globalThis!=='undefined'?globalThis:this, function(){
    'use strict';
    const TYPES=new Set(['smart-text-generator','smart-image-generator','smart-video-generator','smart-audio-generator','smart-music-generator','smart-ai-app','smart-comfy-workflow']);
    const clone=v=>v==null?v:JSON.parse(JSON.stringify(v));
    const newId=()=>{
        if(globalThis.crypto?.randomUUID) return `creation_${globalThis.crypto.randomUUID()}`;
        // 局域网 HTTP 页面没有 randomUUID；getRandomValues 不要求安全上下文。
        if(globalThis.crypto?.getRandomValues) return `creation_${Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('')}`;
        return `creation_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`;
    };
    const isCreation=n=>TYPES.has(n?.type);
    const stable=v=>JSON.stringify(v, function(k,x){return x && typeof x==='object' && !Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(key=>[key,x[key]])):x;});
    function recipe(n){
        return clone({type:n.type,runSettings:n.runSettings||{},promptDraftText:n.promptDraftText||'',manualInputRefs:n.manualInputRefs||[],blockedInputRefs:n.blockedInputRefs||[],inputRefOrder:n.inputRefOrder||[],creationInputBinding:n.creationInputBinding||[]});
    }
    // 仅用于历史结构化说明的单向导入；新说明始终保存自由 Markdown。
    function detailsMarkdown(value){
        if(typeof value==='string') return value;
        if(value==null) return '';
        const labels={role:'用途',episode:'集数',scene:'场次',segment_id:'分段编号',source_node_id:'来源节点',source_text:'来源正文',duration:'预计秒数',purpose:'本段作用',direction:'讲戏说明',assets:'资产',start_state:'开始状态',end_state:'结束状态',background:'背景',characters:'人物',notation:'符号说明',asset_category:'资产类别',owner:'归属',base_asset_node_id:'基础资产节点',state:'状态',notes:'补充说明',name:'名称',node_id:'节点'};
        function lines(item,depth=0){
            const indent='  '.repeat(depth);
            if(Array.isArray(item)) return item.map(entry=>entry && typeof entry==='object'?`${indent}-\n${lines(entry,depth+1)}`:`${indent}- ${String(entry)}`).join('\n');
            if(item && typeof item==='object') return Object.entries(item).filter(([,v])=>v!==null && v!==undefined && v!=='').map(([key,v])=>typeof v==='object'?`${indent}- **${labels[key]||key}**\n${lines(v,depth+1)}`:`${indent}- **${labels[key]||key}**：${String(v).replace(/\n/g,'\n'+indent+'  ')}`).join('\n');
            return indent+String(item);
        }
        return lines(value);
    }
    function ensure(n,id=newId){
        if(!isCreation(n) && n?.type!=='smart-material') return n;
        n.creationDetails = detailsMarkdown(n.creationDetails);
        n.creationId ||= id();
        n.creationOwnerNodeId ||= n.id;
        n.creationRevision ||= 1;
        n.creationSignature ??= stable(recipe(n));
        return n;
    }
    function reconcile(nodes,id=newId,connections){
        nodes.forEach(n=>ensure(n,id));
        for(const n of nodes){
            if(!isCreation(n) && n?.type!=='smart-material') continue;
            ensure(n,id);
            if(connections){
                const first=n.creationInputBinding===undefined;
                n.creationInputBinding=connections.filter(c=>(c.to||c.target)===n.id && !['story','history','result'].includes(c.kind)).map(c=>({
                    source:nodes.find(s=>s.id===(c.from||c.source))?.creationId || c.from || c.source,
                    version:c.sourceVersionId||'',field:c.targetFieldKey||''
                }));
                if(first) n.creationSignature=stable(recipe(n));
            }
            const signature=stable(recipe(n));
            if(n.creationSignature!==signature){
                n.creationParentId=n.creationId;
                n.creationId=id();
                n.creationOwnerNodeId=n.id;
                n.creationSignature=signature;
                n.creationRevision++;
            }
        }
    }
    function snapshot(n,id=n.id){
        return clone({...recipe(n),type:n.creationType||n.type,id,creationId:n.creationId,creationOwnerNodeId:n.creationOwnerNodeId,creationDetails:n.creationDetails,images:clone(n.images||[]),outputKind:n.outputKind,title:n.title,
            runPrompt:n.runPrompt||n.promptDraftText||'',runModelPrompt:n.runModelPrompt||n.runPrompt||n.promptDraftText||'',
            promptDraftHtml:n.promptDraftHtml||'',runInputRefs:clone(n.runInputRefs||n.manualInputRefs||[]),
            runPromptRefs:clone(n.runPromptRefs||[]),runRef:clone(n.runRef),runSnapshot:clone(n.runSnapshot),createdAt:n.runFinishedAt||n.created_at||Date.now()});
    }
    function begin(nodes,n,id=newId){
        reconcile(nodes,id);
        if(n.creationOwnerNodeId !== n.id){
            n.creationParentId=n.creationId; n.creationId=id(); n.creationOwnerNodeId=n.id; n.creationRevision++;
        }
        const task={...snapshot(n,id()),type:'smart-material',sourceKind:'result',sourceExecutionNodeId:n.id,
            creationId:n.creationId,creationSignature:n.creationSignature,creationTask:true,images:[],
            runStatus:'validating',isRunPlaceholder:true,pending:1,runStartedAt:Date.now(),runTimerHidden:false};
        (n.creationTasks ||= []).push(task);
        return task;
    }
    function tasks(nodes){return nodes.flatMap(n=>n.creationTasks||[]);}
    function publish(nodes,task,media=task.images){
        if(!task?.creationTask || task.runStatus==='cancelled' || !media?.length) return false;
        media=media.map(item=>({...item,creationId:task.creationId,creationRecordId:task.id}));
        const version={...snapshot(task,task.id),images:clone(media)};
        task.images=clone(media);
        for(const n of nodes){
            if(n.creationId!==task.creationId || stable(recipe(n))!==task.creationSignature) continue;
            const versions=n.resultVersions ||= (n.images?.length?[snapshot(n,`initial:${n.id}`)]:[]);
            const index=versions.findIndex(v=>v.id===task.id);
            if(index<0) versions.push(clone(version)); else versions[index]=clone(version);
            n.activeResultVersion=index<0?versions.length-1:index;
            n.images=clone(media); n.outputKind=version.outputKind||media[0]?.kind||'image';
            n.sourceKind='result'; n.creationRevision++;
        }
        task.published=true;
        return true;
    }
    function merge(local,remote){
        const newest=Number(remote.creationRevision||0)>Number(local.creationRevision||0)?remote:local;
        const merged=clone(newest);
        const byId=new Map();
        for(const version of [...(local.resultVersions||[]),...(remote.resultVersions||[]),...(newest.resultVersions||[])]){
            if(version.id) byId.set(version.id,clone(version));
        }
        merged.resultVersions=[...byId.values()];
        const selected=newest.resultVersions?.[newest.activeResultVersion||0]?.id;
        merged.activeResultVersion=Math.max(0,merged.resultVersions.findIndex(v=>v.id===selected));
        const rank=t=>t.runStatus==='cancelled'?4:['succeeded','partially_succeeded'].includes(t.runStatus)?3:t.runStatus==='failed'?2:1;
        const taskMap=new Map();
        for(const t of [...(local.creationTasks||[]),...(remote.creationTasks||[])]){
            const old=taskMap.get(t.id);
            if(!old || rank(t)>rank(old) || rank(t)===rank(old) && Number(t.runFinishedAt||0)>Number(old.runFinishedAt||0)) taskMap.set(t.id,clone(t));
        }
        merged.creationTasks=[...taskMap.values()];
        return merged;
    }
    function references(node,connection={}){
        if(connection.sourceVersionId){
            return clone(node.resultVersions?.find(v=>v.id===connection.sourceVersionId)?.images||[]);
        }
        return clone(node.images||[]);
    }
    function migrate(rawNodes,rawConnections,id=newId){
        const nodes=clone(rawNodes||[]), links=clone(rawConnections||[]), removed=new Map();
        for(const n of nodes){
            if(!isCreation(n)) continue;
            ensure(n,id);
            const outputs=nodes.filter(r=>r.type==='smart-material' && r.id!==n.id && (r.sourceExecutionNodeId===n.id || links.some(c=>c.from===n.id && c.to===r.id && c.kind==='result')));
            for(const r of outputs){
                if(r.pending || r.running || r.pendingTasks?.length || r.jimengPending || r.runStatus==='failed' || r.isRunPlaceholder){
                    (n.creationTasks ||= []).push({...r,creationTask:true,creationId:n.creationId,creationSignature:n.creationSignature,sourceExecutionNodeId:n.id});
                    removed.set(r.id,{node:n.id}); continue;
                }
                if(!r.images?.length) continue;
                const versions=r.resultVersions?.length?r.resultVersions.map((v,i)=>({...v,id:v.id||`legacy:${r.id}:${i}`})):[snapshot({...n,...r},`legacy:${r.id}`)];
                n.resultVersions ||= [];
                for(const v of versions) if(!n.resultVersions.some(x=>x.id===v.id)) n.resultVersions.push(v);
                const active=versions[Math.min(versions.length-1,r.activeResultVersion||0)];
                removed.set(r.id,{node:n.id,version:active.id});
                n.images=clone(active.images); n.sourceKind='result';
                n.activeResultVersion=n.resultVersions.findIndex(v=>v.id===active.id);
            }
        }
        const nextLinks=links.flatMap(c=>{
            const from=removed.get(c.from), to=removed.get(c.to);
            if(to && c.kind==='result' && c.from===to.node) return [];
            const next={...c,from:from?.node||c.from,to:to?.node||c.to};
            if(from?.version) next.sourceVersionId=from.version;
            if(next.from===next.to) return [];
            return [next];
        });
        const retained=nodes.filter(n=>!removed.has(n.id));
        function remapReferences(value){
            if(Array.isArray(value)) return value.map(remapReferences);
            if(!value || typeof value!=='object') return value;
            const next={...value};
            for(const key of Object.keys(next)){
                if(['nodeId','sourceNodeId','node_id','source_node_id','base_asset_node_id'].includes(key) && removed.has(next[key])){
                    const target=removed.get(next[key]); next[key]=target.node;
                    if(target.version) next.sourceVersionId=target.version;
                } else if(typeof next[key]==='object') next[key]=remapReferences(next[key]);
            }
            return next;
        }
        for(const n of retained){
            if(n.inputNodeIds) n.inputNodeIds=[...new Set(n.inputNodeIds.map(key=>removed.get(key)?.node||key))].filter(key=>key!==n.id);
            if(n.items) n.items=[...new Set(n.items.map(key=>typeof key==='string'?(removed.get(key)?.node||key):key))];
            for(const key of ['manualInputRefs','runInputRefs','runPromptRefs','creationDetails','resultVersions']) if(n[key]) n[key]=remapReferences(n[key]);
            if(n.promptDraftHtml) for(const [old,target] of removed) n.promptDraftHtml=n.promptDraftHtml.split(`data-node-id="${old}"`).join(`data-node-id="${target.node}"`);
            ensure(n,id);
        }
        return {nodes:retained,connections:nextLinks,changed:removed.size>0};
    }
    function updateDetails(n,markdown,expectedRevision){
        ensure(n);
        if(expectedRevision!==undefined && Number(expectedRevision)!==n.creationRevision) throw new Error('内容已修改，请重新读取 / Content changed; read the node again');
        if(typeof markdown!=='string') throw new Error('创作说明请填写 Markdown 文本 / Creation notes must be Markdown text');
        n.creationDetails=markdown; n.creationRevision++;
        return n;
    }
    return {isCreation,recipe,ensure,reconcile,begin,tasks,publish,merge,references,migrate,snapshot,detailsMarkdown,updateDetails};
});
