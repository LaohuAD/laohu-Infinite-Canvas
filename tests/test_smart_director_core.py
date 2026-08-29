import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(source):
    result = subprocess.run(
        ["node", "-e", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class SmartDirectorCoreTests(unittest.TestCase):
    def test_normalizes_director_and_clips_without_losing_drafts(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const result=d.normalizeDirector({
  directorKind:'generic', projectName:'A',
  assets:[{id:'asset-1',kind:'image',url:'/api/materials/asset-1'}],
  clips:[
    {startMs:1200,durationMs:5000,prompt:'镜头一',inputRefs:['asset-1'],generation:{model:'wan-3.0-prime-i2v'}},
    {id:'bridge',type:'connection',startMs:5900,durationMs:1200,disabledInputRefs:['asset-old']}
  ]
});
console.log(JSON.stringify(result));
""")

        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["directorKind"], "generic")
        self.assertEqual(data["clips"][0]["id"], "clip-001")
        self.assertEqual(data["clips"][0]["type"], "ordinary")
        self.assertEqual(data["clips"][0]["generation"]["model"], "wan-3.0-prime-i2v")
        self.assertEqual(data["clips"][1]["disabledInputRefs"], ["asset-old"])

    def test_export_order_uses_midpoint_then_stable_tiebreakers(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const clips=[
  {id:'z',type:'ordinary',startMs:5000,durationMs:2000,createdAt:2,result:{url:'/z.mp4'}},
  {id:'b',type:'connection',startMs:3000,durationMs:2000,createdAt:2,result:{url:'/b.mp4'}},
  {id:'a',type:'ordinary',startMs:3000,durationMs:2000,createdAt:1,result:{url:'/a.mp4'}},
  {id:'first',type:'ordinary',startMs:0,durationMs:3000,result:{url:'/first.mp4'}}
];
const ordered=d.exportEntries('制作 A', clips);
console.log(JSON.stringify(ordered));
""")

        self.assertEqual([item["clipId"] for item in data], ["first", "a", "b", "z"])
        self.assertEqual(
            [item["filename"] for item in data],
            ["制作 A-clip-001.mp4", "制作 A-clip-002.mp4", "制作 A-clip-003.mp4", "制作 A-clip-004.mp4"],
        )
        self.assertEqual(data[2]["type"], "connection")

    def test_connection_inputs_use_frames_below_one_second_and_segments_at_one_second(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const ordinary=[
  {id:'left',type:'ordinary',startMs:0,durationMs:5000},
  {id:'right',type:'ordinary',startMs:6000,durationMs:5000}
];
const below=d.deriveConnectionInputs({id:'c1',type:'connection',startMs:4001,durationMs:2798}, ordinary);
const exact=d.deriveConnectionInputs({id:'c2',type:'connection',startMs:4000,durationMs:3000}, ordinary);
console.log(JSON.stringify({below,exact}));
""")

        self.assertEqual(data["below"]["inputs"][0]["operation"], "last_frame")
        self.assertEqual(data["below"]["inputs"][1]["operation"], "first_frame")
        self.assertEqual(data["below"]["startMs"], 5000)
        self.assertEqual(data["below"]["endMs"], 6000)
        self.assertEqual(data["exact"]["inputs"][0]["operation"], "video_segment")
        self.assertEqual(data["exact"]["inputs"][0]["startMs"], 4000)
        self.assertEqual(data["exact"]["inputs"][0]["endMs"], 5000)
        self.assertEqual(data["exact"]["inputs"][1]["operation"], "video_segment")
        self.assertEqual(data["exact"]["inputs"][1]["startMs"], 6000)
        self.assertEqual(data["exact"]["inputs"][1]["endMs"], 7000)

    def test_connection_inputs_support_one_sided_and_mixed_overlap(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const ordinary=[
  {id:'left',type:'ordinary',startMs:0,durationMs:5000},
  {id:'right',type:'ordinary',startMs:6500,durationMs:5000}
];
const leftOnly=d.deriveConnectionInputs({id:'c1',type:'connection',startMs:3500,durationMs:2500}, ordinary);
const mixed=d.deriveConnectionInputs({id:'c2',type:'connection',startMs:3500,durationMs:3800}, ordinary);
console.log(JSON.stringify({leftOnly,mixed}));
""")

        self.assertEqual([item["side"] for item in data["leftOnly"]["inputs"]], ["left"])
        self.assertEqual(data["leftOnly"]["inputs"][0]["operation"], "video_segment")
        self.assertEqual([item["operation"] for item in data["mixed"]["inputs"]], ["video_segment", "first_frame"])
        self.assertEqual(data["mixed"]["endMs"], 6500)

    def test_rejects_overlapping_connection_clips(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
console.log(JSON.stringify({
  overlap:d.connectionClipConflict(
    {id:'new',type:'connection',startMs:4500,durationMs:2000},
    [{id:'old',type:'connection',startMs:6000,durationMs:1000}]
  ),
  touching:d.connectionClipConflict(
    {id:'new',type:'connection',startMs:4000,durationMs:2000},
    [{id:'old',type:'connection',startMs:6000,durationMs:1000}]
  )
}));
""")

        self.assertEqual(data["overlap"], "old")
        self.assertEqual(data["touching"], "")


if __name__ == "__main__":
    unittest.main()
