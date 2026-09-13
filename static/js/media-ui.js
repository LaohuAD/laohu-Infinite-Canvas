/* 素材库与画布共享：原生剪贴板、媒体分类和视频封面降级。 */
(function(){
    const text=(zh,en)=>window.StudioI18n?.lang?.()==='en'?en:zh;
    async function nativeCopy(payload){
        const response=await fetch('/api/system-clipboard',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const data=await response.json();
        if(!response.ok) throw new Error(data.detail||text('复制失败','Copy failed'));
        return data;
    }
    async function writeText(value){
        value=String(value??'');
        if(navigator.clipboard?.writeText){try {await navigator.clipboard.writeText(value);return;}catch(_) {}}
        // 隐藏临时文本框，不选中用户正在查看的连接说明。
        const active=document.activeElement, area=document.createElement('textarea');
        area.value=value;area.style.cssText='position:fixed;left:-9999px;top:0;opacity:0';
        (document.querySelector('dialog[open]')||document.body).appendChild(area);
        try {area.select();if(!document.execCommand('copy')) await nativeCopy({text:value});}
        finally {area.remove();active?.focus?.({preventScroll:true});}
    }
    function category(item){
        if(item?.media_category==='music'||item?.generation_kind==='music'||item?.kind==='music') return 'music';
        const kind=String(item?.kind||item?.type||'').toLowerCase();
        const name=String(item?.url||item?.name||'').split('?')[0];
        if(kind.includes('video')||/\.(mp4|webm|mov|m4v|mkv)$/i.test(name))return 'video';
        if(kind.includes('audio')||/\.(mp3|wav|flac|ogg|m4a|aac)$/i.test(name))return 'audio';
        if(kind.includes('text')||/\.(txt|md|json|csv)$/i.test(name)||(!item?.url&&(item?.text||item?.content||item?.prompt)))return 'text';
        return 'image';
    }
    async function copy(items){
        if(!items.length)throw new Error(text('请先选择素材','Select materials first'));
        if(items.every(item=>category(item)==='text')){
            const values=await Promise.all(items.map(async item=>{
                const embedded=item.text??item.content??item.value??item.prompt;
                if(typeof embedded==='string')return embedded;
                const r=await fetch(item.url);if(!r.ok)throw new Error(text('文本读取失败','Cannot read text'));return r.text();
            }));
            await writeText(values.join('\n\n'));return;
        }
        const normalized=items.map(item=>{
            if(!item.url && category(item)==='text') return {text:String(item.text??item.content??item.value??item.prompt??'')};
            const url=new URL(item.url,location.origin);
            if(url.origin!==location.origin)throw new Error(text('请先将外部素材保存到素材库，再复制原文件','Save external materials to the library before copying their files'));
            return url.pathname+url.search;
        });
        if(normalized.every(item=>typeof item==='string')) await nativeCopy({urls:normalized});
        else await nativeCopy({items:normalized.map(item=>typeof item==='string'?{url:item}:item)});
    }
    const posters=new Map();
    function firstFrame(url){
        if(posters.has(url))return posters.get(url);
        const promise=new Promise((resolve,reject)=>{
            const video=document.createElement('video');video.muted=true;video.preload='auto';video.playsInline=true;video.crossOrigin='anonymous';
            let done=false;
            const finish=(error,value)=>{if(done)return;done=true;clearTimeout(timer);video.removeAttribute('src');video.load();error?reject(error):resolve(value);};
            const capture=()=>{try {const canvas=document.createElement('canvas'),scale=Math.min(1,512/video.videoWidth);canvas.width=Math.max(1,Math.round(video.videoWidth*scale));canvas.height=Math.max(1,Math.round(video.videoHeight*scale));canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);finish(null,canvas.toDataURL('image/jpeg',.82));}catch(error){finish(error);}};
            const timer=setTimeout(()=>finish(new Error('Video preview timed out')),15000);
            video.addEventListener('loadeddata',()=>{if(video.duration>.05)video.currentTime=Math.min(.05,video.duration/2);else capture();},{once:true});
            video.addEventListener('seeked',capture,{once:true});video.addEventListener('error',()=>finish(new Error('Cannot decode video')),{once:true});video.src=url;
        });
        posters.set(url,promise);if(posters.size>100)posters.delete(posters.keys().next().value);return promise;
    }
    function bindVideoPosters(root=document){
        root.querySelectorAll('img[data-video-poster]:not([data-video-bound])').forEach(img=>{
            img.dataset.videoBound='1';
            const fallback=()=>{if(img.dataset.videoFallback)return;img.dataset.videoFallback='1';firstFrame(img.dataset.videoPoster).then(src=>{if(img.isConnected)img.src=src;}).catch(()=>{img.alt=text('视频封面不可用，双击播放','Preview unavailable. Double-click to play');img.classList.add('video-preview-unavailable');});};
            img.addEventListener('error',fallback);if(img.complete&&!img.naturalWidth)fallback();
        });
    }
    // 数值只经原滑块的业务事件提交，直接输入与拖动不会分成两条执行链。
    const numericPairs=new WeakMap();
    function syncNumericSlider(range, force=false){
        const number=numericPairs.get(range);
        if(!number)return;
        ['min','max','step'].forEach(key=>number[key]=range[key]);
        number.disabled=range.disabled;
        if(force||document.activeElement!==number)number.value=range.value;
    }
    function bindNumericSliders(ranges){
        ranges.forEach(range=>{
            if(numericPairs.has(range)){syncNumericSlider(range);return;}
            const number=document.createElement('input');
            number.type='number';number.className='capability-number-value studio-slider-number';
            number.setAttribute('aria-label',range.getAttribute('aria-label')||range.closest('label')?.querySelector('span')?.textContent||text('数值','Value'));
            range.insertAdjacentElement('afterend',number);
            numericPairs.set(range,number);syncNumericSlider(range);
            range.addEventListener('input',()=>syncNumericSlider(range));
            range.addEventListener('change',()=>syncNumericSlider(range,true));
            number.addEventListener('input',()=>{
                if(number.value.trim()===''||!Number.isFinite(number.valueAsNumber))return;
                // 由原生 range 统一处理上下限和步长，再调用现有业务校验。
                range.value=String(number.valueAsNumber);
                range.dispatchEvent(new Event('input',{bubbles:true}));
            });
            number.addEventListener('change',()=>{range.dispatchEvent(new Event('change',{bubbles:true}));syncNumericSlider(range,true);});
            number.addEventListener('blur',()=>syncNumericSlider(range,true));
        });
    }
    // 音频和视频共用同一时间轴；选区与播放头独立，不将拖选误当作播放进度。
    function createTimeline(host, media, {url, onRange=()=>{}}={}){
        const controller=new AbortController(),signal=controller.signal;
        const label=(zh,en)=>text(zh,en),format=n=>`${Math.floor(n/60)}:${(n%60).toFixed(2).padStart(5,'0')}`;
        let duration=0,start=0,end=0,disposed=false,frame=0,context;
        host.classList.add('studio-timeline');
        host.innerHTML=`<div class="studio-timeline-track">
            <div class="studio-timeline-bars"></div><div class="studio-timeline-progress"></div>
            <div class="studio-timeline-shade before"></div><div class="studio-timeline-shade after"></div>
            <div class="studio-timeline-selection"></div>
            <button type="button" class="studio-timeline-handle start" data-time-handle="start" role="slider" aria-label="${label('开始时间','Start time')}"></button>
            <button type="button" class="studio-timeline-handle end" data-time-handle="end" role="slider" aria-label="${label('结束时间','End time')}"></button>
            <button type="button" class="studio-timeline-playhead" data-time-handle="play" role="slider" aria-label="${label('播放位置','Playhead')}"></button>
            <span class="studio-timeline-message">${label('读取波形…','Loading waveform…')}</span>
        </div><div class="studio-timeline-ticks"></div><div class="studio-timeline-controls">
            <div class="studio-timeline-transport"><button type="button" data-time-play>${label('播放','Play')}</button>
            <button type="button" data-time-selection>${label('试听选区','Play selection')}</button></div>
            <output data-time-position></output><span class="studio-timeline-range"></span>
        </div>`;
        const track=host.querySelector('.studio-timeline-track'),message=host.querySelector('.studio-timeline-message');
        const play=host.querySelector('[data-time-play]'),selectionButton=host.querySelector('[data-time-selection]');let selectionPlayback=false;
        const listen=(el,event,fn)=>el.addEventListener(event,fn,{signal});
        function sync(){
            const current=Math.max(0,Math.min(duration,media.currentTime||0)),percent=n=>duration?n/duration*100:0;
            host.style.setProperty('--range-start',percent(start)+'%');host.style.setProperty('--range-end',percent(end)+'%');host.style.setProperty('--play-progress',percent(current)+'%');
            host.querySelector('[data-time-position]').textContent=`${format(current)} / ${format(duration)}`;
            host.querySelector('.studio-timeline-range').textContent=`${label('选区','Range')} ${format(start)} — ${format(end)} · ${(end-start).toFixed(2)}s`;
            play.textContent=media.paused?label('播放','Play'):label('暂停','Pause');
            host.querySelectorAll('[data-time-handle]').forEach(el=>{const value=el.dataset.timeHandle==='start'?start:el.dataset.timeHandle==='end'?end:current;el.setAttribute('aria-valuemin','0');el.setAttribute('aria-valuemax',duration);el.setAttribute('aria-valuenow',value.toFixed(2));el.setAttribute('aria-valuetext',format(value));});
            [play,selectionButton,...host.querySelectorAll('[data-time-handle]')].forEach(b=>b.disabled=!duration);
        }
        function setDuration(value){
            if(!Number.isFinite(value)||value<=0||duration===value)return;
            const first=!duration;duration=value;end=first?duration:Math.min(end,duration);start=Math.min(start,Math.max(0,end-.1));
            host.querySelector('.studio-timeline-ticks').innerHTML=Array.from({length:5},(_,i)=>`<span>${format(duration*i/4)}</span>`).join('');sync();onRange({start,end,duration});
        }
        function change(which,value){
            if(!duration)return;
            if(which==='start')start=Math.max(0,Math.min(end-.1,value));
            else if(which==='end')end=Math.min(duration,Math.max(start+.1,value));
            else {selectionPlayback=false;media.currentTime=Math.max(0,Math.min(duration,value));}
            sync();onRange({start,end,duration});
        }
        listen(track,'pointerdown',event=>{
            if(event.button!==0||!duration)return;event.preventDefault();event.stopPropagation();
            const which=event.target.closest('[data-time-handle]')?.dataset.timeHandle||'play';
            const update=e=>{const r=track.getBoundingClientRect();change(which,(e.clientX-r.left)/r.width*duration);};
            track.setPointerCapture(event.pointerId);update(event);
            const move=e=>update(e),finish=()=>{track.removeEventListener('pointermove',move);track.removeEventListener('pointerup',finish);track.removeEventListener('pointercancel',finish);};
            track.addEventListener('pointermove',move,{signal});track.addEventListener('pointerup',finish,{signal});track.addEventListener('pointercancel',finish,{signal});
        });
        host.querySelectorAll('[data-time-handle]').forEach(el=>listen(el,'keydown',event=>{
            if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();
            const which=el.dataset.timeHandle,current=which==='start'?start:which==='end'?end:media.currentTime;
            change(which,event.key==='Home'?0:event.key==='End'?duration:current+(event.key==='ArrowLeft'?-1:1)*(event.shiftKey?1:.1));
        }));
        const safePlay=()=>media.play().catch(()=>{message.hidden=false;message.textContent=label('暂时无法播放','Playback unavailable');});
        listen(play,'click',()=>{selectionPlayback=false;media.paused?safePlay():media.pause();});
        listen(selectionButton,'click',()=>{selectionPlayback=true;media.currentTime=start;safePlay();});
        function tick(){
            if(disposed)return;
            if(selectionPlayback&&media.currentTime>=end){media.pause();media.currentTime=end;selectionPlayback=false;}
            sync();if(!media.paused)frame=requestAnimationFrame(tick);
        }
        listen(media,'play',()=>{cancelAnimationFrame(frame);tick();});listen(media,'pause',()=>{cancelAnimationFrame(frame);sync();});listen(media,'timeupdate',()=>{if(selectionPlayback&&media.currentTime>=end){selectionPlayback=false;media.pause();media.currentTime=end;}sync();});
        listen(media,'loadedmetadata',()=>setDuration(media.duration));listen(media,'ended',sync);
        setDuration(media.duration);sync();
        // 解码真实音频；文件过大或浏览器无法解码时保留可操作时间轴，明确提示而不伪造波形。
        (async()=>{
            try{
                const response=await fetch(url,{signal});if(!response.ok)throw Error('media');
                const limit=40*1024*1024;if(Number(response.headers.get('content-length'))>limit)throw Error('large');
                const reader=response.body.getReader(),chunks=[];let total=0;
                while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>limit){await reader.cancel();throw Error('large');}chunks.push(value);}
                if(disposed) return;
                if(media.duration>1800)throw Error('long');
                const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
                context=new (window.AudioContext||window.webkitAudioContext)({sampleRate:8000});
                const buffer=await context.decodeAudioData(bytes.buffer);if(disposed)return;
                const channels=Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i)),samples=channels[0],count=200,step=Math.max(1,Math.ceil(samples.length/count)),peaks=[];
                for(let i=0;i<count;i++){let peak=0;for(let j=i*step;j<Math.min(samples.length,(i+1)*step);j++)for(const channel of channels)peak=Math.max(peak,Math.abs(channel[j]));peaks.push(peak);}
                const max=Math.max(.01,...peaks);host.querySelector('.studio-timeline-bars').innerHTML=peaks.map(p=>`<i style="height:${Math.max(2,p/max*86)}%"></i>`).join('');message.hidden=true;
            }catch(error){if(!disposed){message.textContent=label('波形不可用 · 仍可拖动时间轴','Waveform unavailable · Timeline still usable');}}
            finally{if(context&&context.state!=='closed')context.close().catch(()=>{});}
        })();
        return {values:()=>({start,end,duration}),setDuration,destroy(){disposed=true;controller.abort();cancelAnimationFrame(frame);if(context&&context.state!=='closed')context.close().catch(()=>{});host.replaceChildren();}};
    }
    window.StudioMedia={createTimeline,copy,writeText,category,bindVideoPosters,firstFrame,bindNumericSliders,syncNumericSlider};
})();
