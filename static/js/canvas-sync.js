/* 同一画布多标签同步：只处理可持久化数据，不依赖 DOM、网络或画布运行时。 */
(function(root, factory){
    const api = factory();
    if(typeof module === 'object' && module.exports) module.exports = api;
    if(root) root.CanvasSync = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
    'use strict';

    const MISSING = Symbol('canvas-sync-missing');
    const LOCAL_ONLY_KEYS = new Set(['viewport', 'selection', 'selectedId', 'selectedIds', 'selectedImage', 'playback']);
    const COLLECTION_FIELDS = new Set(['images', 'resultVersions', 'creationTasks', 'pendingTasks', 'tasks', 'logs']);

    function clone(value){
        if(value === MISSING) return MISSING;
        if(value === undefined || value === null) return value;
        try { return JSON.parse(JSON.stringify(value)); }
        catch(_) { return value; }
    }
    function has(object, key){ return Boolean(object && Object.prototype.hasOwnProperty.call(object, key)); }
    function isObject(value){ return Boolean(value && typeof value === 'object' && !Array.isArray(value)); }
    function canonical(value){
        if(value === MISSING) return '__canvas_sync_missing__';
        if(Array.isArray(value)) return value.map(canonical);
        if(isObject(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
        return value;
    }
    function equal(left, right){
        if(left === MISSING || right === MISSING) return left === right;
        return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
    }
    function positiveInteger(value, fallback=0){
        if(typeof value === 'boolean') return fallback;
        const number = Number(value);
        return Number.isInteger(number) && number > 0 ? number : fallback;
    }
    function pathFor(path, key){ return path ? `${path}.${key}` : String(key); }
    function conflict(conflicts, path, base, local, remote, kind='field'){
        conflicts.push({path, kind, base:clone(base), local:clone(local), remote:clone(remote)});
    }

    // 没有 id 的历史连线用内容生成可重复的键；有 id 的新连线始终优先使用真实 id。
    function shortHash(value){
        let hash = 2166136261;
        for(const char of String(value)){
            hash ^= char.charCodeAt(0);
            hash = Math.imul(hash, 16777619);
        }
        return (hash >>> 0).toString(36);
    }
    function connectionId(connection){
        if(connection?.id) return String(connection.id);
        const identity = {
            from:connection?.from || connection?.source || '',
            to:connection?.to || connection?.target || '',
            kind:connection?.kind || 'flow',
            sourceResultId:connection?.sourceResultId || connection?.source_result_id || '',
            sourceMediaKey:connection?.sourceMediaKey || connection?.source_media_key || '',
            sourceVersionId:connection?.sourceVersionId || connection?.source_version_id || '',
            targetFieldKey:connection?.targetFieldKey || connection?.target_field_key || ''
        };
        return `edge_${shortHash(JSON.stringify(canonical(identity)))}`;
    }
    function entityId(item, kind, index){
        if(kind === 'connection') return connectionId(item);
        if(item?.id !== undefined && item?.id !== null && String(item.id)) return String(item.id);
        if(item?.resultId || item?.result_id) return `result:${item.resultId || item.result_id}`;
        if(item?.taskId || item?.task_id) return `task:${item.taskId || item.task_id}`;
        if(item?.url) return `url:${item.url}`;
        return `index:${index}`;
    }
    function mapEntities(items, kind){
        const map = new Map();
        (Array.isArray(items) ? items : []).forEach((item, index) => {
            if(item === undefined || item === null) return;
            const key = entityId(item, kind, index);
            if(!map.has(key)) map.set(key, {item, index});
        });
        return map;
    }
    function collectionField(path){
        const key = String(path || '').split('.').pop();
        return COLLECTION_FIELDS.has(key);
    }
    function mergeArray(base, local, remote, path, conflicts){
        const values = [base, local, remote];
        if(values.some(value => value !== MISSING && !Array.isArray(value))) return mergeValue(base, local, remote, path, conflicts);
        if(equal(local, remote)) return clone(local);
        if(equal(local, base)) return clone(remote);
        if(equal(remote, base)) return clone(local);
        const all = [...(Array.isArray(local) ? local : []), ...(Array.isArray(remote) ? remote : []), ...(Array.isArray(base) ? base : [])];
        const entityLike = all.every(item => item === null || item === undefined || isObject(item))
            && all.some(item => item && (item.id || item.url || item.resultId || item.result_id || item.taskId || item.task_id));
        if(!entityLike){
            conflict(conflicts, path, base, local, remote);
            return clone(local);
        }
        const baseMap = mapEntities(base, 'item');
        const localMap = mapEntities(local, 'item');
        const remoteMap = mapEntities(remote, 'item');
        const order = [];
        const seen = new Set();
        [localMap, remoteMap, baseMap].forEach(map => map.forEach((_, key) => {
            if(!seen.has(key)){ seen.add(key); order.push(key); }
        }));
        const merged = [];
        order.forEach(key => {
            const baseItem = baseMap.get(key)?.item ?? MISSING;
            const localItem = localMap.get(key)?.item ?? MISSING;
            const remoteItem = remoteMap.get(key)?.item ?? MISSING;
            const value = mergeEntityValue(baseItem, localItem, remoteItem, `${path}.${key}`, conflicts);
            if(value !== MISSING) merged.push(value);
        });
        return merged;
    }
    function mergeObject(base, local, remote, path, conflicts){
        const result = {};
        const keys = new Set([
            ...(isObject(base) ? Object.keys(base) : []),
            ...(isObject(local) ? Object.keys(local) : []),
            ...(isObject(remote) ? Object.keys(remote) : [])
        ]);
        keys.forEach(key => {
            const value = mergeValue(
                isObject(base) && has(base, key) ? base[key] : MISSING,
                isObject(local) && has(local, key) ? local[key] : MISSING,
                isObject(remote) && has(remote, key) ? remote[key] : MISSING,
                pathFor(path, key),
                conflicts
            );
            if(value !== MISSING) result[key] = value;
        });
        return result;
    }
    function mergeEntityValue(base, local, remote, path, conflicts){
        const localPresent = local !== MISSING;
        const remotePresent = remote !== MISSING;
        const basePresent = base !== MISSING;
        if(!localPresent && !remotePresent) return MISSING;
        if(!basePresent){
            if(!localPresent) return clone(remote);
            if(!remotePresent) return clone(local);
            if(equal(local, remote)) return clone(local);
            if(isObject(local) && isObject(remote)) return mergeObject(MISSING, local, remote, path, conflicts);
            conflict(conflicts, path, MISSING, local, remote, 'new-vs-new');
            return clone(local);
        }
        if(!localPresent){
            if(equal(remote, base)) return MISSING;
            conflict(conflicts, path, base, MISSING, remote, 'delete-vs-edit');
            return MISSING;
        }
        if(!remotePresent){
            if(equal(local, base)) return MISSING;
            conflict(conflicts, path, base, local, MISSING, 'delete-vs-edit');
            return clone(local);
        }
        return mergeValue(base, local, remote, path, conflicts);
    }
    function mergeValue(base, local, remote, path, conflicts){
        if(equal(local, remote)) return clone(local);
        if(equal(local, base)) return clone(remote);
        if(equal(remote, base)) return clone(local);
        if(local !== MISSING && remote !== MISSING && isObject(local) && isObject(remote)){
            return mergeObject(isObject(base) ? base : MISSING, local, remote, path, conflicts);
        }
        if(local !== MISSING && remote !== MISSING && Array.isArray(local) && Array.isArray(remote)){
            return collectionField(path)
                ? mergeArray(base, local, remote, path, conflicts)
                : (conflict(conflicts, path, base, local, remote), clone(local));
        }
        const kind = local === MISSING || remote === MISSING ? 'delete-vs-edit' : 'field';
        conflict(conflicts, path, base, local, remote, kind);
        return clone(local);
    }
    function mergeEntities(baseItems, localItems, remoteItems, kind, path, conflicts){
        const baseMap = mapEntities(baseItems, kind);
        const localMap = mapEntities(localItems, kind);
        const remoteMap = mapEntities(remoteItems, kind);
        const order = [];
        const seen = new Set();
        [localMap, remoteMap, baseMap].forEach(map => map.forEach((_, key) => {
            if(!seen.has(key)){ seen.add(key); order.push(key); }
        }));
        const merged = [];
        order.forEach(key => {
            const baseItem = baseMap.get(key)?.item ?? MISSING;
            const localItem = localMap.get(key)?.item ?? MISSING;
            const remoteItem = remoteMap.get(key)?.item ?? MISSING;
            const itemPath = `${path}.${key}`;
            const value = mergeEntityValue(baseItem, localItem, remoteItem, itemPath, conflicts);
            if(value === MISSING) return;
            const normalized = clone(value);
            if(kind === 'connection' && isObject(normalized) && !normalized.id) normalized.id = connectionId(normalized);
            merged.push(normalized);
        });
        return merged;
    }
    function assignDisplayNumbers(canvas){
        const nextCanvas = clone(canvas || {});
        const list = Array.isArray(nextCanvas.nodes) ? nextCanvas.nodes : [];
        const used = new Set();
        let next = positiveInteger(nextCanvas.nextNodeNumber, 1);
        list.forEach(node => {
            const current = positiveInteger(node?.displayNumber, 0);
            if(current && !used.has(current)){
                node.displayNumber = current;
                used.add(current);
                next = Math.max(next, current + 1);
                return;
            }
            while(used.has(next)) next += 1;
            node.displayNumber = next;
            used.add(next);
            next += 1;
        });
        nextCanvas.nextNodeNumber = next;
        return nextCanvas;
    }
    function allocateDisplayNumber(canvas){
        if(!canvas || typeof canvas !== 'object') return 1;
        const used = new Set((Array.isArray(canvas.nodes) ? canvas.nodes : [])
            .map(node => positiveInteger(node?.displayNumber, 0)).filter(Boolean));
        let next = positiveInteger(canvas.nextNodeNumber, 1);
        while(used.has(next)) next += 1;
        canvas.nextNodeNumber = next + 1;
        return next;
    }
    function merge(baseCanvas={}, localCanvas={}, remoteCanvas={}){
        const base = isObject(baseCanvas) ? baseCanvas : {};
        const local = isObject(localCanvas) ? localCanvas : {};
        const remote = isObject(remoteCanvas) ? remoteCanvas : {};
        const conflicts = [];
        const merged = {};
        const special = new Set(['nodes', 'connections', 'settings', 'viewport', 'revision', 'updated_at', 'nextNodeNumber', 'id']);
        const keys = new Set([...Object.keys(base), ...Object.keys(local), ...Object.keys(remote)]);
        keys.forEach(key => {
            if(special.has(key) || LOCAL_ONLY_KEYS.has(key)) return;
            const value = mergeValue(
                has(base, key) ? base[key] : MISSING,
                has(local, key) ? local[key] : MISSING,
                has(remote, key) ? remote[key] : MISSING,
                key,
                conflicts
            );
            if(value !== MISSING) merged[key] = value;
        });
        merged.id = remote.id || local.id || base.id;
        merged.nodes = mergeEntities(base.nodes, local.nodes, remote.nodes, 'node', 'nodes', conflicts);
        merged.connections = mergeEntities(base.connections, local.connections, remote.connections, 'connection', 'connections', conflicts);
        const mergedNodeIds = new Set(merged.nodes.map(node => node?.id).filter(Boolean));
        merged.connections = merged.connections.filter(connection => (
            mergedNodeIds.has(connection?.from || connection?.source)
            && mergedNodeIds.has(connection?.to || connection?.target)
        ));
        merged.settings = mergeObject(
            isObject(base.settings) ? base.settings : {},
            isObject(local.settings) ? local.settings : {},
            isObject(remote.settings) ? remote.settings : {},
            'settings',
            conflicts
        );
        // 视口、选中状态、光标和播放态属于当前标签页，远端不能把用户正在看的位置改走。
        if(has(local, 'viewport')) merged.viewport = clone(local.viewport);
        else if(has(base, 'viewport')) merged.viewport = clone(base.viewport);
        else if(has(remote, 'viewport')) merged.viewport = clone(remote.viewport);
        if(has(remote, 'revision')) merged.revision = remote.revision;
        else if(has(local, 'revision')) merged.revision = local.revision;
        if(has(remote, 'updated_at')) merged.updated_at = remote.updated_at;
        else if(has(local, 'updated_at')) merged.updated_at = local.updated_at;
        const counters = [base.nextNodeNumber, local.nextNodeNumber, remote.nextNodeNumber]
            .map(value => positiveInteger(value, 1));
        const maxNodeNumber = merged.nodes.reduce((max, node) => Math.max(max, positiveInteger(node?.displayNumber, 0)), 0);
        merged.nextNodeNumber = Math.max(...counters, maxNodeNumber + 1);
        const numbered = assignDisplayNumbers(merged);
        return {canvas:numbered, conflicts};
    }
    return {clone, equal, connectionId, merge, assignDisplayNumbers, allocateDisplayNumber};
});
