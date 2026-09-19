(function(){
    // 继承服务端按翻译模块修改时间生成的缓存标识。
    const CACHE_VERSION = new URL(document.currentScript.src, location.href).searchParams.get('v') || '';
    const scripts = [
        '/static/js/i18n-core.js',
        '/static/js/i18n/common.js',
        '/static/js/i18n/studio.js',
        '/static/js/i18n/api-settings.js',
        '/static/js/i18n/canvas.js',
        '/static/js/i18n/smart-canvas.js',
        '/static/js/i18n/comfyui-settings.js',
        '/static/js/i18n/asset-manager.js',
    ];
    const tags = scripts.map(src => '<script src="' + src + '?v=' + CACHE_VERSION + '"></script>').join('');
    if(document.readyState === 'loading' && document.currentScript){
        document.write(tags);
        return;
    }
    scripts.reduce((promise, src) => promise.then(() => new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src + '?v=' + CACHE_VERSION;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    })), Promise.resolve()).then(() => window.StudioI18n?.apply?.()).catch(err => console.error('Failed to load i18n modules', err));
})();
