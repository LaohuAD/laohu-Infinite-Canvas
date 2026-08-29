(function(root, factory){
    const api = factory();
    if(typeof module === 'object' && module.exports) module.exports = api;
    if(root) root.SmartDirectorCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
    'use strict';

    const SCHEMA_VERSION = 1;
    const CONNECTION_FRAME_THRESHOLD_MS = 1000;
    const PARAMETER_UNSET = '__canvas_unset__';
    const NODE_TYPES = Object.freeze({
        generic:'smart-video-director',
        minimax:'smart-minimax-director',
        legacyMinimax:'smart-minimax'
    });

    function clone(value){
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function finiteNumber(value, fallback=0){
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function nonNegativeMs(value, fallback=0){
        return Math.max(0, Math.round(finiteNumber(value, fallback)));
    }

    function clipEndMs(clip){
        return nonNegativeMs(clip?.startMs) + Math.max(1, nonNegativeMs(clip?.durationMs, 5000));
    }

    function clipMidpoint(clip){
        return nonNegativeMs(clip?.startMs) + Math.max(1, nonNegativeMs(clip?.durationMs, 5000)) / 2;
    }

    function normalizeGeneration(value){
        const source = value && typeof value === 'object' && !Array.isArray(value) ? clone(value) : {};
        return {
            ...source,
            providerId:String(source.providerId || source.provider_id || ''),
            model:String(source.model || ''),
            mode:String(source.mode || source.executionMode || source.execution_mode || ''),
            params:source.params && typeof source.params === 'object' && !Array.isArray(source.params)
                ? clone(source.params)
                : {},
            parameterDrafts:source.parameterDrafts && typeof source.parameterDrafts === 'object' && !Array.isArray(source.parameterDrafts)
                ? clone(source.parameterDrafts)
                : {}
        };
    }

    function selectGenerationModel(value, modelId, operation=''){
        const generation = normalizeGeneration(value);
        const previousModel = String(generation.model || '').trim();
        const nextModel = String(modelId || '').trim();
        if(previousModel) generation.parameterDrafts[previousModel] = clone(generation.params || {});
        generation.model = nextModel;
        generation.mode = String(operation || '');
        generation.params = clone(generation.parameterDrafts[nextModel] || {});
        return generation;
    }

    // 导演台运行设置必须与普通视频节点的“最近设置”隔离，避免临时链接和模式状态串入 Clip。
    function isolatedVideoRunSettings(value){
        const source = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
        const modelId = String(source.modelId || '').trim();
        const rawParams = source.params && typeof source.params === 'object' && !Array.isArray(source.params)
            ? clone(source.params)
            : {};
        const submittedSource = source.submittedParams && typeof source.submittedParams === 'object' && !Array.isArray(source.submittedParams)
            ? source.submittedParams
            : {};
        const submittedParams = Object.fromEntries(Object.entries(submittedSource).filter(([, value]) => (
            value !== PARAMETER_UNSET && value !== undefined && value !== null && value !== ''
        )));
        const duration = Math.max(1, Math.round(finiteNumber(source.duration, 5)));
        const ratio = String(source.aspectRatio || '16:9');
        return {
            ...submittedParams,
            engine:'api',
            apiKind:'video',
            provider_id:'',
            model:'',
            videoProvider:String(source.providerId || ''),
            videoFamilyId:String(source.familyId || ''),
            videoModel:modelId,
            videoDuration:duration,
            videoAspect:ratio,
            videoResolution:'',
            videoUseFrameRoles:Boolean(source.useFrameRoles),
            videoTempShLinks:[],
            videoMultimodal:false,
            _videoMultimodalUserSet:false,
            videoTrustedAsset:false,
            videoTrustedSource:'library',
            capabilityParameters:modelId ? {[modelId]:rawParams} : {},
            _directorExecutionMode:String(source.mode || '')
        };
    }

    function normalizeClip(value, index=0){
        const source = value && typeof value === 'object' && !Array.isArray(value) ? clone(value) : {};
        const type = source.type === 'connection' ? 'connection' : 'ordinary';
        const results = Array.isArray(source.results) ? clone(source.results) : [];
        if(source.result && typeof source.result === 'object' && !results.length) results.push(clone(source.result));
        return {
            ...source,
            id:String(source.id || `clip-${String(index + 1).padStart(3, '0')}`),
            type,
            startMs:nonNegativeMs(source.startMs ?? source.start_ms),
            durationMs:Math.max(1, nonNegativeMs(source.durationMs ?? source.duration_ms, 5000)),
            createdAt:finiteNumber(source.createdAt ?? source.created_at, index),
            prompt:String(source.prompt || ''),
            inputRefs:Array.isArray(source.inputRefs) ? clone(source.inputRefs) : [],
            disabledInputRefs:Array.isArray(source.disabledInputRefs) ? clone(source.disabledInputRefs) : [],
            timelineInputs:Array.isArray(source.timelineInputs) ? clone(source.timelineInputs) : [],
            generation:normalizeGeneration(source.generation),
            results,
            currentResultId:String(source.currentResultId || source.current_result_id || '')
        };
    }

    function normalizeAsset(value, index=0){
        const source = value && typeof value === 'object' && !Array.isArray(value) ? clone(value) : {};
        return {
            ...source,
            id:String(source.id || `asset-${String(index + 1).padStart(3, '0')}`),
            kind:String(source.kind || source.mediaKind || source.type || 'file').toLowerCase()
        };
    }

    function assetKey(value){
        const source = value && typeof value === 'object' ? value : {};
        const url = String(source.url || source.path || source.src || source.uri || '').trim();
        if(url) return `url:${url}`;
        const text = String(source.text ?? source.content ?? '').trim();
        if(text) return `text:${text}`;
        return `id:${String(source.id || source.assetId || source.material_id || '')}`;
    }

    function normalizeDirector(value){
        const source = value && typeof value === 'object' && !Array.isArray(value) ? clone(value) : {};
        const seenAssets = new Set();
        const assets = (Array.isArray(source.assets) ? source.assets : [])
            .map(normalizeAsset)
            .filter(asset => {
                const key = assetKey(asset);
                if(seenAssets.has(key)) return false;
                seenAssets.add(key);
                return true;
            });
        const directorKind = source.directorKind === 'minimax-h3' ? 'minimax-h3' : 'generic';
        return {
            ...source,
            schemaVersion:SCHEMA_VERSION,
            directorKind,
            projectName:String(source.projectName || source.project_name || ''),
            assets,
            clips:(Array.isArray(source.clips) ? source.clips : []).map(normalizeClip),
            selectedClipId:String(source.selectedClipId || source.selected_clip_id || '')
        };
    }

    function registerProjectAssets(value, refs){
        const director = normalizeDirector(value);
        const byKey = new Map(director.assets.map(asset => [assetKey(asset), asset]));
        (Array.isArray(refs) ? refs : []).forEach((ref, index) => {
            const normalized = normalizeAsset(ref, director.assets.length + index);
            const key = assetKey(normalized);
            if(!key || key === 'id:') return;
            if(!byKey.has(key)) byKey.set(key, normalized);
        });
        director.assets = [...byKey.values()];
        return director;
    }

    function attachAssetsToClip(value, clipId, refs){
        let director = registerProjectAssets(value, refs);
        const clip = director.clips.find(item => item.id === clipId);
        if(!clip) return director;
        const projectByKey = new Map(director.assets.map(asset => [assetKey(asset), asset]));
        const clipByKey = new Map((clip.inputRefs || []).map(asset => [assetKey(asset), asset]));
        (Array.isArray(refs) ? refs : []).forEach(ref => {
            const registered = projectByKey.get(assetKey(ref));
            if(registered && !clipByKey.has(assetKey(registered))) clipByKey.set(assetKey(registered), clone(registered));
        });
        clip.inputRefs = [...clipByKey.values()];
        return director;
    }

    function referenceLabels(clip){
        const labels = {text:'文本', image:'图片', video:'视频', audio:'音频'};
        const order = ['text', 'image', 'video', 'audio'];
        const counters = {text:0, image:0, video:0, audio:0};
        return (Array.isArray(clip?.inputRefs) ? clip.inputRefs : [])
            .map((asset, index) => normalizeAsset(asset, index))
            .filter(asset => order.includes(asset.kind))
            .sort((left, right) => order.indexOf(left.kind) - order.indexOf(right.kind))
            .map(asset => {
                counters[asset.kind] += 1;
                return {
                    assetId:asset.id,
                    kind:asset.kind,
                    mention:`@${labels[asset.kind]}${counters[asset.kind]}`,
                    asset
                };
            });
    }

    function migrateLegacyMinimaxNode(value){
        if(!value || typeof value !== 'object') return value;
        if(value.type !== NODE_TYPES.legacyMinimax){
            if([NODE_TYPES.generic, NODE_TYPES.minimax].includes(value.type)) return normalizeDirector(value);
            return clone(value);
        }
        const source = clone(value);
        const allLegacyAssets = [
            ...(Array.isArray(source.materials) ? source.materials : []),
            ...['image', 'video', 'audio'].flatMap(kind => (Array.isArray(source.refs?.[kind]) ? source.refs[kind] : []).map(item => ({...item, kind}))),
            ...(Array.isArray(source.segments) ? source.segments : []).flatMap(segment => Array.isArray(segment?.refItems) ? segment.refItems : [])
        ];
        const assetByKey = new Map();
        allLegacyAssets.forEach((asset, index) => {
            const normalized = normalizeAsset({
                ...asset,
                id:asset?.id || asset?.assetId || asset?.material_id || `asset-${String(index + 1).padStart(3, '0')}`
            }, index);
            const key = String(normalized.id || normalized.url || normalized.path || '');
            if(key && !assetByKey.has(key)) assetByKey.set(key, normalized);
        });
        const clips = (Array.isArray(source.segments) ? source.segments : []).map((segment, index) => {
            const results = Array.isArray(segment?.results) ? clone(segment.results) : [];
            if(segment?.result?.url && !results.some(result => result?.id === segment.result.id || result?.url === segment.result.url)){
                results.push(clone(segment.result));
            }
            const current = segment?.result?.url
                ? segment.result
                : results.find(result => result?.url) || {};
            const inputRefs = (Array.isArray(segment?.refItems) ? segment.refItems : [])
                .map((item, refIndex) => normalizeAsset({
                    ...item,
                    id:item?.id || item?.assetId || item?.material_id || `clip-${index + 1}-asset-${refIndex + 1}`
                }, refIndex));
            return normalizeClip({
                id:segment?.id || `clip-${String(index + 1).padStart(3, '0')}`,
                type:'ordinary',
                startMs:Math.round(finiteNumber(segment?.start) * 1000),
                durationMs:Math.round(Math.max(0.5, finiteNumber(segment?.duration, source.duration || 8)) * 1000),
                createdAt:finiteNumber(segment?.createdAt ?? segment?.created_at, index),
                prompt:String(segment?.prompt || ''),
                inputRefs,
                generation:{
                    providerId:'',
                    model:'',
                    mode:'',
                    params:{
                        aspect_ratio:segment?.aspectRatio || source.aspectRatio || '16:9 (Widescreen)',
                        megapixels:finiteNumber(segment?.megapixels, source.megapixels || 0.4)
                    }
                },
                trimInMs:Math.round(finiteNumber(segment?.trimIn) * 1000),
                trimOutMs:Math.round(finiteNumber(segment?.trimOut, segment?.duration || source.duration || 8) * 1000),
                results,
                currentResultId:String(current?.id || '')
            }, index);
        });
        if(!clips.length){
            clips.push(normalizeClip({
                id:'clip-001',
                durationMs:Math.round(Math.max(0.5, finiteNumber(source.duration, 8)) * 1000)
            }, 0));
        }
        const {
            materials:unusedMaterials,
            refs:unusedRefs,
            segments:unusedSegments,
            selectedSegmentId:unusedSelectedSegmentId,
            minimaxEngine:unusedMinimaxEngine,
            minimaxRunningHubWorkflowId:unusedRunningHubWorkflowId,
            workflow:unusedWorkflow,
            duration:unusedDuration,
            aspectRatio:unusedAspectRatio,
            megapixels:unusedMegapixels,
            ...stableNode
        } = source;
        return normalizeDirector({
            ...stableNode,
            type:NODE_TYPES.minimax,
            title:source.title || 'MiniMax H3 导演台',
            directorKind:'minimax-h3',
            projectName:source.projectName || source.title || '',
            assets:[...assetByKey.values()],
            clips,
            selectedClipId:source.selectedSegmentId || clips[0].id,
            adapter:{
                kind:'minimax-h3',
                engine:String(source.minimaxEngine || 'comfyui'),
                workflow:String(source.workflow || 'MiniMax_H3.json'),
                runningHubWorkflowId:String(source.minimaxRunningHubWorkflowId || '')
            }
        });
    }

    function compareClipExportOrder(left, right){
        return (clipMidpoint(left) - clipMidpoint(right))
            || (nonNegativeMs(left?.startMs) - nonNegativeMs(right?.startMs))
            || (finiteNumber(left?.createdAt ?? left?.created_at) - finiteNumber(right?.createdAt ?? right?.created_at))
            || String(left?.id || '').localeCompare(String(right?.id || ''));
    }

    function resultForClip(clip){
        if(clip?.result && typeof clip.result === 'object') return clip.result;
        const results = Array.isArray(clip?.results) ? clip.results : [];
        const currentId = String(clip?.currentResultId || clip?.current_result_id || '');
        return results.find(result => String(result?.id || '') === currentId) || results.at(-1) || {};
    }

    function extensionForUrl(value){
        const clean = String(value || '').split('#')[0].split('?')[0];
        const match = clean.match(/\.([a-z0-9]{2,5})$/i);
        return match ? match[1].toLowerCase() : 'mp4';
    }

    function exportEntries(projectName, clips){
        const name = String(projectName || '未命名工程').trim() || '未命名工程';
        return (Array.isArray(clips) ? clips : [])
            .map(normalizeClip)
            .filter(clip => {
                const result = resultForClip(clip);
                return Boolean(result?.url || result?.path);
            })
            .sort(compareClipExportOrder)
            .map((clip, index) => {
                const result = resultForClip(clip);
                const url = String(result?.url || result?.path || '');
                return {
                    clipId:clip.id,
                    type:clip.type,
                    startMs:clip.startMs,
                    durationMs:clip.durationMs,
                    midpointMs:clipMidpoint(clip),
                    resultId:String(result?.id || clip.currentResultId || ''),
                    url,
                    filename:`${name}-clip-${String(index + 1).padStart(3, '0')}.${extensionForUrl(url)}`
                };
            });
    }

    function overlaps(leftStart, leftEnd, rightStart, rightEnd){
        return leftStart < rightEnd && rightStart < leftEnd;
    }

    function connectionClipConflict(candidate, clips){
        const startMs = nonNegativeMs(candidate?.startMs);
        const endMs = clipEndMs(candidate);
        const id = String(candidate?.id || '');
        const conflict = (Array.isArray(clips) ? clips : []).find(clip => {
            if(clip?.type !== 'connection' || String(clip?.id || '') === id) return false;
            return overlaps(startMs, endMs, nonNegativeMs(clip.startMs), clipEndMs(clip));
        });
        return String(conflict?.id || '');
    }

    function deriveConnectionInputs(connectionClip, ordinaryClips, thresholdMs=CONNECTION_FRAME_THRESHOLD_MS){
        const clip = normalizeClip({...connectionClip, type:'connection'});
        const originalStartMs = clip.startMs;
        const originalEndMs = clipEndMs(clip);
        const ordinary = (Array.isArray(ordinaryClips) ? ordinaryClips : [])
            .filter(item => item?.type !== 'connection')
            .map(normalizeClip)
            .sort((a, b) => a.startMs - b.startMs || a.id.localeCompare(b.id));
        const left = ordinary
            .filter(item => item.startMs <= originalStartMs && (overlaps(originalStartMs, originalEndMs, item.startMs, clipEndMs(item)) || clipEndMs(item) === originalStartMs))
            .sort((a, b) => clipEndMs(b) - clipEndMs(a))[0];
        const right = ordinary
            .filter(item => item.startMs > originalStartMs && (overlaps(originalStartMs, originalEndMs, item.startMs, clipEndMs(item)) || item.startMs === originalEndMs))
            .sort((a, b) => a.startMs - b.startMs)[0];
        const inputs = [];
        let startMs = originalStartMs;
        let endMs = originalEndMs;

        if(left){
            const sourceEndMs = clipEndMs(left);
            const overlapMs = Math.max(0, Math.min(originalEndMs, sourceEndMs) - Math.max(originalStartMs, left.startMs));
            if((overlapMs > 0 && overlapMs < thresholdMs) || (overlapMs === 0 && sourceEndMs === originalStartMs)){
                inputs.push({side:'left', sourceClipId:left.id, operation:'last_frame', atMs:sourceEndMs, overlapMs});
                startMs = sourceEndMs;
            }else if(overlapMs >= thresholdMs){
                inputs.push({
                    side:'left', sourceClipId:left.id, operation:'video_segment',
                    startMs:sourceEndMs - overlapMs, endMs:sourceEndMs, overlapMs
                });
            }
        }
        if(right){
            const sourceEndMs = clipEndMs(right);
            const overlapMs = Math.max(0, Math.min(originalEndMs, sourceEndMs) - Math.max(originalStartMs, right.startMs));
            if((overlapMs > 0 && overlapMs < thresholdMs) || (overlapMs === 0 && right.startMs === originalEndMs)){
                inputs.push({side:'right', sourceClipId:right.id, operation:'first_frame', atMs:right.startMs, overlapMs});
                endMs = right.startMs;
            }else if(overlapMs >= thresholdMs){
                inputs.push({
                    side:'right', sourceClipId:right.id, operation:'video_segment',
                    startMs:right.startMs, endMs:right.startMs + overlapMs, overlapMs
                });
            }
        }

        return {
            clipId:clip.id,
            originalStartMs,
            originalEndMs,
            startMs,
            endMs,
            durationMs:Math.max(1, endMs - startMs),
            inputs
        };
    }

    function connectionDependencyState(connectionClip, clips){
        const ordinary = (Array.isArray(clips) ? clips : []).filter(clip => clip?.type !== 'connection');
        const derived = deriveConnectionInputs(connectionClip, ordinary);
        const recorded = new Map((connectionClip?.timelineInputs || []).map(input => [
            `${input.side}:${input.sourceClipId}:${input.operation}`,
            input
        ]));
        const missing = [];
        const stale = [];
        derived.inputs.forEach(input => {
            const source = ordinary.find(clip => String(clip.id) === String(input.sourceClipId));
            const result = resultForClip(source);
            const currentResultId = String(result?.id || source?.currentResultId || result?.url || '');
            const previous = recorded.get(`${input.side}:${input.sourceClipId}:${input.operation}`) || {};
            if(!result?.url){
                missing.push({side:input.side, sourceClipId:input.sourceClipId});
                return;
            }
            if(connectionClip?.results?.length || connectionClip?.result?.url){
                if(!previous.sourceResultId || String(previous.sourceResultId) !== currentResultId){
                    stale.push({side:input.side, sourceClipId:input.sourceClipId, previousResultId:String(previous.sourceResultId || ''), currentResultId});
                }
            }
        });
        return {ready:derived.inputs.length > 0 && missing.length === 0, needsRegeneration:stale.length > 0, missing, stale, derived};
    }

    return Object.freeze({
        SCHEMA_VERSION,
        CONNECTION_FRAME_THRESHOLD_MS,
        PARAMETER_UNSET,
        NODE_TYPES,
        normalizeClip,
        normalizeDirector,
        selectGenerationModel,
        isolatedVideoRunSettings,
        assetKey,
        registerProjectAssets,
        attachAssetsToClip,
        referenceLabels,
        migrateLegacyMinimaxNode,
        clipEndMs,
        clipMidpoint,
        compareClipExportOrder,
        exportEntries,
        connectionClipConflict,
        deriveConnectionInputs,
        connectionDependencyState
    });
});
