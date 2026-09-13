"""后台任务生命周期；只依赖显式传入的存储、任务容器和模型执行函数。"""
import asyncio
import logging
import time


async def execute_task(task_id, execute, *, storage, records, handles, lock,
                       classify_error=None,
                       cancel_message='已停止本地等待；上游任务可能仍在继续'):
    def cancelled():
        with lock:
            return records.get(task_id, {}).get('status') == 'cancelled'

    def transition(**changes):
        with lock:
            if records.get(task_id, {}).get('status') == 'cancelled' and changes.get('status') != 'cancelled':
                return False
        try:
            storage.update_canvas_task(task_id, **changes)
        except Exception as exc:
            # 已产生结果时保留结果并暴露同步错误，不自动重提模型请求。
            changes['sync_error'] = str(exc)
            logging.exception('画布任务状态持久化失败 [%s]', task_id)
        else:
            changes['sync_error'] = ''
        with lock:
            records.setdefault(task_id, {}).update(changes, updated_at=time.time())
        return not changes['sync_error']

    try:
        if cancelled():
            return
        if not transition(status='running'):
            detail = records[task_id].get('sync_error', '')
            transition(status='failed', error=f'任务状态无法保存，未提交模型请求：{detail}')
            return
        result = await execute()
        if cancelled():
            return
        if isinstance(result, dict) and result.get('error'):
            raise RuntimeError(str(result['error']))
        transition(status='succeeded', result=result, error='')
    except asyncio.CancelledError:
        transition(status='cancelled', error='', message=cancel_message)
        raise
    except Exception as exc:
        if cancelled():
            return
        details = classify_error(exc) if classify_error else None
        transition(**(details or {'status':'failed', 'error':str(getattr(exc,'detail',None) or exc), 'status_code':getattr(exc,'status_code',500)}))
    finally:
        with lock:
            if handles.get(task_id) is asyncio.current_task():
                handles.pop(task_id, None)
