(function () {
    'use strict';

    const SLOTS = ['text', 'image', 'video', 'audio', 'voice'];
    const NODE_TYPES = {
        text: 'text_generation',
        image: 'image_generation',
        video: 'video_generation',
        audio: 'audio_generation',
        voice: 'audio_generation'
    };
    const SLOT_LABELS = {
        text: 'hypit.slotText',
        image: 'hypit.slotImage',
        video: 'hypit.slotVideo',
        audio: 'hypit.slotAudio',
        voice: 'hypit.slotVoice'
    };
    const API = '/api/studio/hypit/models';
    const projectId = new URLSearchParams(location.search).get('hypit_project');
    const settingsURL = projectId ? `${API}/projects/${encodeURIComponent(projectId)}/binding` : `${API}/settings`;
    const root = document.getElementById('providerSettingsView');
    const layout = document.querySelector('.layout');
    const block = document.getElementById('hypitSettingsBlock');
    const nav = document.getElementById('hypitSettingsNav');
    const slotsEl = document.getElementById('hypitSlots');
    const summaryEl = document.getElementById('hypitCapabilitySummary');
    const statusEl = document.getElementById('hypitSettingsStatus');
    const state = {
        catalog: { providers: [] },
        capabilities: [],
        unsupported: [],
        settings: { defaults: {} },
        loaded: false,
        loading: false,
        saving: false
    };

    const translations = {
        zh: {
            'hypit.navTitle': 'Hypit 设置',
            'hypit.navLabel': 'Hypit',
            'hypit.navMeta': '绑定工作台共享模型',
            'hypit.title': 'Hypit 设置',
            'hypit.description': '为 Hypit 项目选择工作台共享模型。这里不保存 API Key，项目首次接入时会固定一份默认模型快照。',
            'hypit.back': '返回平台设置',
            'hypit.noKeys': 'Hypit 使用工作台后端执行；外部平台 Key 只由后端读取，不会写入 Hypit 设置或 Endpoint 配置。',
            'hypit.reload': '重新读取',
            'hypit.save': '保存 Hypit 默认模型',
            'hypit.slotText': '文本生成',
            'hypit.slotImage': '图片生成',
            'hypit.slotVideo': '视频生成',
            'hypit.slotAudio': '音频生成',
            'hypit.slotVoice': '语音生成',
            'hypit.slotTextHint': 'Hypit Text 输入映射到工作台文本生成。',
            'hypit.slotImageHint': '只显示当前用户已启用且有确认适配的图片模型。',
            'hypit.slotVideoHint': '只显示当前用户已启用且有确认适配的视频模型。',
            'hypit.slotAudioHint': '音频生成用于音效或其他非音乐音频输出。',
            'hypit.slotVoiceHint': '语音生成独立使用语音槽位，不把音乐模型当作语音。',
            'hypit.family': '模型',
            'hypit.variant': '模式',
            'hypit.provider': '平台',
            'hypit.parameters': '参数',
            'hypit.noModels': '当前用户启用白名单中没有可运行模型。请先在平台设置中启用模型。',
            'hypit.noCatalog': '暂时无法读取模型能力目录。',
            'hypit.unavailable': '未接入',
            'hypit.modelsCount': '{count} 个可用模型',
            'hypit.selectedUnavailable': '当前默认模型不在此能力的已确认候选中；不会自动替换。',
            'hypit.loading': '正在读取 Hypit 模型设置…',
            'hypit.saving': '正在保存…',
            'hypit.saved': 'Hypit 默认模型已保存。',
            'hypit.loaded': '已读取 Hypit 模型目录与默认设置。',
            'hypit.loadError': '读取 Hypit 设置失败：{message}',
            'hypit.saveError': '保存 Hypit 设置失败：{message}',
            'hypit.noImplementation': '当前桥接未实现此能力。'
        },
        en: {
            'hypit.navTitle': 'Hypit settings',
            'hypit.navLabel': 'Hypit',
            'hypit.navMeta': 'Bind shared Studio models',
            'hypit.title': 'Hypit settings',
            'hypit.description': 'Choose the shared workbench model for Hypit. API keys are not stored here; the first project binding keeps a default-model snapshot.',
            'hypit.back': 'Back to platform settings',
            'hypit.noKeys': 'Hypit executes through the workbench backend. External platform keys are read only by the backend and never written to Hypit settings or the Endpoint config.',
            'hypit.reload': 'Reload',
            'hypit.save': 'Save Hypit defaults',
            'hypit.slotText': 'Text generation',
            'hypit.slotImage': 'Image generation',
            'hypit.slotVideo': 'Video generation',
            'hypit.slotAudio': 'Audio generation',
            'hypit.slotVoice': 'Speech generation',
            'hypit.slotTextHint': 'Hypit Text input is mapped to the workbench text generator.',
            'hypit.slotImageHint': 'Only enabled image models with a confirmed adapter are shown.',
            'hypit.slotVideoHint': 'Only enabled video models with a confirmed adapter are shown.',
            'hypit.slotAudioHint': 'Audio generation is for effects and non-music audio output.',
            'hypit.slotVoiceHint': 'Speech has its own slot; music models are never treated as speech.',
            'hypit.family': 'Model',
            'hypit.variant': 'Variant',
            'hypit.provider': 'Platform',
            'hypit.parameters': 'Parameters',
            'hypit.noModels': 'No runnable model is enabled for this capability. Enable one in platform settings first.',
            'hypit.noCatalog': 'The model capability catalog is temporarily unavailable.',
            'hypit.unavailable': 'Not implemented',
            'hypit.modelsCount': '{count} available model(s)',
            'hypit.selectedUnavailable': 'The current default is not a confirmed candidate for this capability; it will not be replaced automatically.',
            'hypit.loading': 'Loading Hypit model settings…',
            'hypit.saving': 'Saving…',
            'hypit.saved': 'Hypit defaults saved.',
            'hypit.loaded': 'Hypit catalog and defaults loaded.',
            'hypit.loadError': 'Could not load Hypit settings: {message}',
            'hypit.saveError': 'Could not save Hypit settings: {message}',
            'hypit.noImplementation': 'This capability is not implemented by the bridge.'
        }
    };

    function registerTranslations() {
        if (window.StudioI18n) window.StudioI18n.register(translations);
    }

    function t(key, values) {
        const base = window.StudioI18n ? window.StudioI18n.t(key) : (translations.zh[key] || key);
        return String(base).replace(/\{(\w+)\}/g, (_, name) => values && values[name] !== undefined ? String(values[name]) : `{${name}}`);
    }

    function currentLang() {
        return window.StudioI18n?.lang?.() === 'en' ? 'en' : 'zh';
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>'"]/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        }[char]));
    }

    function setStatus(message, stateName = '') {
        if (!statusEl) return;
        statusEl.textContent = message || '';
        if (stateName) statusEl.dataset.state = stateName;
        else delete statusEl.dataset.state;
    }

    function refreshIcons() {
        if (typeof window.refreshIcons === 'function') window.refreshIcons();
        else if (window.lucide?.createIcons) window.lucide.createIcons();
    }

    function syncEditorHeader() {
        const title = document.getElementById('editorTitle');
        if (title && layout?.classList.contains('hypit-settings-mode')) title.textContent = t('hypit.title');
    }

    function emptySlot() {
        return { provider: '', model: '', parameters: {} };
    }

    function ensureDefaults() {
        if (!state.settings || typeof state.settings !== 'object') state.settings = { defaults: {} };
        if (!state.settings.defaults || typeof state.settings.defaults !== 'object') state.settings.defaults = {};
        SLOTS.forEach(slot => {
            const value = state.settings.defaults[slot];
            if (!value || typeof value !== 'object') state.settings.defaults[slot] = emptySlot();
            if (!state.settings.defaults[slot].parameters || typeof state.settings.defaults[slot].parameters !== 'object') {
                state.settings.defaults[slot].parameters = {};
            }
        });
    }

    function capabilityFor(slot) {
        return state.capabilities.find(item => item.slot === slot) || null;
    }

    function enabledModels(slot) {
        const capability = capabilityFor(slot);
        if (Array.isArray(capability?.models)) return capability.models.filter(model => model && model.model_id && model.runnable === true && model.validation_mode === 'strict');
        const nodeType = NODE_TYPES[slot];
        return (state.catalog.providers || []).flatMap(provider => (provider.models || [])
            .filter(model => model.node_type === nodeType && model.runnable === true && model.validation_mode === 'strict')
            .map(model => ({
                ...model,
                provider_id: provider.id,
                provider_name: provider.name || provider.id
            })));
    }

    function modelKey(model) {
        return `${String(model?.provider_id || '')}::${String(model?.model_id || '')}`;
    }

    function exactProfile(slot, providerId, modelId) {
        const direct = enabledModels(slot).find(item => item.provider_id === providerId && item.model_id === modelId);
        if (direct) return direct;
        const helper = window.SmartModelCapabilities;
        return helper?.findModel?.(state.catalog, providerId, modelId, NODE_TYPES[slot]) || null;
    }

    function candidateFamilies(slot) {
        const models = enabledModels(slot);
        const allowed = new Set(models.map(modelKey));
        const helper = window.SmartModelCapabilities;
        const providerIds = [...new Set(models.map(model => String(model.provider_id || '')).filter(Boolean))];
        const families = helper?.familiesAcrossProviders?.(
            state.catalog,
            NODE_TYPES[slot],
            { text: 1 },
            providerIds,
            '',
            {},
            {}
        ) || [];
        const output = families.map(family => ({
            ...family,
            variants: (family.compatible_variants || family.variants || []).filter(model => allowed.has(modelKey(model)))
        })).filter(family => family.variants.length);
        const covered = new Set(output.flatMap(family => family.variants.map(modelKey)));
        // 能力目录可能没有 family 资料；此时仍按精确 family_id/model_id 展示，
        // 但不通过显示名猜测跨平台等价关系。
        models.forEach(model => {
            if (covered.has(modelKey(model))) return;
            const familyId = String(model.family_id || model.model_id);
            let family = output.find(item => item.family_id === familyId && item.provider_ids?.includes(model.provider_id));
            if (!family) {
                family = {
                    family_id: familyId,
                    family_name: model.family_name || model.display_name || familyId,
                    provider_ids: [model.provider_id],
                    providers: [{ id: model.provider_id, name: model.provider_name || model.provider_id }],
                    variants: []
                };
                output.push(family);
            }
            family.variants.push(model);
        });
        return output;
    }

    function familyLabel(family) {
        const name = currentLang() === 'en'
            ? (family.family_name_en || family.display_name_en || family.family_name || family.display_name)
            : (family.family_name || family.display_name || family.family_name_en || family.display_name_en);
        return String(name || family.family_id || '—');
    }

    function variantLabel(model) {
        const name = currentLang() === 'en'
            ? (model.variant_name_en || model.variant_name || model.display_name_en || model.display_name)
            : (model.variant_name || model.display_name || model.variant_name_en || model.display_name_en);
        const modelId = String(model.model_id || model.variant_id || '').trim();
        const display = String(name || '').trim();
        return display && display !== modelId ? `${display} · ${modelId}` : (modelId || display || '—');
    }

    function statusFor(slot, model) {
        if (!model) return { text: t('hypit.unavailable'), className: 'is-warning' };
        if (model.runnable === false || (model.readiness && model.readiness !== 'ready') || model.validation_mode !== 'strict') {
            return { text: model.readiness || t('hypit.unavailable'), className: 'is-warning' };
        }
        return { text: currentLang() === 'en' ? 'Ready' : '可运行', className: 'is-ready' };
    }

    function optionsHtml(items, selected, labeler, valueKey) {
        return items.map(item => {
            const value = String(item[valueKey] ?? '');
            return `<option value="${escapeHtml(value)}"${value === String(selected ?? '') ? ' selected' : ''}>${escapeHtml(labeler(item))}</option>`;
        }).join('');
    }

    function parameterInput(slot, key, spec, value) {
        const type = String(spec?.type || '').toLowerCase();
        const labels = {duration:['时长','Duration'], resolution:['分辨率','Resolution'],aspect_ratio:['画幅','Ratio'],quality:['画质','Quality'],voice_id:['音色','Voice'],speed:['语速','Speed'],volume:['音量','Volume'],pitch:['音高','Pitch']};
        const label = labels[key]?.[currentLang() === 'en' ? 1 : 0] || spec?.label || key;
        let choices = Array.isArray(spec?.options || spec?.values) ? spec.options || spec.values : null;
        if(type === 'boolean' || type === 'bool') choices=[true,false];
        const lower=spec?.min ?? spec?.minimum, upper=spec?.max ?? spec?.maximum;
        if(!choices && type==='integer' && Number.isInteger(lower) && Number.isInteger(upper) && upper-lower<=100) choices=Array.from({length:upper-lower+1},(_,i)=>lower+i);
        if(choices) return `<div class="hypit-parameter-field"><span class="hypit-parameter-label">${escapeHtml(label)}</span><div class="hypit-choices">${[undefined,...choices].map(option=>`<button type="button" class="${option===value?'active':''}" data-hypit-choice="${escapeHtml(key)}" data-hypit-slot="${escapeHtml(slot)}" data-value="${escapeHtml(option===undefined?'':JSON.stringify(option))}">${escapeHtml(option===undefined?(currentLang()==='en'?'Default':'默认'):option===true?(currentLang()==='en'?'Yes':'是'):option===false?(currentLang()==='en'?'No':'否'):option)}</button>`).join('')}</div></div>`;
        if (type === 'boolean' || type === 'bool') {
            return `<label class="hypit-parameter-checkbox"><input type="checkbox" data-hypit-parameter="${escapeHtml(key)}" data-hypit-slot="${escapeHtml(slot)}"${value === true ? ' checked' : ''}><span>${escapeHtml(label)}</span></label>`;
        }
        if (type === 'enum' && Array.isArray(spec?.options || spec?.values)) {
            const values = spec.options || spec.values;
            return `<label class="hypit-parameter-field"><span class="hypit-parameter-label">${escapeHtml(label)}</span><select data-hypit-parameter="${escapeHtml(key)}" data-hypit-slot="${escapeHtml(slot)}">${values.map(option => `<option value="${escapeHtml(option)}"${String(option) === String(value ?? '') ? ' selected' : ''}>${escapeHtml(option)}</option>`).join('')}</select></label>`;
        }
        const numeric = type === 'integer' || type === 'number' || type === 'float';
        const min = spec?.min ?? spec?.minimum;
        const max = spec?.max ?? spec?.maximum;
        return `<label class="hypit-parameter-field"><span class="hypit-parameter-label">${escapeHtml(label)}</span><input type="${numeric ? 'number' : 'text'}"${numeric && type === 'integer' ? ' step="1"' : ''}${min !== undefined ? ` min="${escapeHtml(min)}"` : ''}${max !== undefined ? ` max="${escapeHtml(max)}"` : ''} value="${escapeHtml(value ?? '')}" data-hypit-parameter="${escapeHtml(key)}" data-hypit-slot="${escapeHtml(slot)}"></label>`;
    }

    function renderParameters(slot, profile) {
        const schema = profile?.parameters && typeof profile.parameters === 'object' ? profile.parameters : {};
        const keys = Object.keys(schema);
        if (!keys.length) return '';
        const values = state.settings.defaults[slot].parameters || {};
        return `<div class="hypit-parameters"><div class="hypit-parameters-title">${escapeHtml(t('hypit.parameters'))}</div>${keys.map(key => parameterInput(slot, key, schema[key], values[key])).join('')}</div>`;
    }

    function syncSelection(slot, card) {
        const familySelect = card.querySelector('[data-hypit-family]');
        const variantSelect = card.querySelector('[data-hypit-variant]');
        const providerSelect = card.querySelector('[data-hypit-provider]');
        const familyId = familySelect?.value || '';
        const family = candidateFamilies(slot).find(item => String(item.family_id) === familyId);
        const variants = family?.variants || [];
        const selectedVariant = variants.find(item => String(item.model_id) === String(variantSelect?.value || '')) || variants[0];
        const providerId = providerSelect?.value || selectedVariant?.provider_id || '';
        const model = variants.find(item => item.provider_id === providerId && item.model_id === selectedVariant?.model_id) || selectedVariant;
        if (!model) return;
        const current = state.settings.defaults[slot];
        const helper = window.SmartModelCapabilities;
        const retained = current.provider === model.provider_id && current.model === model.model_id ? current.parameters || {} : {};
        const parameters = helper?.effectiveParameters?.(model, retained) || retained;
        state.settings.defaults[slot] = { provider: model.provider_id || '', model: model.model_id || '', parameters };
    }

    function renderSlot(slot) {
        const capability = capabilityFor(slot);
        const models = enabledModels(slot);
        const families = candidateFamilies(slot);
        const current = state.settings.defaults[slot] || emptySlot();
        const selectedModel = models.find(model => model.provider_id === current.provider && model.model_id === current.model) || null;
        const selectedFamily = families.find(family => family.variants.some(model => modelKey(model) === modelKey(selectedModel)));
        const variants = selectedFamily?.variants || [];
        const selectedVariant = variants.find(model => model.provider_id === current.provider && model.model_id === current.model) || variants[0];
        const providers = variants.filter((item, index, list) => list.findIndex(other => other.provider_id === item.provider_id) === index);
        const selectedProvider = providers.find(item => item.provider_id === current.provider) || selectedVariant;
        const activeModel = variants.find(item => item.provider_id === selectedProvider?.provider_id && item.model_id === selectedVariant?.model_id) || selectedVariant;
        const status = current.model ? statusFor(slot, selectedModel) : {text:currentLang() === 'en' ? 'Not set' : '未设置',className:''};
        const unavailable = Boolean(current.provider && current.model && !selectedModel);
        const familyOptions = `<option value="">${currentLang() === 'en' ? 'Choose' : '选择'}</option>` + families.map(item => `<option value="${escapeHtml(item.family_id)}"${item === selectedFamily ? ' selected' : ''}>${escapeHtml(familyLabel(item))}</option>`).join('');
        const variantOptions = optionsHtml(variants, selectedVariant?.model_id, variantLabel, 'model_id');
        const providerOptions = providers.map(item => `<option value="${escapeHtml(item.provider_id)}"${item.provider_id === (selectedProvider?.provider_id || '') ? ' selected' : ''}>${escapeHtml(item.provider_name || item.provider_id)}</option>`).join('');
        const title = t(SLOT_LABELS[slot]);
        const hint = t(`hypit.slot${slot.charAt(0).toUpperCase()}${slot.slice(1)}Hint`);
        const modelNote = unavailable ? `<div class="hypit-slot-description">${escapeHtml(t('hypit.selectedUnavailable'))}<br><code>${escapeHtml(current.provider)} / ${escapeHtml(current.model)}</code></div>` : '';
        if (!models.length || !families.length) {
            return `<section class="hypit-slot-card is-disabled" data-hypit-slot-card="${escapeHtml(slot)}"><div class="hypit-slot-head"><div><div class="hypit-slot-title">${escapeHtml(title)}</div><div class="hypit-slot-description">${escapeHtml(hint)}</div></div><span class="hypit-slot-status is-warning">${escapeHtml(t('hypit.unavailable'))}</span></div><div class="hypit-empty">${escapeHtml(t('hypit.noModels'))}${modelNote}</div></section>`;
        }
        return `<section class="hypit-slot-card" data-hypit-slot-card="${escapeHtml(slot)}"><div class="hypit-slot-head"><div><div class="hypit-slot-title">${escapeHtml(title)}</div><div class="hypit-slot-description">${escapeHtml(hint)}</div></div><span class="hypit-slot-status ${status.className}">${escapeHtml(status.text)}</span></div><div class="hypit-model-fields"><label class="hypit-field"><span class="hypit-field-label">${escapeHtml(t('hypit.family'))}</span><select data-hypit-family data-hypit-slot="${escapeHtml(slot)}">${familyOptions}</select></label><label class="hypit-field"><span class="hypit-field-label">${escapeHtml(t('hypit.variant'))}</span><select data-hypit-variant data-hypit-slot="${escapeHtml(slot)}">${variantOptions}</select></label><label class="hypit-field"><span class="hypit-field-label">${escapeHtml(t('hypit.provider'))}</span><select data-hypit-provider data-hypit-slot="${escapeHtml(slot)}">${providerOptions}</select></label></div>${modelNote}${renderParameters(slot, activeModel)}</section>`;
    }

    function renderSummary() {
        const supported = state.capabilities || [];
        const chips = supported.map(item => {
            const models = Array.isArray(item.models) ? item.models.filter(m=>m.runnable === true && m.validation_mode === 'strict') : [];
            const label = item.label?.[currentLang()] || item.label?.zh || item.kind || item.slot;
            return `<div class="hypit-capability-chip${models.length ? '' : ' is-unavailable'}"><div class="hypit-capability-chip-title">${escapeHtml(label)}</div><div class="hypit-capability-chip-meta">${escapeHtml(models.length ? t('hypit.modelsCount', { count: models.length }) : t('hypit.unavailable'))}</div></div>`;
        });
        (state.unsupported || []).forEach(item => {
            const label = item.label?.[currentLang()] || item.name || '';
            chips.push(`<div class="hypit-capability-chip is-unavailable"><div class="hypit-capability-chip-title">${escapeHtml(label)}</div><div class="hypit-capability-chip-meta">${escapeHtml(t('hypit.noImplementation'))}</div></div>`);
        });
        if (!chips.length) chips.push(`<div class="hypit-empty">${escapeHtml(t('hypit.noCatalog'))}</div>`);
        if (summaryEl) summaryEl.innerHTML = chips.join('');
    }

    function render() {
        ensureDefaults();
        renderSummary();
        if (slotsEl) slotsEl.innerHTML = SLOTS.map(renderSlot).join('');
        refreshIcons();
    }

    async function responseJSON(response) {
        let body = {};
        try { body = await response.json(); } catch (_) {}
        if (!response.ok) throw new Error(body?.detail || body?.error || `HTTP ${response.status}`);
        return body;
    }

    async function load() {
        if (state.loading) return;
        state.loading = true;
        setStatus(t('hypit.loading'));
        try {
            const [capabilityResponse, settingsResponse] = await Promise.all([
                fetch(`${API}/capabilities`),
                fetch(settingsURL)
            ]);
            const capabilities = await responseJSON(capabilityResponse);
            state.settings = await responseJSON(settingsResponse);
            state.catalog = capabilities;
            state.capabilities = Array.isArray(capabilities.supported_capabilities) ? capabilities.supported_capabilities : [];
            state.unsupported = Array.isArray(capabilities.unsupported_capabilities) ? capabilities.unsupported_capabilities : [];
            state.loaded = true;
            render();
            setStatus(t('hypit.loaded'), 'success');
        } catch (error) {
            setStatus(t('hypit.loadError', { message: error?.message || error }), 'error');
            render();
        } finally {
            state.loading = false;
        }
    }

    async function save() {
        if (state.saving) return;
        ensureDefaults();
        state.saving = true;
        setStatus(t('hypit.saving'));
        try {
            const response = await fetch(settingsURL, {
                method: 'PUT',
                headers: { 'content-type': 'application/json' },
                body: JSON.stringify({ defaults: state.settings.defaults, ...(projectId ? {expected_revision:state.settings.revision || 1} : {}) })
            });
            state.settings = await responseJSON(response);
            render();
            setStatus(t('hypit.saved'), 'success');
        } catch (error) {
            setStatus(t('hypit.saveError', { message: error?.message || error }), 'error');
        } finally {
            state.saving = false;
        }
    }

    function open() {
        if (typeof window.closeComfyUiSettings === 'function') window.closeComfyUiSettings();
        layout?.classList.add('hypit-settings-mode');
        block?.removeAttribute('hidden');
        nav?.classList.add('active');
        nav?.setAttribute('aria-current', 'page');
        document.querySelector('.api-page-delete-btn')?.setAttribute('hidden', 'hidden');
        document.querySelector('.api-page-save-btn')?.setAttribute('hidden', 'hidden');
        render();
        syncEditorHeader();
        if (!state.loaded) load();
    }

    function close() {
        layout?.classList.remove('hypit-settings-mode');
        block?.setAttribute('hidden', 'hidden');
        nav?.classList.remove('active');
        nav?.setAttribute('aria-current', 'false');
        document.querySelector('.api-page-delete-btn')?.removeAttribute('hidden');
        document.querySelector('.api-page-save-btn')?.removeAttribute('hidden');
        if (typeof window.renderEditor === 'function') window.renderEditor();
    }

    function onSlotChange(event) {
        const target = event.target;
        const slot = target?.dataset?.hypitSlot;
        if (!slot) return;
        if (target.matches('[data-hypit-family], [data-hypit-variant], [data-hypit-provider]')) {
            const card = target.closest('[data-hypit-slot-card]');
            if (!card) return;
            if (target.matches('[data-hypit-family]')) {
                const families = candidateFamilies(slot);
                if(!target.value){state.settings.defaults[slot]=emptySlot();renderSlotInPlace(slot);return;}
                const family = families.find(item => item.family_id === target.value);
                const variants = family?.variants || [];
                const variantSelect = card.querySelector('[data-hypit-variant]');
                const providerSelect = card.querySelector('[data-hypit-provider]');
                if (variantSelect) variantSelect.innerHTML = optionsHtml(variants, variants[0]?.model_id, variantLabel, 'model_id');
                const providers = variants.filter((item, index, list) => list.findIndex(other => other.provider_id === item.provider_id) === index);
                if (providerSelect) providerSelect.innerHTML = providers.map(item => `<option value="${escapeHtml(item.provider_id)}">${escapeHtml(item.provider_name || item.provider_id)}</option>`).join('');
            } else if (target.matches('[data-hypit-variant]')) {
                const families = candidateFamilies(slot);
                const family = families.find(item => item.family_id === card.querySelector('[data-hypit-family]')?.value);
                const selected = family?.variants.find(item => item.model_id === target.value);
                const providerSelect = card.querySelector('[data-hypit-provider]');
                if (providerSelect && selected) providerSelect.value = selected.provider_id;
            }
            syncSelection(slot, card);
            renderSlotInPlace(slot);
            return;
        }
        if (target.matches('[data-hypit-parameter]')) {
            const current = state.settings.defaults[slot] || emptySlot();
            current.parameters = current.parameters || {};
            const value = target.type === 'checkbox' ? target.checked : (target.type === 'number' && target.value !== '' ? Number(target.value) : target.value);
            if (value === '' || value === undefined) delete current.parameters[target.dataset.hypitParameter];
            else current.parameters[target.dataset.hypitParameter] = value;
            state.settings.defaults[slot] = current;
        }
    }

    function renderSlotInPlace(slot) {
        const currentCard = [...(slotsEl?.querySelectorAll('[data-hypit-slot-card]') || [])]
            .find(item => item.dataset.hypitSlotCard === slot);
        if (!currentCard) return render();
        const wrapper = document.createElement('div');
        wrapper.innerHTML = renderSlot(slot);
        const next = wrapper.firstElementChild;
        if (next) currentCard.replaceWith(next);
        refreshIcons();
    }

    registerTranslations();
    if(projectId) window.addEventListener('load', ()=>{open(); const title=document.querySelector('#hypitSettingsBlock [data-i18n="hypit.title"]');if(title)title.textContent=currentLang()==='en'?'Project models':'项目模型';});
    if (window.StudioI18n) window.StudioI18n.apply(document);

    window.openHypitSettings = open;
    window.closeHypitSettings = close;
    window.reloadHypitSettings = load;
    window.saveHypitSettings = save;

    slotsEl?.addEventListener('click', event=>{
        const target=event.target.closest('[data-hypit-choice]');if(!target)return;
        const current=state.settings.defaults[target.dataset.hypitSlot];
        if(target.dataset.value==='')delete current.parameters[target.dataset.hypitChoice];
        else current.parameters[target.dataset.hypitChoice]=JSON.parse(target.dataset.value);
        renderSlotInPlace(target.dataset.hypitSlot);
    });
    slotsEl?.addEventListener('change', onSlotChange);
    slotsEl?.addEventListener('input', onSlotChange);
    document.getElementById('localComfyuiNav')?.addEventListener('click', close);
    document.getElementById('runningHubComfyuiNav')?.addEventListener('click', close);
    window.addEventListener('studio-lang-change', () => {
        if (state.loaded || layout?.classList.contains('hypit-settings-mode')) render();
        syncEditorHeader();
    });
    window.addEventListener('load', () => {
        if (layout?.classList.contains('hypit-settings-mode')) load();
    });
})();
