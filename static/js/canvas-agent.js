/* Agent 只调用现有画布动作；不解释代码，不绕过模型预检。 */
(() => {
    'use strict';
    const text = (zh, en) => capabilityUiText(zh, en);
    const nodeKinds = {material:'smart-material', text:'smart-text-generator', image:'smart-image-generator', video:'smart-video-generator', audio:'smart-audio-generator', music:'smart-music-generator', app:'smart-ai-app', comfy:'smart-comfy-workflow'};
    const fields = {text:['textProvider','textModel','textFamilyId','text_generation'], image:['provider_id','model','imageFamilyId','image_generation'], video:['videoProvider','videoModel','videoFamilyId','video_generation'], audio:['audioProvider','audioModel','audioFamilyId','audio_generation'], music:['musicProvider','musicModel','musicFamilyId','music_generation']};
    const commandResults = new Map();
    let polling = false, canvasReady = false;
    const endpoint = () => `/api/agent/canvases/${encodeURIComponent(canvasId)}`;
    async function api(path, payload){
        const response = await fetch(path, {method:payload ? 'POST' : 'GET', headers:{'Content-Type':'application/json'}, ...(payload ? {body:JSON.stringify(payload)} : {})});
        const data = await response.json();
        if(!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
        return data;
    }
    function find(id){
        const node = nodes.find(n => n.id === id);
        if(!node) throw new Error(text(`节点不存在：${id}`, `Node not found: ${id}`));
        return node;
    }
    function select(node){
        savePromptDraftForCurrent();
        selectedId = node.id;
        selectedIds = [node.id];
        settings = cloneSmartSettings(smartSettingsForNode(node));
        lastComposerNodeId = '';
        render();
        updateComposer();
    }
    function configure(node, args){
        CanvasCreation.ensure(node);
        if(args.expected_revision !== undefined && args.expected_revision !== node.creationRevision) throw new Error(text('节点已修改，请重新读取再更新','Node changed; read it again before updating'));
        if(args.creation_details !== undefined) CanvasCreation.updateDetails(node,args.creation_details,args.expected_revision);
        const kind = Object.keys(nodeKinds).find(k => nodeKinds[k] === node.type);
        const keys = fields[kind];
        if(args.model !== undefined || args.provider_id !== undefined || args.parameters !== undefined){
            if(!keys) throw new Error(text('此节点请通过 run_settings 配置已同步应用或工作流','Use run_settings for this app or workflow node'));
            const source = cloneSmartSettings(node.runSettings || {});
            const provider = args.provider_id ?? source[keys[0]];
            const model = args.model ?? source[keys[1]];
            const profile = capabilityProfileFor(provider, model, keys[3]);
            if(!profile?.runnable) throw new Error(text('模型未启用或适配不可用，请读取模型能力列表','Model is disabled or unavailable; read model capabilities'));
            for(const key of Object.keys(args.parameters || {})){
                if(!Object.hasOwn(profile.parameters || {}, key)) throw new Error(text(`模型不支持参数：${key}`, `Unsupported parameter: ${key}`));
            }
            const changedModel = source[keys[0]] !== provider || source[keys[1]] !== model;
            source[keys[0]] = provider; source[keys[1]] = model; source[keys[2]] = profile.family_id;
            source.capabilityParameters = {...source.capabilityParameters, [model]:{...(!changedModel ? source.capabilityParameters?.[model] : {}), ...(args.parameters || {})}};
            if(kind === 'image' && args.parameters?.count !== undefined) source.count = args.parameters.count === CAPABILITY_PARAMETER_UNSET ? 1 : Number(args.parameters.count);
            node.runSettings = source;
        }
        if(args.run_settings){
            if(!['app','comfy'].includes(kind)) throw new Error(text('普通模型使用 provider_id、model、parameters 配置','Use provider_id, model and parameters for models'));
            const allowed = kind === 'app' ? ['rhAppId','rhConfigKey','rhParams'] : ['comfyWorkflow','comfyParams'];
            if(Object.keys(args.run_settings).some(k => !allowed.includes(k))) throw new Error(text('包含未支持的应用设置字段','Unsupported app settings field'));
            node.runSettings = {...node.runSettings, ...args.run_settings};
        }
        if(node.runSettings) node.runSettings=SMART_NODE_CONTRACT.normalizeExecutionSettings(node,node.runSettings);
        for(const key of ['x','y','w','h']) if(args[key] !== undefined){
            if(!Number.isFinite(args[key]) || (['w','h'].includes(key) && args[key] <= 0)) throw new Error(`Invalid ${key}`);
            node[key] = args[key];
        }
        if(args.title !== undefined) node.title = String(args.title).slice(0,160);
        if(args.text !== undefined){
            if(kind === 'material'){
                if(!node.images?.every(item=>mediaKindForItem(item)==='text')) throw new Error('Only text material accepts text');
                if(node.images?.length){
                    node.resultVersions ||= [CanvasCreation.snapshot(node,uid('version'))];
                    node.creationParentId=node.creationId; node.creationId=uid('creation'); node.creationOwnerNodeId=node.id;
                }
                node.images=[{kind:'text',text:String(args.text),content:String(args.text),name:node.title||'正文.md'}];
                node.resultVersions ||= [];
                node.resultVersions.push(CanvasCreation.snapshot(node,uid('version')));
                node.activeResultVersion=node.resultVersions.length-1;
                node.creationRevision++;
            } else
            setPromptDraftForNode(node, args.text);
        }
        if(selectedId === node.id){
            settings = cloneSmartSettings(smartSettingsForNode(node));
            lastComposerNodeId = '';
            updateComposer();
        }
        if(args.production !== undefined) CanvasProduction.update(node,args.production,nodes,canvas.connections);
    }
    async function persist(){
        clearTimeout(saveTimer);
        CanvasCreation.reconcile(nodes,undefined,canvas.connections||[]);
        const expectedNodes=cloneSmartSettings(nodes);
        await saveCanvas();
        const remote = await api(`/api/canvases/${encodeURIComponent(canvasId)}`);
        const saved = remote.canvas || remote;
        for(const node of expectedNodes){
            const stored = (saved.nodes || []).find(n => n.id === node.id);
            const matches = (expected, actual) => expected && typeof expected === 'object'
                ? actual && typeof actual === 'object' && Object.entries(expected).every(([key,value]) => matches(value, actual[key]))
                : expected === actual;
            const keys = ['type','title','promptDraftText','x','y','w','h','runSettings','creationId','creationDetails','creationRevision','production'];
            if(!stored || !keys.every(key => matches(node[key],stored[key]))) throw new Error(text('画布尚未保存成功，请查询实时状态，不要重复提交运行','Canvas save is unconfirmed; inspect state before retrying'));
        }
        const expectedConnections = canvas.connections || [];
        const actualConnections = saved.connections || [];
        if(expectedConnections.length !== actualConnections.length || expectedConnections.some(connection => !actualConnections.some(stored => stored.from === connection.from && stored.to === connection.to && (stored.targetFieldKey || '') === (connection.targetFieldKey || '') && (stored.kind||'flow') === (connection.kind||'flow')))) throw new Error(text('连线保存尚未确认，请查询画布状态','Connection save is unconfirmed; inspect canvas state'));
    }
    async function execute(command){
        const a = command.args || {};
        if(command.action === 'production_status') return {rows:CanvasProduction.rows(nodes,canvas.connections||[])};
        if(command.action === 'snapshot') return {canvas:canvasForStorage()};
        if(command.action === 'duplicate_node'){
            const source=find(a.node_id);
            pushUndo();
            const copy=cloneSmartNode(source,a.dx==null?420:Number(a.dx),a.dy==null?0:Number(a.dy));
            if(a.title) copy.title=String(a.title).slice(0,160);
            nodes.push(copy);
            canvas.connections.push(...(canvas.connections||[]).filter(c=>c.to===source.id).map(c=>({...c,id:uid('edge'),to:copy.id})));
            render(); await persist(); return {node_id:copy.id,node:copy};
        }
        if(command.action === 'group_nodes'){
            const members=(a.node_ids||[]).map(find);
            if(!members.length || !String(a.title||'').trim()) throw new Error('Provide node_ids and a meaningful title');
            const group=createSmartGroupNode(0,0,{select:false});
            group.title=String(a.title).slice(0,160); group.items=members.map(n=>n.id); fitSmartGroupBounds(group);
            render(); await persist(); return {node_id:group.id,node:group};
        }
        if(command.action === 'create_node'){
            if(!String(a.title||'').trim()) throw new Error(text('请提供有实际意义的节点名称 title','Provide a meaningful node title'));
            const type = nodeKinds[a.kind];
            if(!type) throw new Error(text('kind 必须为 material/text/image/video/audio/music/app/comfy','Invalid node kind'));
            let node;
            if(a.kind === 'material'){
                let items = a.media || [];
                if(a.text !== undefined) items = [{kind:'text', text:String(a.text), content:String(a.text), name:a.title || text('Agent 文本','Agent text')}];
                if(!Array.isArray(items)) throw new Error('media must be an array');
                node = createNode(Number(a.x) || 0, Number(a.y) || 0, items, {select:false});
                await restoreCreationFromMaterial(node);
                try { configure(node, {...a, text:undefined}); } catch(error){ deleteNode(node.id); throw error; }
            } else {
                node = createExecutionNode(Number(a.x) || 0, Number(a.y) || 0, type, {select:false});
                try {
                    const defaults = canvasDefaultSmartSettings.agentDefaults?.[a.kind];
                    if(!defaults && fields[a.kind] && !a.provider_id && !a.model && a.defer_configuration){
                        const keys=fields[a.kind];node.runSettings={...node.runSettings,[keys[0]]:'',[keys[1]]:'',[keys[2]]:'',capabilityParameters:{}};
                        configure(node,a);render();await persist();return {node_id:node.id,node,needs_configuration:true};
                    }
                    if(!defaults && fields[a.kind] && !(a.provider_id && a.model)) throw new Error(text('请先在 Agent 接入中设置此类节点默认模型，或明确提供平台和模型','Set defaults for this node type, or provide a provider and model'));
                    if(fields[a.kind]) node.runSettings.capabilityParameters = {};
                    if(a.kind === "image") node.runSettings.count = 1;
                    const changedModel = (a.model !== undefined && a.model !== defaults?.model) || (a.provider_id !== undefined && a.provider_id !== defaults?.provider_id);
                    configure(node, {...defaults,...a, ...(fields[a.kind] ? {parameters:{...(!changedModel ? defaults?.parameters : {}),...a.parameters}} : {}), ...(defaults?.run_settings || a.run_settings ? {run_settings:{...defaults?.run_settings,...a.run_settings}} : {})});
                } catch(error){ deleteNode(node.id); throw error; }
            }
            render(); await persist(); return {node_id:node.id, node};
        }
        if(command.action === 'update_node'){
            const node = find(a.node_id);
            savePromptDraftForCurrent();
            const backup = JSON.parse(JSON.stringify(node));
            pushUndo();
            try { configure(node, a); } catch(error){ Object.keys(node).forEach(k => delete node[k]); Object.assign(node, backup); throw error; }
            render(); await persist(); return {node_id:node.id, node};
        }
        if(command.action === 'connect'){
            const source = find(a.from); const target = find(a.to);
            if(source.id === target.id) throw new Error('Cannot connect a node to itself');
            if(a.relation === 'story'){
                pushUndo(); addConnection(source.id,target.id,'story'); render(); await persist(); return {connections:canvas.connections};
            }
            let key = a.target_field_key || '';
            if(target.type === SMART_NODE_TYPES.aiApp){
                const list = rhActiveFields(smartSettingsForNode(target));
                const plan = SMART_NODE_CONTRACT.runningHubTargetFieldPlan(list, runningHubSourceKind(source, {}), canvas.connections || [], target.id);
                key = key || (plan.mode === 'auto' ? plan.targetFieldKey : '');
                if(!key || !list.some(f => `${f.nodeId}::${f.fieldName}` === key)) throw new Error(text('请提供官方字段 target_field_key（nodeId::fieldName）','Provide an official target_field_key (nodeId::fieldName)'));
            }
            pushUndo();
            if(!connectInputNode(source.id, target.id, {targetFieldKey:key, sourceResultId:a.source_result_id || '', sourceMediaKey:a.source_media_key || ''})) throw new Error('Incompatible connection');
            render(); await persist(); return {connections:canvas.connections};
        }
        if(command.action === 'disconnect'){
            find(a.from); find(a.to); pushUndo();
            const indexes = (canvas.connections || []).map((c,i) => c.from === a.from && c.to === a.to && (!a.relation || (a.relation==='story' ? c.kind==='story' : c.kind!=='story')) ? i : -1).filter(i => i >= 0).reverse();
            indexes.forEach(i => disconnectConnection(i)); render(); await persist(); return {removed:indexes.length};
        }
        if(command.action === 'delete_node'){
            const node = find(a.node_id);
            if(node.running || node.pending) throw new Error(text('请先停止运行再删除','Cancel the run before deleting'));
            deleteNode(node.id);
            if(nodes.some(n=>n.id===node.id)) throw new Error(text('节点未删除，请先停止其运行任务','Node was not deleted; cancel its running tasks first'));
            await persist(); return {deleted:node.id};
        }
        if(command.action === 'arrange'){
            const ids = a.node_ids || nodes.map(n => n.id); ids.forEach(find);
            arrangeSmartIdsOnGrid(ids); render(); await persist(); return {node_ids:ids};
        }
        if(command.action === 'cancel_run'){
            const taskId=a.task_id||a.node_id; if(!CanvasCreation.tasks(nodes).some(t=>t.id===taskId)) find(taskId); await cancelExecutionResultRun(taskId); await persist(); return {cancelled:taskId};
        }
        if(command.action === 'run_node'){
            const node = find(a.node_id);
            if(!isSmartExecutionNode(node)) throw new Error(text('请选择执行节点','Select an execution node'));
            select(node);
            const before = new Set(CanvasCreation.tasks(nodes).map(t=>t.id));
            await runSelectedNode();
            const tasks=CanvasCreation.tasks(nodes).filter(t=>!before.has(t.id) && t.sourceExecutionNodeId===node.id);
            await persist();
            if(!tasks.length) throw new Error(text('运行未提交，请查看预检日志','Run was not submitted; check preflight logs'));
            return {node_id:node.id, task_ids:tasks.map(t=>t.id), tasks, versions:node.resultVersions||[]};
        }
        throw new Error('Unsupported action');
    }
    async function finish(command){
        let completion = commandResults.get(command.id);
        if(!completion){
            try { completion = {status:'succeeded', result:await execute(command)}; }
            catch(error){ completion = {status:'failed', error:String(error.message || error)}; }
            commandResults.set(command.id, completion);
        }
        try {
            await api(`${endpoint()}/commands/${command.id}/complete`, {...completion, client_id:smartClientId, claim_token:command.claim_token});
            commandResults.delete(command.id);
        } catch(error){ setTimeout(() => finish(command), 3000); }
    }
    async function poll(){
        if(!canvasReady || polling || typeof canvasId === 'undefined' || !canvasId || !canvas || !nodes || canvasSyncInFlight) return;
        // 用户正在输入时等到编辑结束，避免抢走焦点与光标。
        if(!modelCapabilityCatalog?.providers?.length) return;
        if(document.activeElement?.matches('input,textarea,[contenteditable="true"]')) return;
        polling = true;
        try {
            const data = await api(`${endpoint()}/claim`, {client_id:smartClientId});
            if(data.command){
                if(data.command.action === 'run_node') void finish(data.command);
                else await finish(data.command);
            }
        } catch(error){ /* 服务重启时下一轮恢复，不重投已领取的命令。 */ }
        finally { polling = false; }
    }
    setInterval(poll, 1500);
    const button = document.getElementById('canvasAgentToggle');
    window.addEventListener('canvas-ready', () => { canvasReady = true; button.disabled = false; });
    const dialog = document.getElementById('canvasAgentDialog');
    const guide = document.getElementById('canvasAgentInstructions');
    const defaultsRoot = document.getElementById('canvasAgentDefaults');
    const feedback = document.getElementById('canvasAgentFeedback');
    let defaultDraft = {}, defaultKind = 'image';
    const kindLabels = () => ({text:text('文本 / LLM','Text / LLM'), image:text('图片','Image'), video:text('视频','Video'), audio:text('音频','Audio'), music:text('音乐','Music'), app:text('AI 应用','AI app'), comfy:'ComfyUI'});
    const profilesFor = kind => (modelCapabilityCatalog?.providers || []).flatMap(provider => (provider.models || []).filter(profile => profile.node_type === fields[kind]?.[3] && profile.runnable).map(profile => ({...profile, provider_id:provider.id || provider.provider_id})));
    function defaultProfile(){
        const current = defaultDraft[defaultKind] || {};
        if(fields[defaultKind]) return profilesFor(defaultKind).find(p => p.provider_id === current.provider_id && p.model_id === current.model);
        const source=current.run_settings || {};
        const app=runningHubEntries('app').find(entry=>runningHubEntryId(entry,'app')===source.rhAppId);
        const definitions=defaultKind==='app' ? rhEntryFields(app) : (comfyWorkflowCache[source.comfyWorkflow]?.config?.fields || []);
        const parameters={};
        definitions.forEach(field=>{
            const kind=defaultKind==='app' ? rhFieldRole(field) : comfyFieldKind(field);
            if(['image','video','audio','prompt','text'].includes(kind)) return;
            const key=defaultKind==='app' ? rhParamKey(field.nodeId,field.fieldName) : field.id;
            parameters[key]=externalParameterSpec(field,defaultKind==='app'?'rh':'comfy');
        });
        return {model_id:source.rhAppId || source.comfyWorkflow || '',parameters};
    }
    function renderDefaultEditor(openKey=''){
        const current = defaultDraft[defaultKind] || {};
        const profiles = profilesFor(defaultKind);
        const profile = defaultProfile();
        const providerIds = [...new Set(profiles.map(p => p.provider_id))];
        const providerProfiles = profiles.filter(p => p.provider_id === current.provider_id);
        const families = [...new Map(providerProfiles.map(p => [p.family_id || p.model_id,p])).values()];
        const variants = providerProfiles.filter(p => (p.family_id || p.model_id) === (profile?.family_id || profile?.model_id));
        const option = (value,label,chosen) => `<option value="${escapeAttr(value)}" ${value === chosen ? 'selected' : ''}>${escapeHtml(label)}</option>`;
        const empty = option('',text('请选择','Select'),'');
        const select = (id,label,options) => `<label><span>${escapeHtml(label)}</span><select data-agent-select="${id}" aria-label="${escapeAttr(label)}">${empty}${options}</select></label>`;
        let editor;
        if(fields[defaultKind]){
            editor = `<div class="agent-default-selectors">${select('provider',text('平台','Provider'),providerIds.map(id => option(id,apiProviders.find(p => p.id === id)?.name || id,current.provider_id)).join(''))}${select('family',text('模型','Model'),families.map(p => option(p.family_id || p.model_id,text(p.family_name || p.display_name || p.model_id,p.family_name_en || p.family_name || p.display_name || p.model_id),profile?.family_id || profile?.model_id)).join(''))}${select('model',text('运行模式','Mode'),variants.map(p => option(p.model_id,capabilityVariantLabel(p),current.model)).join(''))}</div>`;
            if(profile){
                const values = capabilityParameterValues(profile,{capabilityParameters:{[profile.model_id]:current.parameters || {}}});
                editor += `<div class="agent-default-params">${Object.entries(profile.parameters || {}).filter(([,spec]) => spec.ui_hidden !== true).map(([key,spec]) => {
                    const entry = renderCapabilityParameterEditor(key,spec,profile,values);
                    const label = entry.unset ? entry.label : `${entry.label} · ${capabilityParameterPreview(key,spec,entry.value,false)}`;
                    return `<details class="agent-default-param" data-agent-param="${escapeAttr(key)}" ${key === openKey ? 'open' : ''}><summary>${escapeHtml(label)}</summary><div class="agent-param-body"><strong>${escapeHtml(entry.label)}</strong><p>${escapeHtml(entry.description)}</p>${entry.body}</div></details>`;
                }).join('')}</div>`;
            } else editor += `<p>${escapeHtml(current.model ? text('已保存的模型当前不可用，请重新选择。','The saved model is unavailable. Select a model.') : text('选择后，Agent 创建此类节点就会使用这里的模型和参数。','Once configured, agents use this model and its parameters for new nodes.'))}</p>`;
        } else {
            const source = current.run_settings || {};
            const entries=defaultKind==='app' ? runningHubEntries('app').map(entry=>({id:runningHubEntryId(entry,'app'),name:runningHubEntryLabel(entry,'app')})) : comfyWorkflows.map(entry=>({id:entry.name,name:entry.title || entry.name}));
            editor=`<div class="agent-default-selectors">${select('custom',defaultKind==='app'?text('AI 应用','AI app'):text('工作流','Workflow'),entries.map(entry=>option(entry.id,entry.name,source.rhAppId || source.comfyWorkflow)).join(''))}</div>`;
            if(!entries.length) editor+=`<p>${text('请先在 API 设置中添加应用或工作流。','Add an app or workflow in API settings first.')}</p>`;
            if(profile?.model_id){
                const values=capabilityParameterValues(profile,{capabilityParameters:{[profile.model_id]:source.rhParams || source.comfyParams || {}}});
                editor+=`<div class="agent-default-params">${Object.entries(profile.parameters).map(([key,spec])=>{
                    const entry=renderCapabilityParameterEditor(key,spec,profile,values);
                    return `<details class="agent-default-param" data-agent-param="${escapeAttr(key)}" ${key===openKey?'open':''}><summary>${escapeHtml(entry.label)} · ${escapeHtml(capabilityParameterPreview(key,spec,entry.value,entry.unset))}</summary><div class="agent-param-body"><strong>${escapeHtml(entry.label)}</strong>${entry.body}</div></details>`;
                }).join('')}</div>`;
            }

        }
        defaultsRoot.innerHTML = `<div class="agent-default-heading"><h3>${text('Agent 默认设置','Agent defaults')}</h3><span>${text('仅当前画布','This canvas')}</span></div><p>${text('先设好每类节点。Agent 会沿用这些设置；你明确指定时，只修改指定项。未设置的类型会提示先配置。','Set each node type once. Agents keep these defaults and override only explicitly requested fields. Unconfigured types require setup first.')}</p><div class="agent-default-tabs" role="tablist">${Object.entries(kindLabels()).map(([kind,label]) => `<button type="button" role="tab" aria-selected="${kind === defaultKind}" data-agent-kind="${kind}">${label}${defaultDraft[kind] ? ' ·' : ''}</button>`).join('')}</div>${editor}<div class="agent-default-actions"><button type="button" data-agent-save>${text('保存默认设置','Save defaults')}</button></div>`;
        defaultsRoot.querySelectorAll('.capability-option').forEach(option => option.setAttribute('aria-label',option.title || option.textContent.trim()));
        defaultsRoot.querySelectorAll('details').forEach(item => item.addEventListener('toggle',() => {
            if(!item.open) return;
            const body=item.querySelector('.agent-param-body');
            body.style.left='0px';
            const bounds=dialog.getBoundingClientRect();
            body.style.maxHeight=`${Math.max(80,Math.min(320,item.getBoundingClientRect().top-bounds.top-16))}px`;
            const rect=body.getBoundingClientRect();
            if(rect.right > bounds.right-20) body.style.left=`${bounds.right-20-rect.right}px`;
        }));
        refreshIcons();
    }
    function setDefaultValue(key,value){
        const current = defaultDraft[defaultKind];
        if(!current) return;
        if(fields[defaultKind]) current.parameters = {...current.parameters,[key]:value};
        else {
            const field=defaultKind==='app'?'rhParams':'comfyParams';
            current.run_settings[field]={...current.run_settings[field],[key]:value};
        }
        feedback.textContent = text('设置已修改，请保存。','Changes pending. Save defaults to apply.');
    }
    defaultsRoot.addEventListener('change', async e => {
        const select = e.target.closest('[data-agent-select]');
        if(!select) return;
        const current = defaultDraft[defaultKind] || {};
        let profile;
        const profiles = profilesFor(defaultKind);
        if(select.dataset.agentSelect === 'custom'){
            if(!select.value) delete defaultDraft[defaultKind];
            else if(defaultKind==='app') defaultDraft.app={run_settings:{rhAppId:select.value,rhConfigKey:runningHubEntryKey('app',select.value),rhParams:{}}};
            else {await ensureComfyWorkflow(select.value);defaultDraft.comfy={run_settings:{comfyWorkflow:select.value,comfyParams:{}}};}
            renderDefaultEditor();return;
        }
        if(select.dataset.agentSelect === 'provider'){
            profile = profiles.find(p=>p.provider_id===select.value);
            if(profile) defaultDraft[defaultKind] = {provider_id:select.value,model:profile.model_id,parameters:{}};
            else delete defaultDraft[defaultKind];
        } else {
            profile = profiles.find(p => p.provider_id === current.provider_id && (select.dataset.agentSelect === 'family' ? (p.family_id || p.model_id) === select.value : p.model_id === select.value));
            defaultDraft[defaultKind] = {provider_id:current.provider_id,model:profile?.model_id || '',parameters:{}};
        }
        renderDefaultEditor();
        feedback.textContent = text('设置已修改，请保存。','Changes pending. Save defaults to apply.');
    });
    defaultsRoot.addEventListener('input', e => {
        const control = e.target.closest('input[data-capability-param],textarea[data-capability-param]');
        if(!control) return;
        const spec = defaultProfile()?.parameters?.[control.dataset.capabilityParam];
        let value = capabilityInputValue(control);
        if(value === undefined) return;
        syncCapabilityNumericControls(control,value);
        if(value === '' && capabilityParameterIsOptional(spec)) value = CAPABILITY_PARAMETER_UNSET;
        setDefaultValue(control.dataset.capabilityParam,value);
        const summary=control.closest('details')?.querySelector('summary');
        if(summary) summary.textContent=capabilityParameterLabel(control.dataset.capabilityParam,spec,defaultProfile())+' · '+capabilityParameterPreview(control.dataset.capabilityParam,spec,value,false);
        const output = control.closest('.capability-range-field')?.querySelector('output');
        if(output) output.textContent = String(value);
    });
    defaultsRoot.addEventListener('click', async e => {
        const button = e.target.closest('button');
        const summary = e.target.closest('summary');
        if(summary){
            defaultsRoot.querySelectorAll('details[open]').forEach(item => {if(item !== summary.parentElement) item.open = false;});
            return;
        }
        if(!button) return;
        e.preventDefault(); e.stopPropagation();
        if(!button.closest('.agent-default-param')) defaultsRoot.querySelectorAll('details[open]').forEach(item=>item.open=false);
        if(button.dataset.agentKind){ defaultKind = button.dataset.agentKind; if(defaultKind==='comfy' && defaultDraft.comfy?.run_settings?.comfyWorkflow) await ensureComfyWorkflow(defaultDraft.comfy.run_settings.comfyWorkflow); renderDefaultEditor(); return; }
        if(button.hasAttribute('data-agent-save')){
            for(const [kind,value] of Object.entries(defaultDraft)){
                if(fields[kind] && !profilesFor(kind).some(p => p.provider_id === value.provider_id && p.model_id === value.model)){
                    feedback.textContent=text(`请先选好“${kindLabels()[kind]}”的模型。`,`Choose a model for ${kindLabels()[kind]}.`);return;
                }
            }
            button.disabled = true;
            try {
                canvasDefaultSmartSettings.agentDefaults = JSON.parse(JSON.stringify(defaultDraft));
                await persist();
                const saved = await api(`${endpoint()}/defaults`);
                if(JSON.stringify(saved.defaults) !== JSON.stringify(defaultDraft)) throw new Error(text('保存尚未确认，请重试。','Save is unconfirmed. Please try again.'));
                feedback.textContent=text('默认设置已保存，Agent 创建新节点时会自动使用。','Defaults saved. Agents will use them for new nodes.');
            } catch(error){feedback.textContent=error.message;}
            finally {button.disabled=false;}
            return;
        }
        const key = button.dataset.capabilityParam, profile = defaultProfile();
        if(!key || !profile) return;
        const spec = profile.parameters[key], current = defaultDraft[defaultKind];
        let value;
        if(button.hasAttribute('data-capability-unset')) value=CAPABILITY_PARAMETER_UNSET;
        else if(button.hasAttribute('data-capability-step')){
            const old=capabilityParameterValues(profile,{capabilityParameters:{[profile.model_id]:current.parameters || current.run_settings?.rhParams || current.run_settings?.comfyParams || {}}})[key];
            value=(Number(old) || 0)+Number(button.dataset.capabilityStep)*Number(button.dataset.capabilityDelta || 1);
            if(spec.min !== undefined) value=Math.max(spec.min,value);
            if(spec.max !== undefined) value=Math.min(spec.max,value);
        } else {
            const raw=button.dataset.capabilityValue;
            value=spec.type === 'boolean' ? raw === 'true' : ['integer','number'].includes(spec.type) ? Number(raw) : raw;
        }
        setDefaultValue(key,value); renderDefaultEditor(key);
    });
    dialog.addEventListener('click', e => {
        if(!e.target.closest('.agent-default-param')) defaultsRoot.querySelectorAll('details[open]').forEach(item => item.open=false);
    });
    const refreshLabels = () => {
        button.querySelector('span').textContent = text('Agent 接入','Agent');
        button.title = text('用 Codex 等 Agent 操作画布','Control the canvas with Codex or another agent');
        document.getElementById('canvasAgentHeading').textContent = text('让 Agent 帮你创作','Create with an agent');
        document.getElementById('canvasAgentSummary').textContent = text('复制下面的说明，发给新的 Codex 对话。让它读取接口后创建节点、填写内容、连接素材并运行。创作时保持此画布打开。连接说明会使用当前实际地址，支持启动器打开的本机局域网地址。','Copy these instructions into a new Codex conversation. It can create nodes, fill content, connect materials and run models. Keep this canvas open. Instructions use the current address, including this computer’s LAN address.');
        document.getElementById('canvasAgentCopy').textContent = text('复制连接说明','Copy instructions');
        document.getElementById('canvasAgentDocs').textContent = text('完整接口文档','API guide');
        document.getElementById('canvasAgentClose').ariaLabel = text('关闭','Close');
    };
    button.addEventListener('click', () => {
        refreshLabels();
        guide.value = text(`请阅读 ${location.origin}/api/agent/guide （项目文件 static/agent-guide.md），连接 ${location.origin} 的老胡无限画布。当前画布 ID：${canvasId}。先 GET /api/agent/canvases/${canvasId}/defaults 读取当前画布各类节点的默认模型和参数；未指明时沿用默认，明确指明时只覆盖对应字段，换模型时重新校验参数。再 GET /api/agent/capabilities、GET /api/model-capabilities 和 GET /api/canvases/${canvasId}，再按我的创作要求提交结构化命令。复用现有素材和模型白名单；运行前检查参数；保存 request_id 并查询原命令，超时不要重复生成。先创建和填写节点，只有我要求生成时才调用付费模型。请同时阅读指南中的“如何与 Agent 一起创作”和“创作进度表”章节，用普通话说明我可以怎样提出需求。常见流程是完整剧本→只读原文分段→图片与音频/音色资产→每段视频。分段到图片、音频和视频用 relation:"story" 虚线登记，虚线不作为模型输入；资产到视频的真实参考用普通实线。把每段实际节点登记到创作进度表；完整剧本说明讲背景、梗概和人物，分段说明才讲戏与衔接。创作说明使用自由 Markdown。后续按目标段读取上下文，不要求我重复所有历史聊天。`, `Read ${location.origin}/api/agent/guide (project file static/agent-guide.md) and connect to the Laohu Infinite Canvas at ${location.origin}. Current canvas ID: ${canvasId}. Read /api/agent/canvases/${canvasId}/defaults first. Use canvas defaults unless I explicitly override a field; validate parameters again when changing models. Read /api/agent/capabilities, /api/model-capabilities and /api/canvases/${canvasId} first. Create nodes and fill content according to my instructions. Use only enabled, compatible models. Save request_id and query the original command after timeouts; never repeat paid generation automatically. Run paid models only when I ask for generation. Also read the guide sections about working with agents and the production table, then explain in plain language how I can request work. Typical flow: full script, source-preserving segmentation, image and audio/voice assets, then segment videos. Use relation:"story" for dashed segment-to-asset/audio/video associations; these do not provide model inputs. Use normal input edges from reference assets to videos. Register actual nodes in the production table. Full-script notes cover background and synopsis; segment notes cover performance and continuity. Keep notes in free-form Markdown and read only the relevant segment context when continuing.`);
        defaultDraft = JSON.parse(JSON.stringify(canvasDefaultSmartSettings.agentDefaults || {}));
        feedback.textContent = "";
        document.getElementById("canvasAgentCopy").classList.remove("copy-success");
        document.getElementById("canvasAgentCopy").textContent=text("复制连接说明","Copy connection instructions");
        renderDefaultEditor();
        dialog.showModal();
        dialog.scrollTop=0;
    });
    document.getElementById('canvasAgentClose').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', e => { if(e.target === dialog) dialog.close(); });
    document.getElementById('canvasAgentCopy').addEventListener('click', async () => {
        const button=document.getElementById('canvasAgentCopy');
        try {
            await StudioMedia.writeText(guide.value);
            button.textContent=text('✓ 已复制，去粘贴','✓ Copied — ready to paste');
            button.classList.add('copy-success');
            feedback.textContent = text('连接说明已复制，可以粘贴到新的 Agent 对话中。','Instructions copied. Paste them into a new agent conversation.');
        } catch(error) { feedback.textContent = text('复制失败，请重试：','Copy failed. Please retry: ')+error.message; }
    });
    ['wheel','pointerdown','dblclick'].forEach(event => dialog.addEventListener(event, e => e.stopPropagation()));
    refreshLabels();
    window.addEventListener('canvas-capabilities-ready', () => { if(dialog.open) renderDefaultEditor(); });
    window.addEventListener('studio-lang-change', () => { refreshLabels(); if(dialog.open) renderDefaultEditor(); });
})();
