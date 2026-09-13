"""HTTP 请求恢复策略；只读重试与付费提交明确分离，取消向上传递。"""
import asyncio
import httpx


async def httpx_request_with_transient_retries(client, method, url, attempts=2, retry_delay=1.2, **kwargs):
    attempts = max(1, int(attempts or 1))
    # 提交超时不代表上游未接单；只有只读请求允许自动重试。
    # 第三方任务提交须凭原 task_id 查询，不能靠重发 POST 恢复。
    if str(method).upper() not in {"GET", "HEAD", "OPTIONS"}:
        attempts = 1
    last_exc = None
    retry_statuses = {502, 503, 504, 520, 522, 524}
    for attempt in range(attempts):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code in retry_statuses and attempt + 1 < attempts:
                await asyncio.sleep(retry_delay * (attempt + 1))
                continue
            return response
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                raise
            print(f"[HTTPX-RETRY] {method} {type(exc).__name__}; retry {attempt + 2}/{attempts}", flush=True)
            await asyncio.sleep(retry_delay * (attempt + 1))
    if last_exc:
        raise last_exc
    raise httpx.HTTPError(f"请求失败：{method} {url}")
