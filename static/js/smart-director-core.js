(function(root, factory){
    const api = factory();
    if(typeof module === 'object' && module.exports) module.exports = api;
    if(root) root.SmartDirectorCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
    'use strict';

    const SCHEMA_VERSION = 1;
    const CONNECTION_FRAME_THRESHOLD_MS = 1000;
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
                : {}
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

    function normalizeDirector(value){
        const source = value && typeof value === 'object' && !Array.isArray(value) ? clone(value) : {};
        const seenAssets = new Set();
        const assets = (Array.isArray(source.assets) ? source.assets : [])
            .map(normalizeAsset)
            .filter(asset => {
                if(seenAssets.has(asset.id)) return false;
                seenAssets.add(asset.id);
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
            .filter(item => item.startMs <= originalStartMs && overlaps(originalStartMs, originalEndMs, item.startMs, clipEndMs(item)))
            .sort((a, b) => clipEndMs(b) - clipEndMs(a))[0];
        const right = ordinary
            .filter(item => item.startMs > originalStartMs && overlaps(originalStartMs, originalEndMs, item.startMs, clipEndMs(item)))
            .sort((a, b) => a.startMs - b.startMs)[0];
        const inputs = [];
        let startMs = originalStartMs;
        let endMs = originalEndMs;

        if(left){
            const sourceEndMs = clipEndMs(left);
            const overlapMs = Math.max(0, Math.min(originalEndMs, sourceEndMs) - Math.max(originalStartMs, left.startMs));
            if(overlapMs > 0 && overlapMs < thresholdMs){
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
            if(overlapMs > 0 && overlapMs < thresholdMs){
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

    return Object.freeze({
        SCHEMA_VERSION,
        CONNECTION_FRAME_THRESHOLD_MS,
        NODE_TYPES,
        normalizeClip,
        normalizeDirector,
        clipEndMs,
        clipMidpoint,
        compareClipExportOrder,
        exportEntries,
        connectionClipConflict,
        deriveConnectionInputs
    });
});
