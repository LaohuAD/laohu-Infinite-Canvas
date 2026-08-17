(function(root, factory){
    const api = factory();
    if(typeof module === 'object' && module.exports) module.exports = api;
    if(root) root.SmartModelCapabilities = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function(){
    'use strict';

    function providersForNodeType(catalog, nodeType){
        return (catalog?.providers || []).map(provider => ({
            ...provider,
            models:(provider.models || []).filter(model => model.node_type === nodeType)
        })).filter(provider => provider.models.length);
    }

    function mediaLimits(inputs){
        const limits = {};
        Object.values(inputs || {}).forEach(spec => {
            const mediaType = String(spec?.media_type || '').trim();
            if(!mediaType) return;
            const current = limits[mediaType] || {min:0, max:0};
            current.min += Math.max(0, Number(spec?.min) || 0);
            current.max += Math.max(0, spec?.max == null ? 1 : Number(spec.max) || 0);
            limits[mediaType] = current;
        });
        return limits;
    }

    function normalizeInputRole(value){
        const role = String(value || '').trim().toLowerCase().replace(/-/g, '_');
        return ({first:'first_frame',last:'last_frame',reference_image:'reference',image_reference:'reference',audio_reference:'reference_audio'})[role] || role;
    }

    function roleLimits(inputs){
        const limits = {};
        Object.entries(inputs || {}).forEach(([key, spec]) => {
            const role = normalizeInputRole(spec?.role || key);
            if(!role) return;
            const current = limits[role] || {min:0,max:0,media_type:String(spec?.media_type || '').trim()};
            current.min += Math.max(0, Number(spec?.min) || 0);
            current.max += Math.max(0, spec?.max == null ? 1 : Number(spec.max) || 0);
            limits[role] = current;
        });
        return limits;
    }

    function modelSupportsParameters(model, parameters={}){
        if(model?.validation_mode !== 'strict') return false;
        const specs = model.parameters || {};
        return Object.entries(parameters || {}).every(([key, value]) => {
            if(key === '__execution_mode') return true;
            if(value === undefined || value === null || value === '' || value === '__canvas_unset__') return true;
            const spec = specs[key];
            if(!spec) return false;
            const type = String(spec.type || '').toLowerCase();
            if(type === 'enum'){
                const options = Array.isArray(spec.options) ? spec.options.map(String) : [];
                return !options.length || options.includes(String(value));
            }
            if(type === 'integer' || type === 'number'){
                const numeric = Number(value);
                if(!Number.isFinite(numeric) || (type === 'integer' && !Number.isInteger(numeric))) return false;
                if(Number.isFinite(Number(spec.min)) && numeric < Number(spec.min)) return false;
                if(Number.isFinite(Number(spec.max)) && numeric > Number(spec.max)) return false;
            }
            if(type === 'boolean' && !['boolean','number','string'].includes(typeof value)) return false;
            return true;
        });
    }

    function modelExecutionMode(model){
        const operation = String(model?.operation || '').trim().toLowerCase().replace(/-/g, '_');
        return {
            text_to_video:'text2video',
            image_to_video:'image2video',
            multimodal_to_video:'multimodal2video',
            reference_to_video:'multimodal2video',
            compatible_video:'multimodal2video',
            start_end_to_video:'frames2video'
        }[operation] || '';
    }

    function modelSupportsExecutionMode(model, executionMode){
        const requested = String(executionMode || '').trim();
        if(!requested || model?.node_type !== 'video_generation') return true;
        const declared = modelExecutionMode(model);
        return !declared || declared === requested;
    }

    function modelSupportsInputs(model, inputCounts={}, inputRoles={}, parameters={}){
        if(model?.validation_mode !== 'strict') return false;
        if(model?.readiness && model.readiness !== 'ready') return false;
        if(model?.runnable === false) return false;
        if(!modelSupportsExecutionMode(model, parameters?.__execution_mode)) return false;
        if(!modelSupportsParameters(model, parameters)) return false;
        const limits = mediaLimits(model.inputs);
        for(const [mediaType, rawCount] of Object.entries(inputCounts || {})){
            const count = Math.max(0, Number(rawCount) || 0);
            const limit = limits[mediaType];
            if(count > 0 && !limit) return false;
            if(limit && count > limit.max) return false;
        }
        if(!Object.entries(limits).every(([mediaType, limit]) => (Number(inputCounts?.[mediaType]) || 0) >= limit.min)) return false;
        const normalizedRoles = {};
        Object.entries(inputRoles || {}).forEach(([rawRole, rawCount]) => {
            const role = normalizeInputRole(rawRole);
            const count = Math.max(0, Number(rawCount) || 0);
            if(role && count) normalizedRoles[role] = (normalizedRoles[role] || 0) + count;
        });
        if(!Object.keys(normalizedRoles).length) return true;
        const declaredRoles = roleLimits(model.inputs);
        const roleMediaCounts = {};
        for(const [role, count] of Object.entries(normalizedRoles)){
            const limit = declaredRoles[role];
            if(!limit){
                const genericMediaType = role === 'reference' ? 'image' : '';
                const hasAssignableRole = genericMediaType && Object.values(declaredRoles).some(item => item.media_type === genericMediaType);
                if(hasAssignableRole && count <= (Number(inputCounts?.[genericMediaType]) || 0)) continue;
                return false;
            }
            if(count > limit.max) return false;
            if(limit.media_type) roleMediaCounts[limit.media_type] = (roleMediaCounts[limit.media_type] || 0) + count;
        }
        const coveredMediaTypes = new Set(Object.keys(roleMediaCounts));
        if(!Object.entries(declaredRoles).every(([role, limit]) => !coveredMediaTypes.has(limit.media_type) || (normalizedRoles[role] || 0) >= limit.min)) return false;
        return Object.entries(roleMediaCounts).every(([mediaType, count]) => count <= (Number(inputCounts?.[mediaType]) || 0));
    }

    function modelsForInputs(catalog, nodeType, inputCounts={}, inputRoles={}, parameters={}){
        return providersForNodeType(catalog, nodeType).flatMap(provider =>
            provider.models.filter(model => modelSupportsInputs(model, inputCounts, inputRoles, parameters)).map(model => ({
                ...model,
                provider_id:provider.id,
                provider_name:provider.name,
                protocol:provider.protocol
            }))
        );
    }

    function modelsForVerifiedInputs(catalog, nodeType, inputCounts={}, inputRoles={}, parameters={}){
        return providersForNodeType(catalog, nodeType).flatMap(provider =>
            provider.models.filter(model => {
                if(model?.validation_mode !== 'strict') return false;
                return modelSupportsInputs(model, inputCounts, inputRoles, parameters);
            }).map(model => ({
                ...model,
                provider_id:provider.id,
                provider_name:provider.name,
                protocol:provider.protocol
            }))
        );
    }

    function compatibleFamilyVariants(family, inputCounts={}, inputRoles={}, parameters={}){
        return (family?.variants || []).filter(model => modelSupportsInputs(model, inputCounts, inputRoles, parameters));
    }

    function resolveFamilyVariant(family, inputCounts={}, operation='', inputRoles={}, parameters={}){
        const variants = compatibleFamilyVariants(family, inputCounts, inputRoles, parameters).filter(model => {
            if(!operation) return true;
            return model.operation === operation || model.variant_id === operation || model.model_id === operation;
        });
        if(variants.length === 1) return variants[0];
        if(!variants.length) return null;
        const exact = variants.filter(model => {
            const limits = mediaLimits(model.inputs);
            return ['text','image','video','audio'].every(mediaType => {
                const count = Number(inputCounts?.[mediaType]) || 0;
                const limit = limits[mediaType];
                return count === 0 ? !limit || limit.min === 0 : Boolean(limit && count >= limit.min && count <= limit.max);
            });
        });
        return exact.length === 1 ? exact[0] : null;
    }

    function familiesForInputs(catalog, nodeType, inputCounts={}, providerId='', operation='', inputRoles={}, parameters={}){
        return (catalog?.providers || []).filter(provider => !providerId || provider.id === providerId).flatMap(provider =>
            (provider.families || []).filter(family => family.node_type === nodeType).map(family => {
                const compatibleVariants = compatibleFamilyVariants(family, inputCounts, inputRoles, parameters);
                if(!compatibleVariants.length) return null;
                const resolved = resolveFamilyVariant(family, inputCounts, operation, inputRoles, parameters);
                return {
                    ...family,
                    provider_id:provider.id,
                    provider_name:provider.name,
                    protocol:provider.protocol,
                    compatible_variants:compatibleVariants,
                    resolved_variant:resolved
                };
            }).filter(Boolean)
        );
    }

    function familyForModel(provider, modelId, nodeType=''){
        return (provider?.families || []).find(family =>
            (!nodeType || family.node_type === nodeType) &&
            (family.variants || []).some(variant => variant.model_id === modelId)
        ) || null;
    }

    function findModel(catalog, providerId, modelId, nodeType=''){
        const provider = (catalog?.providers || []).find(item => item.id === providerId);
        return (provider?.models || []).find(model => model.model_id === modelId && (!nodeType || model.node_type === nodeType)) || null;
    }

    function effectiveParameters(profile, values={}){
        if(!profile || profile.validation_mode !== 'strict') return {...(values || {})};
        const specs = profile.parameters || {};
        const result = {};
        Object.entries(values || {}).forEach(([key, value]) => {
            const spec = specs[key];
            if(!spec || value === undefined || value === null || value === '') return;
            const type = String(spec.type || '').toLowerCase();
            if(type === 'enum'){
                const options = Array.isArray(spec.options) ? spec.options.map(String) : [];
                if(options.length && !options.includes(String(value))) return;
                result[key] = value;
                return;
            }
            if(type === 'integer' || type === 'number'){
                let numeric = Number(value);
                if(!Number.isFinite(numeric)) return;
                if(type === 'integer') numeric = Math.round(numeric);
                if(Number.isFinite(Number(spec.min))) numeric = Math.max(Number(spec.min), numeric);
                if(Number.isFinite(Number(spec.max))) numeric = Math.min(Number(spec.max), numeric);
                result[key] = numeric;
                return;
            }
            if(type === 'boolean'){
                result[key] = typeof value === 'boolean' ? value : ['true','1'].includes(String(value).toLowerCase());
                return;
            }
            result[key] = value;
        });
        return result;
    }

    function mediaAspectRatio(item){
        const width = Number(item?.natural_w || item?.naturalWidth || item?.width || item?.w || 0);
        const height = Number(item?.natural_h || item?.naturalHeight || item?.height || item?.h || 0);
        return width > 0 && height > 0 ? width / height : 0;
    }

    function requestedAspectRatio(value){
        const parts = String(value || '').trim().split(':').map(Number);
        return parts.length === 2 && parts[0] > 0 && parts[1] > 0 ? parts[0] / parts[1] : 0;
    }

    function resolveVideoExecutionMode(options={}){
        const imageRefs = Array.isArray(options.imageRefs) ? options.imageRefs.filter(Boolean) : [];
        const videoCount = Math.max(0, Number(options.videoCount) || 0);
        const audioCount = Math.max(0, Number(options.audioCount) || 0);
        if(options.useFrameRoles && imageRefs.length === 2 && !videoCount && !audioCount) return 'frames2video';
        if(options.forceMultimodal || videoCount || audioCount || imageRefs.length > 1) return 'multimodal2video';
        if(imageRefs.length === 1){
            const desiredRatio = requestedAspectRatio(options.parameters?.aspect_ratio);
            if(desiredRatio){
                const sourceRatio = mediaAspectRatio(imageRefs[0]);
                if(!sourceRatio || Math.abs(sourceRatio - desiredRatio) / desiredRatio > 0.01) return 'multimodal2video';
            }
            return 'image2video';
        }
        return 'text2video';
    }

    function capabilitySnapshot(profile, inputCounts={}, values={}){
        const sourceValues = values && typeof values === 'object' ? values : {};
        const effective = effectiveParameters(profile, sourceValues);
        const omitted = {};
        if(profile?.validation_mode === 'strict'){
            Object.entries(sourceValues).forEach(([key, value]) => {
                if(value === undefined || value === null || value === '') return;
                if(!Object.prototype.hasOwnProperty.call(effective, key)) omitted[key] = value;
            });
        }
        return {
            provider_id:profile?.provider_id || '',
            capability_provider_id:profile?.capability_provider_id || '',
            family_id:profile?.family_id || profile?.model_id || '',
            variant_id:profile?.variant_id || profile?.operation || '',
            model_id:profile?.model_id || '',
            node_type:profile?.node_type || '',
            operation:profile?.operation || '',
            profile_version:profile?.version ?? 0,
            validation_mode:profile?.validation_mode || 'compatible',
            evidence_level:profile?.evidence_level || '',
            input_counts:{...(inputCounts || {})},
            effective_parameters:effective,
            omitted_parameters:omitted,
            request_mapping:{...(profile?.request_mapping || {})}
        };
    }

    function compactRequest(values={}){
        return Object.fromEntries(Object.entries(values || {}).filter(([, value]) => value !== undefined));
    }

    function buildVideoRequest(profile, base={}, values={}){
        const effective = effectiveParameters(profile, values);
        const strict = profile?.validation_mode === 'strict';
        return compactRequest({
            ...(base || {}),
            duration:effective.duration ?? (strict ? undefined : 5),
            aspect_ratio:effective.aspect_ratio ?? (strict ? undefined : ''),
            resolution:effective.resolution ?? (strict ? undefined : ''),
            generate_audio:effective.generate_audio ?? (strict ? undefined : false),
            return_last_frame:effective.return_last_frame,
            seed:effective.seed,
            enhance_prompt:strict ? undefined : Boolean(effective.enhance_prompt),
            enable_upsample:strict ? undefined : Boolean(effective.enable_upsample),
            watermark:strict ? undefined : Boolean(effective.watermark),
            camerafixed:strict ? undefined : Boolean(effective.camerafixed),
            multimodal:base.multimodal !== undefined ? Boolean(base.multimodal) : (strict ? undefined : Boolean(effective.multimodal))
        });
    }

    function buildAudioRequest(profile, base={}, values={}){
        const effective = effectiveParameters(profile, values);
        const strict = profile?.validation_mode === 'strict';
        return compactRequest({
            ...(base || {}),
            speaker:effective.speaker ?? (strict ? undefined : ''),
            audio_format:effective.format ?? (strict ? undefined : 'mp3'),
            sample_rate:effective.sample_rate ?? (strict ? undefined : 24000),
            speech_rate:effective.speech_rate ?? (strict ? undefined : 0),
            loudness_rate:effective.loudness_rate ?? (strict ? undefined : 0),
            pitch_rate:effective.pitch_rate ?? (strict ? undefined : 0)
        });
    }

    return Object.freeze({
        providersForNodeType,
        mediaLimits,
        normalizeInputRole,
        roleLimits,
        modelSupportsParameters,
        modelExecutionMode,
        modelSupportsExecutionMode,
        modelSupportsInputs,
        modelsForInputs,
        modelsForVerifiedInputs,
        compatibleFamilyVariants,
        resolveFamilyVariant,
        familiesForInputs,
        familyForModel,
        findModel,
        effectiveParameters,
        resolveVideoExecutionMode,
        capabilitySnapshot,
        buildVideoRequest,
        buildAudioRequest
    });
});
