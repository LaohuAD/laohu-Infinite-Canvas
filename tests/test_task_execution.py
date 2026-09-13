"""后台任务隔离与取消边界；不调用模型。"""
import asyncio
import unittest
from threading import Lock
from unittest.mock import Mock
from canvas_core.task_execution import execute_task

class TaskExecutionTests(unittest.IsolatedAsyncioTestCase):
    def context(self):
        records={'one':{'status':'queued'},'two':{'status':'queued'}}
        return records,{},Lock(),Mock()

    async def test_one_failure_does_not_affect_another_task(self):
        records,handles,lock,storage=self.context()
        async def fail():raise ValueError('坏任务')
        async def good():return {'images':['/result']}
        await asyncio.gather(execute_task('one',fail,storage=storage,records=records,handles=handles,lock=lock),execute_task('two',good,storage=storage,records=records,handles=handles,lock=lock))
        self.assertEqual(records['one']['status'],'failed')
        self.assertEqual(records['two']['status'],'succeeded')

    async def test_cancelled_task_cannot_publish_even_when_executor_swallows_cancel(self):
        records,handles,lock,storage=self.context();started=asyncio.Event()
        async def executor():
            started.set()
            try:await asyncio.sleep(60)
            except asyncio.CancelledError:return {'images':['late']}
        task=asyncio.create_task(execute_task('one',executor,storage=storage,records=records,handles=handles,lock=lock));handles['one']=task
        await started.wait();records['one']['status']='cancelled';task.cancel();await task
        self.assertEqual(records['one']['status'],'cancelled')
        self.assertNotIn('result',records['one']);self.assertNotIn('one',handles)

    async def test_failed_initial_persistence_prevents_paid_submission(self):
        records,handles,lock,storage=self.context();storage.update_canvas_task.side_effect=OSError('disk full');called=[]
        async def executor():called.append(1)
        await execute_task('one',executor,storage=storage,records=records,handles=handles,lock=lock)
        self.assertEqual(called,[]);self.assertEqual(records['one']['status'],'failed');self.assertIn('disk full',records['one']['error'])

    async def test_provider_pending_retains_remote_identity(self):
        records,handles,lock,storage=self.context()
        async def executor():raise ValueError('pending')
        await execute_task('one',executor,storage=storage,records=records,handles=handles,lock=lock,classify_error=lambda e:{'status':'jimeng_pending','submit_id':'upstream-1','error':''})
        self.assertEqual(records['one']['submit_id'],'upstream-1');self.assertEqual(records['one']['status'],'jimeng_pending')
