(function(){
    function escapeHtml(value=''){
        return String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
    }
    function text(key, fallback){
        return window.StudioI18n?.t?.(key) || fallback;
    }
    function materialIdFromUrl(url=''){
        const clean = decodeURIComponent(String(url || '').split('?', 1)[0]);
        return clean.startsWith('/api/materials/') ? clean.split('/').pop() : '';
    }
    function resultIdFromUrl(url=''){
        const clean = decodeURIComponent(String(url || '').split('?', 1)[0]);
        return clean.startsWith('/api/results/') ? clean.split('/').pop() : '';
    }
    function mediaCategories(library){
        return (library?.categories || []).filter(category => ['image','media'].includes(String(category.type || 'image').toLowerCase()));
    }
    function ensureStyle(){
        if(document.getElementById('materialPromoteStyle')) return;
        const style = document.createElement('style');
        style.id = 'materialPromoteStyle';
        style.textContent = `
            .material-promote-overlay{position:fixed;inset:0;z-index:300;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(15,23,42,.42);backdrop-filter:blur(10px)}
            .material-promote-dialog{width:min(440px,94vw);border:1px solid var(--line,#e2e8f0);border-radius:14px;background:var(--panel,#fff);color:var(--text,#111827);box-shadow:0 26px 80px rgba(15,23,42,.28);overflow:hidden}
            .material-promote-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:16px 18px;border-bottom:1px solid var(--line,#e2e8f0)}
            .material-promote-head strong{display:block;font-size:16px;line-height:1.2;font-weight:900}
            .material-promote-head span{display:block;margin-top:5px;color:var(--muted,#64748b);font-size:11px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:330px}
            .material-promote-close{width:30px;height:30px;border:1px solid var(--line,#e2e8f0);border-radius:8px;background:var(--soft,#f1f4f8);color:var(--muted,#64748b);font-size:20px;line-height:1}
            .material-promote-body{display:grid;gap:12px;padding:16px 18px}
            .material-promote-field{display:grid;gap:6px;color:var(--muted,#64748b);font-size:11px;font-weight:850}
            .material-promote-field select{width:100%;height:38px;border:1px solid var(--line,#e2e8f0);border-radius:9px;background:var(--card,#fff);color:var(--text,#111827);padding:0 10px;outline:none;font:inherit}
            .material-promote-field select:focus{border-color:var(--line-2,#cbd5e1);box-shadow:0 0 0 3px rgba(148,163,184,.14)}
            .material-promote-category-row{display:grid;grid-template-columns:minmax(0,1fr) 38px;gap:8px;align-items:center}
            .material-promote-add-category{width:38px;height:38px;border:1px solid var(--line,#e2e8f0);border-radius:9px;background:var(--card,#fff);color:var(--muted,#64748b);display:inline-flex;align-items:center;justify-content:center;font-size:20px;font-weight:700}
            .material-promote-inline-create{display:none;grid-template-columns:minmax(0,1fr) auto auto;gap:8px}
            .material-promote-inline-create.open{display:grid}
            .material-promote-inline-create input{min-width:0;height:36px;border:1px solid var(--line,#e2e8f0);border-radius:9px;background:var(--card,#fff);color:var(--text,#111827);padding:0 10px;outline:none;font:inherit}
            .material-promote-inline-create button{height:36px;padding:0 11px;border:1px solid var(--line,#e2e8f0);border-radius:9px;background:var(--card,#fff);color:var(--muted,#64748b);font-weight:800}
            .material-promote-hint{color:var(--muted,#64748b);font-size:11px;line-height:1.5;font-weight:700}
            .material-promote-error{padding:9px 10px;border:1px solid rgba(220,38,38,.25);border-radius:9px;background:rgba(220,38,38,.07);color:#b91c1c;font-size:11px;line-height:1.45;font-weight:800}
            .theme-dark .material-promote-error{color:#fca5a5;background:rgba(248,113,113,.1);border-color:rgba(248,113,113,.28)}
            .material-promote-actions{display:flex;justify-content:flex-end;gap:8px;padding:13px 18px;border-top:1px solid var(--line,#e2e8f0)}
            .material-promote-actions button{height:34px;padding:0 14px;border:1px solid var(--line,#e2e8f0);border-radius:9px;background:var(--card,#fff);color:var(--muted,#64748b);font-weight:850}
            .material-promote-actions button.primary{border-color:var(--strong,#111827);background:var(--strong,#111827);color:var(--strong-text,#fff)}
            .material-promote-actions button:disabled{opacity:.55;cursor:wait}
        `;
        document.head.appendChild(style);
    }
    async function open(options={}){
        const entries = [
            ...(Array.isArray(options.entries) ? options.entries : []),
            ...(Array.isArray(options.materialIds) ? options.materialIds.map(id => ({kind:'material', id})) : []),
            ...(Array.isArray(options.resultIds) ? options.resultIds.map(id => ({kind:'result', id})) : []),
            {kind:options.resultId || resultIdFromUrl(options.url || '') ? 'result' : 'material', id:options.resultId || options.materialId || resultIdFromUrl(options.url || '') || materialIdFromUrl(options.url || '')}
        ].map(entry => ({kind:entry?.kind === 'result' ? 'result' : 'material', id:String(entry?.id || '').trim()})).filter(entry => entry.id);
        const uniqueEntries = [...new Map(entries.map(entry => [`${entry.kind}:${entry.id}`, entry])).values()];
        if(!uniqueEntries.length) throw new Error(text('material.promoteOnlyTemporary', '当前内容无法收藏'));
        ensureStyle();
        document.querySelector('.material-promote-overlay')?.remove();
        const response = await fetch('/api/asset-library');
        const data = await response.json().catch(() => ({}));
        if(!response.ok) throw new Error(data.detail || text('material.loadFailed', '资产库加载失败'));
        const libraries = Array.isArray(data.library?.libraries) ? data.library.libraries : [];
        if(!libraries.length) throw new Error(text('material.noLibrary', '暂无可用资产库'));
        const overlay = document.createElement('div');
        overlay.className = 'material-promote-overlay';
        overlay.innerHTML = `<div class="material-promote-dialog" role="dialog" aria-modal="true" aria-label="${escapeHtml(text('material.promote', '收藏到资产素材'))}">
            <div class="material-promote-head"><div><strong>${escapeHtml(text('material.promote', '收藏到资产素材'))}</strong><span title="${escapeHtml(options.name || '')}">${escapeHtml(uniqueEntries.length > 1 ? `${uniqueEntries.length} 个素材` : (options.name || text('material.unnamed', '未命名素材')))}</span></div><button class="material-promote-close" type="button" aria-label="${escapeHtml(text('common.close', '关闭'))}">×</button></div>
            <div class="material-promote-body">
                <label class="material-promote-field"><span>${escapeHtml(text('material.library', '资产库'))}</span><select data-promote-library></select></label>
                <label class="material-promote-field"><span>${escapeHtml(text('material.category', '分组'))}</span><div class="material-promote-category-row"><select data-promote-category></select><button class="material-promote-add-category" type="button" data-promote-add-category title="新建分组">+</button></div></label>
                <div class="material-promote-inline-create" data-promote-inline-create><input data-promote-new-category placeholder="分组名称"><button type="button" data-promote-create-category>新建</button><button type="button" data-promote-create-cancel>取消</button></div>
                <div class="material-promote-hint">${escapeHtml(text('material.promoteHint', '收藏后将移出临时素材，文件不会重复复制，画布引用保持不变。'))}</div>
                <div class="material-promote-error" data-promote-error role="alert" hidden></div>
            </div>
            <div class="material-promote-actions"><button type="button" data-promote-cancel>${escapeHtml(text('common.cancel', '取消'))}</button><button class="primary" type="button" data-promote-save>${escapeHtml(text('material.promoteConfirm', '确认收藏'))}</button></div>
        </div>`;
        document.body.appendChild(overlay);
        const librarySelect = overlay.querySelector('[data-promote-library]');
        const categorySelect = overlay.querySelector('[data-promote-category]');
        const newCategoryInput = overlay.querySelector('[data-promote-new-category]');
        const inlineCreate = overlay.querySelector('[data-promote-inline-create]');
        const errorBox = overlay.querySelector('[data-promote-error]');
        const saveButton = overlay.querySelector('[data-promote-save]');
        librarySelect.innerHTML = libraries.map(library => `<option value="${escapeHtml(library.id)}">${escapeHtml(library.name || text('material.library', '资产库'))}</option>`).join('');
        const requestedLibraryId = String(options.libraryId || data.library?.active_library_id || libraries[0].id || '');
        librarySelect.value = libraries.some(library => String(library.id) === requestedLibraryId) ? requestedLibraryId : String(libraries[0].id || '');
        const refreshCategories = () => {
            const library = libraries.find(entry => String(entry.id) === String(librarySelect.value)) || libraries[0];
            const categories = mediaCategories(library);
            categorySelect.innerHTML = categories.length
                ? categories.map(category => `<option value="${escapeHtml(category.id)}">${escapeHtml(category.name || text('material.category', '分组'))}</option>`).join('')
                : `<option value="">${escapeHtml(text('material.createCategoryFirst', '请填写新分组名称'))}</option>`;
            if(options.categoryId && categories.some(category => String(category.id) === String(options.categoryId))) categorySelect.value = String(options.categoryId);
        };
        refreshCategories();
        const clearError = () => { errorBox.textContent = ''; errorBox.hidden = true; };
        librarySelect.addEventListener('change', () => { clearError(); refreshCategories(); });
        categorySelect.addEventListener('change', clearError);
        newCategoryInput.addEventListener('input', clearError);
        overlay.querySelector('[data-promote-add-category]').addEventListener('click', () => { inlineCreate.classList.add('open'); newCategoryInput.focus(); });
        overlay.querySelector('[data-promote-create-cancel]').addEventListener('click', () => { inlineCreate.classList.remove('open'); newCategoryInput.value = ''; clearError(); });
        overlay.querySelector('[data-promote-create-category]').addEventListener('click', async () => {
            const name = newCategoryInput.value.trim();
            if(!name) return;
            clearError();
            try {
                const categoryResponse = await fetch('/api/asset-library/categories', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:librarySelect.value, name, type:'image'})});
                const categoryData = await categoryResponse.json().catch(() => ({}));
                if(!categoryResponse.ok) throw new Error(categoryData.detail || text('material.createCategoryFailed', '新建分组失败'));
                const library = categoryData.library?.libraries?.find(entry => String(entry.id) === String(librarySelect.value));
                if(library){
                    const index = libraries.findIndex(entry => String(entry.id) === String(library.id));
                    if(index >= 0) libraries[index] = library;
                }
                refreshCategories();
                categorySelect.value = categoryData.category?.id || categorySelect.value;
                inlineCreate.classList.remove('open');
                newCategoryInput.value = '';
            } catch(error){
                errorBox.textContent = error?.message || text('material.createCategoryFailed', '新建分组失败');
                errorBox.hidden = false;
            }
        });
        const close = () => overlay.remove();
        overlay.querySelector('.material-promote-close').addEventListener('click', close);
        overlay.querySelector('[data-promote-cancel]').addEventListener('click', close);
        overlay.addEventListener('mousedown', event => { if(event.target === overlay) close(); });
        saveButton.addEventListener('click', async () => {
            const libraryId = librarySelect.value;
            let categoryId = categorySelect.value;
            clearError();
            saveButton.disabled = true;
            try {
                if(!categoryId) throw new Error(text('material.selectCategory', '请选择分组'));
                const promoted = [];
                for(const entry of uniqueEntries){
                    const endpoint = entry.kind === 'result' ? `/api/results/${encodeURIComponent(entry.id)}/promote` : `/api/materials/${encodeURIComponent(entry.id)}/promote`;
                    const promoteResponse = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({library_id:libraryId, category_id:categoryId, name:uniqueEntries.length === 1 ? (options.name || '') : ''})});
                    const promoteData = await promoteResponse.json().catch(() => ({}));
                    if(!promoteResponse.ok) throw new Error(promoteData.detail || text('material.promoteFailed', '收藏失败'));
                    promoted.push(promoteData);
                }
                const result = uniqueEntries.length === 1 ? promoted[0] : {items:promoted, count:promoted.length};
                await options.onSuccess?.(result);
                close();
                return result;
            } catch(error){
                saveButton.disabled = false;
                errorBox.textContent = error?.message || text('material.promoteFailed', '收藏失败');
                errorBox.hidden = false;
                options.onError?.(error);
            }
        });
        return overlay;
    }
    window.MaterialPromote = {open, materialIdFromUrl, resultIdFromUrl};
})();
