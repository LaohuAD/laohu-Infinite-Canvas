"""工作台迁移保留用户作品，而不是只隐藏旧入口。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from canvas_core.workbench_migration import assign_node_numbers, retire_directors


class WorkbenchMigrationTests(unittest.TestCase):
    def test_director_clips_and_legacy_segments_keep_text_media_and_identity(self):
        root = Path(__file__).resolve().parents[1] / 'cache/studio-tests'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            canvas = {'id': 'film', 'nodes': [
                {'id': 'a', 'type': 'smart-video-director', 'x': 20, 'title': '作品',
                 'clips': [{'prompt': '镜头一', 'results': [{'url': '/api/results/video1'}]}]},
                {'id': 'b', 'type': 'smart-minimax-director', 'segments': [
                    {'prompt': '镜头二', 'result': {'url': '/api/results/video2', 'kind': 'video'},
                     'refs': {'audio': [{'url': '/api/assets/voice'}]}}]}],
                'connections': [{'from': 'a', 'to': 'b'}]}
            original = copy.deepcopy(canvas)
            self.assertTrue(retire_directors(canvas, Path(tmp)))
            self.assertEqual(json.loads((Path(tmp)/'film-directors.json').read_text()), original)
            self.assertFalse(retire_directors(canvas, Path(tmp)))
            self.assertEqual(canvas['connections'], original['connections'])
            self.assertEqual(canvas['nodes'][0]['id'], 'a')
            self.assertEqual(canvas['nodes'][0]['images'][0]['url'], '/api/results/video1')
            self.assertIn('镜头一', canvas['nodes'][0]['images'][-1]['text'])
            self.assertEqual(canvas['nodes'][1]['images'][1]['kind'], 'audio')
            self.assertNotIn('clips', canvas['nodes'][0])

    def test_node_numbers_stable_monotonic_and_not_boolean(self):
        canvas={'nodes':[{'id':'a','displayNumber':1},{'id':'b','displayNumber':True},
                         {'id':'c','displayNumber':1},{'id':'d','displayNumber':9}]}
        self.assertTrue(assign_node_numbers(canvas))
        numbers={n['id']:n['displayNumber'] for n in canvas['nodes']}
        self.assertEqual(len(set(numbers.values())),4)
        self.assertEqual(numbers['a'],1)
        self.assertEqual(numbers['d'],9)
        canvas['nodes'].reverse()
        self.assertFalse(assign_node_numbers(canvas))
        canvas['nodes'].append({'id':'new'})
        assign_node_numbers(canvas)
        self.assertGreater(canvas['nodes'][-1]['displayNumber'],max(numbers.values()))

if __name__=='__main__': unittest.main()
