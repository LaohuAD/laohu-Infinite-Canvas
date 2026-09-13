/* 模型 HTTP 边界：只提交一次，取消直传，调用方决定任务和界面状态。 */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;if(root)root.CanvasModelClient=api;})(typeof globalThis==='undefined'?this:globalThis,function(){
    function create({request=globalThis.fetch,errorMessage}={}){
        async function post(endpoint,payload,{signal}={}){
            const response=await request(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal});
            if(!response.ok){
                const detail=errorMessage?await errorMessage(response):await response.text();
                const error=new Error(detail||`HTTP ${response.status}`);error.status=response.status;throw error;
            }
            return response.json();
        }
        async function submitMany(endpoint,payload,count,options={}){
            if(!Number.isInteger(count)||count<1||count>8)throw Error('无效提交数量 / Invalid submission count');
            return Promise.allSettled(Array.from({length:count},()=>post(endpoint,payload,options)));
        }
        return {post,submitMany};
    }
    return {create};
});
