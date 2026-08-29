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

    def test_model_switch_restores_each_models_parameter_draft(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
let generation={model:'model-a',mode:'text2video',params:{duration:5,seed:11}};
generation=d.selectGenerationModel(generation,'model-b','image2video');
generation.params={duration:10,quality:'high'};
generation=d.selectGenerationModel(generation,'model-a','text2video');
const restoredA=JSON.parse(JSON.stringify(generation));
generation=d.selectGenerationModel(generation,'model-b','image2video');
console.log(JSON.stringify({restoredA,restoredB:generation}));
""")

        self.assertEqual(data["restoredA"]["params"], {"duration": 5, "seed": 11})
        self.assertEqual(data["restoredA"]["mode"], "text2video")
        self.assertEqual(data["restoredB"]["params"], {"duration": 10, "quality": "high"})
        self.assertEqual(data["restoredB"]["mode"], "image2video")

    def test_director_video_settings_are_isolated_and_submit_only_effective_parameters(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const settings=d.isolatedVideoRunSettings({
  providerId:'ai-money',familyId:'wan-3.0',modelId:'wan-3.0-prime-i2v',mode:'image2video',
  params:{duration:5,seed:'__canvas_unset__',quality:'high'},
  submittedParams:{duration:5,seed:'__canvas_unset__',quality:'high'},
  duration:5,aspectRatio:'16:9',useFrameRoles:true,
  recentSettings:{videoTempShLinks:[{url:'https://example.com/old.mp4'}],videoMultimodal:true,recentOnly:'leak'}
});
console.log(JSON.stringify(settings));
""")

        self.assertEqual(data["videoTempShLinks"], [])
        self.assertFalse(data["videoMultimodal"])
        self.assertFalse(data["_videoMultimodalUserSet"])
        self.assertNotIn("recentOnly", data)
        self.assertNotIn("seed", {key: data[key] for key in data if key != "capabilityParameters"})
        self.assertEqual(data["duration"], 5)
        self.assertEqual(data["quality"], "high")
        self.assertEqual(
            data["capabilityParameters"]["wan-3.0-prime-i2v"]["seed"],
            "__canvas_unset__",
        )
        self.assertTrue(data["videoUseFrameRoles"])

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
const snapped=d.deriveConnectionInputs({id:'c3',type:'connection',startMs:5000,durationMs:1000}, ordinary);
console.log(JSON.stringify({below,exact,snapped}));
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
        self.assertEqual([item["operation"] for item in data["snapped"]["inputs"]], ["last_frame", "first_frame"])

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

    def test_connection_dependency_reports_missing_and_changed_source_results(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const ordinary=[
  {id:'left',type:'ordinary',startMs:0,durationMs:5000,currentResultId:'left-v2',results:[{id:'left-v2',url:'/left-v2.mp4'}]},
  {id:'right',type:'ordinary',startMs:6000,durationMs:5000,results:[]}
];
const bridge={
  id:'bridge',type:'connection',startMs:4000,durationMs:3000,
  results:[{id:'bridge-v1',url:'/bridge.mp4'}],currentResultId:'bridge-v1',
  timelineInputs:[
    {side:'left',sourceClipId:'left',operation:'video_segment',sourceResultId:'left-v1'},
    {side:'right',sourceClipId:'right',operation:'video_segment',sourceResultId:''}
  ]
};
console.log(JSON.stringify(d.connectionDependencyState(bridge,[...ordinary,bridge])));
""")

        self.assertFalse(data["ready"])
        self.assertTrue(data["needsRegeneration"])
        self.assertEqual(data["missing"][0]["sourceClipId"], "right")
        self.assertEqual(data["stale"][0]["previousResultId"], "left-v1")
        self.assertEqual(data["stale"][0]["currentResultId"], "left-v2")

    def test_connection_dependency_requires_at_least_one_timeline_source(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
console.log(JSON.stringify(d.connectionDependencyState(
  {id:'bridge',type:'connection',startMs:9000,durationMs:1000},
  [{id:'ordinary',type:'ordinary',startMs:0,durationMs:5000,results:[{id:'v1',url:'/v1.mp4'}]}]
)));
""")

        self.assertFalse(data["ready"])
        self.assertEqual(data["derived"]["inputs"], [])

    def test_migrates_legacy_minimax_to_single_new_data_source(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const migrated=d.migrateLegacyMinimaxNode({
  id:'old-director',type:'smart-minimax',x:20,y:30,w:1040,h:640,title:'旧工程',
  workflow:'MiniMax_H3.json',minimaxEngine:'runninghub',minimaxRunningHubWorkflowId:'rh-1',
  materials:[{id:'mat-1',kind:'image',url:'/api/materials/mat-1'}],
  refs:{image:[{id:'ref-1',kind:'image',url:'/api/materials/ref-1'}],video:[],audio:[]},
  segments:[{
    id:'seg-1',start:1.5,duration:8,prompt:'镜头一',aspectRatio:'16:9 (Widescreen)',megapixels:0.8,
    refItems:[{id:'ref-1',kind:'image',url:'/api/materials/ref-1'}],
    results:[{id:'result-1',url:'/api/results/result-1.mp4'}],result:{id:'result-1',url:'/api/results/result-1.mp4'}
  }],selectedSegmentId:'seg-1',created_at:123
});
console.log(JSON.stringify(migrated));
""")

        self.assertEqual(data["type"], "smart-minimax-director")
        self.assertEqual(data["directorKind"], "minimax-h3")
        self.assertEqual(data["id"], "old-director")
        self.assertEqual(data["projectName"], "旧工程")
        self.assertEqual(data["selectedClipId"], "seg-1")
        self.assertEqual(data["clips"][0]["startMs"], 1500)
        self.assertEqual(data["clips"][0]["durationMs"], 8000)
        self.assertEqual(data["clips"][0]["prompt"], "镜头一")
        self.assertEqual(data["clips"][0]["results"][0]["id"], "result-1")
        self.assertEqual(data["clips"][0]["currentResultId"], "result-1")
        self.assertEqual(data["adapter"]["engine"], "runninghub")
        self.assertEqual(data["adapter"]["runningHubWorkflowId"], "rh-1")
        self.assertEqual({item["id"] for item in data["assets"]}, {"mat-1", "ref-1"})
        self.assertNotIn("segments", data)
        self.assertNotIn("materials", data)
        self.assertNotIn("refs", data)

    def test_project_registration_and_direct_clip_drop_share_stable_assets(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
let director=d.normalizeDirector({clips:[{id:'clip-a'}]});
director=d.registerProjectAssets(director,[
  {id:'image-a',kind:'image',url:'/api/materials/image-a'},
  {id:'image-a-copy',kind:'image',url:'/api/materials/image-a'}
]);
director=d.attachAssetsToClip(director,'clip-a',[
  {id:'image-a-copy',kind:'image',url:'/api/materials/image-a'},
  {id:'audio-a',kind:'audio',url:'/api/materials/audio-a'},
  {id:'text-a',kind:'text',text:'旁白'}
]);
console.log(JSON.stringify({director,labels:d.referenceLabels(director.clips[0])}));
""")

        self.assertEqual(len(data["director"]["assets"]), 3)
        self.assertEqual(len(data["director"]["clips"][0]["inputRefs"]), 3)
        self.assertEqual(
            [item["mention"] for item in data["labels"]],
            ["@文本1", "@图片1", "@音频1"],
        )
        self.assertEqual(data["labels"][1]["assetId"], "image-a")

    def test_fresh_clip_is_selected_without_inheriting_previous_state(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const source=d.normalizeDirector({
  clips:[{
    id:'clip-a',startMs:0,durationMs:8000,prompt:'旧提示',
    inputRefs:[{id:'image-a',kind:'image',url:'/image-a.png'}],
    generation:{providerId:'provider-a',model:'model-a',mode:'image_to_video',params:{seed:1}},
    results:[{id:'result-a',url:'/result-a.mp4'}],currentResultId:'result-a'
  }],
  selectedClipId:'clip-a'
});
const result=d.appendFreshOrdinaryClip(source,{id:'clip-b',durationMs:8000});
console.log(JSON.stringify(result));
""")

        self.assertEqual(data["selectedClipId"], "clip-b")
        self.assertEqual(data["clips"][1]["startMs"], 8000)
        self.assertEqual(data["clips"][1]["durationMs"], 8000)
        self.assertEqual(data["clips"][1]["prompt"], "")
        self.assertEqual(data["clips"][1]["inputRefs"], [])
        self.assertEqual(data["clips"][1]["generation"]["providerId"], "")
        self.assertEqual(data["clips"][1]["generation"]["model"], "")
        self.assertEqual(data["clips"][1]["generation"]["params"], {})
        self.assertEqual(data["clips"][1]["results"], [])
        self.assertEqual(data["clips"][0]["inputRefs"][0]["id"], "image-a")
        self.assertEqual(data["clips"][0]["prompt"], "旧提示")

    def test_resize_pushes_right_but_shrink_keeps_gap(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const clips=[
  {id:'clip-a',type:'ordinary',startMs:0,durationMs:8000},
  {id:'clip-b',type:'ordinary',startMs:8000,durationMs:8000}
];
const grown=d.resizeOrdinaryClip(clips,'clip-a',{edge:'right',timeMs:15000});
const shrunk=d.resizeOrdinaryClip(grown,'clip-a',{edge:'right',timeMs:8000});
console.log(JSON.stringify({
  grown,
  shrunk,
  extent:d.timelineExtentMs(shrunk,{minimumMs:16000,viewportEndMs:30000,paddingMs:4000})
}));
""")

        self.assertEqual(data["grown"][0]["durationMs"], 15000)
        self.assertEqual(data["grown"][1]["startMs"], 15000)
        self.assertEqual(data["shrunk"][0]["durationMs"], 8000)
        self.assertEqual(data["shrunk"][1]["startMs"], 15000)
        self.assertEqual(data["extent"], 30000)

    def test_move_right_pushes_following_clips_and_move_left_clamps(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const clips=[
  {id:'clip-a',type:'ordinary',startMs:0,durationMs:5000},
  {id:'clip-b',type:'ordinary',startMs:7000,durationMs:5000},
  {id:'clip-c',type:'ordinary',startMs:12000,durationMs:5000},
  {id:'bridge',type:'connection',startMs:4500,durationMs:3000}
];
const movedRight=d.moveOrdinaryClip(clips,'clip-b',10000);
const movedLeft=d.moveOrdinaryClip(clips,'clip-b',1000);
console.log(JSON.stringify({movedRight,movedLeft}));
""")

        self.assertEqual(data["movedRight"][1]["startMs"], 10000)
        self.assertEqual(data["movedRight"][2]["startMs"], 15000)
        self.assertEqual(data["movedRight"][3]["startMs"], 4500)
        self.assertEqual(data["movedLeft"][1]["startMs"], 5000)
        self.assertEqual(data["movedLeft"][0]["startMs"], 0)

    def test_timeline_drag_preview_stays_continuous_until_commit_snap(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
const clips=[
  {id:'clip-a',type:'ordinary',startMs:0,durationMs:8000},
  {id:'clip-b',type:'ordinary',startMs:8000,durationMs:8000}
];
const movePreview=d.moveOrdinaryClip(clips,'clip-b',10550,{snap:false});
const moveCommit=d.moveOrdinaryClip(clips,'clip-b',10550,{snap:true});
const resizePreview=d.resizeOrdinaryClip(clips,'clip-a',{edge:'right',timeMs:7550,snap:false});
const resizeCommit=d.resizeOrdinaryClip(clips,'clip-a',{edge:'right',timeMs:7550,snap:true});
console.log(JSON.stringify({movePreview,moveCommit,resizePreview,resizeCommit}));
""")

        self.assertEqual(data["movePreview"][1]["startMs"], 10550)
        self.assertEqual(data["moveCommit"][1]["startMs"], 11000)
        self.assertEqual(data["resizePreview"][0]["durationMs"], 7550)
        self.assertEqual(data["resizePreview"][1]["startMs"], 8000)
        self.assertEqual(data["resizeCommit"][0]["durationMs"], 8000)
        self.assertEqual(data["resizeCommit"][1]["startMs"], 8000)

    def test_duration_constraint_uses_supported_integer_seconds(self):
        data = run_node("""
const d=require('./static/js/smart-director-core.js');
console.log(JSON.stringify({
  choices:d.constrainDurationMs(7300,{optionsMs:[5000,8000,10000]}),
  rangeLow:d.constrainDurationMs(2400,{minMs:3000,maxMs:12000,stepMs:1000}),
  rangeStep:d.constrainDurationMs(7600,{minMs:3000,maxMs:12000,stepMs:1000}),
  rangeHigh:d.constrainDurationMs(14000,{minMs:3000,maxMs:12000,stepMs:1000})
}));
""")

        self.assertEqual(data["choices"], 8000)
        self.assertEqual(data["rangeLow"], 3000)
        self.assertEqual(data["rangeStep"], 8000)
        self.assertEqual(data["rangeHigh"], 12000)


if __name__ == "__main__":
    unittest.main()
