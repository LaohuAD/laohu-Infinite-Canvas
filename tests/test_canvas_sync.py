import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(expression):
    result = subprocess.run(
        ["node", "-e", expression],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"node failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return json.loads(result.stdout)


class CanvasSyncTests(unittest.TestCase):
    def test_three_way_merge_combines_different_node_fields_and_settings(self):
        data = run_node(
            r'''
const {merge} = require('./static/js/canvas-sync.js');
const base = {
  revision: 4,
  viewport: {x: 0, y: 0, scale: 1},
  settings: {quality: 'standard', count: 1},
  nodes: [{id: 'n1', title: '原名', x: 0, y: 0, promptDraftText: '原提示', displayNumber: 1}],
  connections: []
};
const local = JSON.parse(JSON.stringify(base));
local.nodes[0].x = 240;
local.settings.quality = 'high';
local.viewport = {x: 90, y: 12, scale: 1.4};
const remote = JSON.parse(JSON.stringify(base));
remote.nodes[0].title = '远端名';
remote.settings.count = 3;
remote.viewport = {x: -500, y: -300, scale: 0.4};
const result = merge(base, local, remote);
console.log(JSON.stringify({
  node: result.canvas.nodes[0],
  settings: result.canvas.settings,
  viewport: result.canvas.viewport,
  conflicts: result.conflicts
}));
'''
        )
        self.assertEqual(data["node"]["x"], 240)
        self.assertEqual(data["node"]["title"], "远端名")
        self.assertEqual(data["settings"], {"quality": "high", "count": 3})
        self.assertEqual(data["viewport"], {"x": 90, "y": 12, "scale": 1.4})
        self.assertEqual(data["conflicts"], [])

    def test_same_field_conflict_keeps_local_draft_and_reports_path(self):
        data = run_node(
            r'''
const {merge} = require('./static/js/canvas-sync.js');
const base = {nodes: [{id: 'n1', title: '原名', promptDraftText: '原提示'}], connections: [], settings: {}};
const local = {nodes: [{id: 'n1', title: '本地名', promptDraftText: '本地提示'}], connections: [], settings: {}};
const remote = {nodes: [{id: 'n1', title: '远端名', promptDraftText: '远端提示'}], connections: [], settings: {}};
const result = merge(base, local, remote);
console.log(JSON.stringify({node: result.canvas.nodes[0], conflicts: result.conflicts}));
'''
        )
        self.assertEqual(data["node"]["title"], "本地名")
        self.assertEqual(data["node"]["promptDraftText"], "本地提示")
        self.assertEqual(
            {item["path"] for item in data["conflicts"]},
            {"nodes.n1.title", "nodes.n1.promptDraftText"},
        )

    def test_delete_vs_edit_is_a_conflict_and_preserves_local_deletion(self):
        data = run_node(
            r'''
const {merge} = require('./static/js/canvas-sync.js');
const base = {nodes: [{id: 'n1', title: '原名'}], connections: [], settings: {}};
const local = {nodes: [], connections: [], settings: {}};
const remote = {nodes: [{id: 'n1', title: '远端改名'}], connections: [], settings: {}};
const result = merge(base, local, remote);
console.log(JSON.stringify(result));
'''
        )
        self.assertEqual(data["canvas"]["nodes"], [])
        self.assertEqual(data["conflicts"][0]["path"], "nodes.n1")
        self.assertEqual(data["conflicts"][0]["kind"], "delete-vs-edit")

    def test_remote_task_result_is_added_without_overwriting_local_prompt(self):
        data = run_node(
            r'''
const {merge} = require('./static/js/canvas-sync.js');
const base = {
  nodes: [{id: 'n1', promptDraftText: '原提示', runStatus: 'queued', images: [], creationTasks: []}],
  connections: [], settings: {}
};
const local = JSON.parse(JSON.stringify(base));
local.nodes[0].promptDraftText = '本地正在编辑的提示';
const remote = JSON.parse(JSON.stringify(base));
remote.nodes[0].runStatus = 'succeeded';
remote.nodes[0].images = [{url: '/api/results/r1', kind: 'image'}];
remote.nodes[0].creationTasks = [{id: 'task-1', runStatus: 'succeeded', images: [{url: '/api/results/r1'}]}];
const result = merge(base, local, remote);
console.log(JSON.stringify(result));
'''
        )
        node = data["canvas"]["nodes"][0]
        self.assertEqual(node["promptDraftText"], "本地正在编辑的提示")
        self.assertEqual(node["runStatus"], "succeeded")
        self.assertEqual(node["images"][0]["url"], "/api/results/r1")
        self.assertEqual(node["creationTasks"][0]["id"], "task-1")

    def test_remote_connection_and_parallel_new_nodes_survive_with_unique_numbers(self):
        data = run_node(
            r'''
const {merge} = require('./static/js/canvas-sync.js');
const base = {
  nextNodeNumber: 3,
  nodes: [{id: 'n1', displayNumber: 1}, {id: 'n2', displayNumber: 2}],
  connections: []
};
const local = {
  nextNodeNumber: 3,
  nodes: [...base.nodes, {id: 'local-new', displayNumber: 3, title: '本地新建'}],
  connections: []
};
const remote = {
  nextNodeNumber: 3,
  nodes: [...base.nodes, {id: 'remote-new', displayNumber: 3, title: '远端新建'}],
  connections: [{id: 'edge-1', from: 'n1', to: 'remote-new', kind: 'flow'}]
};
const result = merge(base, local, remote);
console.log(JSON.stringify(result));
'''
        )
        nodes = {item["id"]: item for item in data["canvas"]["nodes"]}
        self.assertIn("local-new", nodes)
        self.assertIn("remote-new", nodes)
        self.assertEqual(len({item["displayNumber"] for item in nodes.values()}), 4)
        self.assertEqual(data["canvas"]["connections"][0]["id"], "edge-1")

    def test_numbering_preserves_existing_values_and_allocates_monotonically(self):
        data = run_node(
            r'''
const {assignDisplayNumbers, allocateDisplayNumber} = require('./static/js/canvas-sync.js');
const canvas = assignDisplayNumbers({
  nextNodeNumber: 4,
  nodes: [
    {id: 'stable', displayNumber: 2},
    {id: 'duplicate', displayNumber: 2},
    {id: 'missing'}
  ]
});
const allocated = allocateDisplayNumber(canvas);
console.log(JSON.stringify({
  numbers: canvas.nodes.map(node => [node.id, node.displayNumber]),
  allocated,
  nextNodeNumber: canvas.nextNodeNumber
}));
'''
        )
        self.assertEqual(data["numbers"], [["stable", 2], ["duplicate", 4], ["missing", 5]])
        self.assertEqual(data["allocated"], 6)
        self.assertEqual(data["nextNodeNumber"], 7)


if __name__ == "__main__":
    unittest.main()
