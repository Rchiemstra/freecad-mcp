#!/usr/bin/env python3
"""Package unchanged Stage 2a design and derived evidence, without staging files."""
import json,shutil,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];O=ROOT/'demo-out';E=ROOT/'examples/strawberry-picker'
E.mkdir(exist_ok=True,parents=True);(E/'parts').mkdir(exist_ok=True);(E/'evidence').mkdir(exist_ok=True)
r=json.loads((O/'stage2/checks.json').read_text());f=json.loads((O/'stage2/fem.json').read_text());m=json.loads((O/'stage2/design-manifest.json').read_text())
shutil.copyfile(O/'strawberry-head-v2.FCStd',E/'strawberry-head.FCStd')
shutil.copyfile(O/'stage2/fem.FCStd',E/'evidence/jaw-fem.FCStd')
for src,dst in [('checks.json','stage2-checks.json'),('design-manifest.json','design-manifest.json'),('fem.json','fem.json')]:shutil.copyfile(O/'stage2'/src,E/'evidence'/dst)
shutil.copyfile(O/'stills2/design-notes.md',E/'evidence/design-notes.md')
for name in m['printed']:
 for ext in ['step','stl']:shutil.copyfile(O/'files'/f'{name}-v2.{ext}',E/'parts'/f'{name}.{ext}')
checks=[]
def add(name,tool,args,result,source='Stage 2a retained evidence'):
 checks.append({'check':name,'mcp_tool':tool,'args_summary':args,'result':result,'source':source})
for n,v in r['geometry_checks'].items():add('valid solid '+n,'validate_geometry',{'obj_name':n},v)
for n,v in r['poses'].items():
 ds={obj:entry['distance']['distance'] for obj,entry in v['clearances'].items()}
 cs={obj:entry['intersection']['volume']['volume_mm3'] for obj,entry in v['clearances'].items()}
 add(n,'measure_distance; common_volume_along_path',{'moving_object':'HeadEnvelope','obstacle_objects':list(ds),'samples':[{'x':0,'y':0,'z':0}],'pose':{k:x for k,x in v.items() if k!='clearances'}},{'distances_mm':ds,'minimum_distance_mm':min(ds.values()),'common_volumes_mm3':cs})
for n,v in r['paths'].items():add(n+' path','common_volume_along_path',{'moving_object':'HeadEnvelope','points':v['points'],'frame':v['frame'],'obstacles':['NeighbourLBerry','NeighbourLCap','NeighbourLStem','NeighbourRBerry','NeighbourRCap','NeighbourRStem','Truss','TargetBranch','NeighbourLBranch','NeighbourRBranch']},{'sample_count':len(v['results']),'max_common_volume_mm3':max(x['max_common_volume_mm3'] for x in v['results'])})
for i,v in enumerate(r['travel']):add('mechanism travel '+str(i),'common_volume_along_path',{'jaw_angle':v['jaw_angle'],'cutter_angle':v['cutter_angle'],'pairs':list(v['checks'])},{'max_common_volume_mm3':max(x['volume']['volume_mm3'] for x in v['checks'].values()),'intentional_pin_contacts_excluded':True})
add('blade crosses stem','common_volume_along_path',{'cutter_angles_deg':[13,9,4,0,-4,-9,-13],'moving_object':'World_HobbyBlade','obstacle_objects':['World_TargetStem']},{'volumes_mm3':[v['intersection']['volume']['volume_mm3'] for v in r['blade_crossing']]})
for tag in ['Clamp','Cut']:add(tag+' force budget','spreadsheet_get_cells; execute_code',{'sheet_name':'Dims','cells':r['force_cells']['cells'],'angle_step_deg':.1},{'minimum_N':min(v['force'] for v in r['transmission'][tag]),'required_N':10 if tag=='Clamp' else 15,'max_link_residual_mm':max(v['link_residual'] for v in r['transmission'][tag])})
add('original narrow clash','measure_volume; execute_code',{'native_archived_shapes':r['baseline_archive']['copies']},r['baseline_archive']['whole_head_common_mm3'])
add('jaw FEM','create_object; run_fem_analysis; execute_code',{'analysis_name':'JawAnalysis','load_N':10,'fixture':'M3 pin bore fixed','material':'isotropic PLA E=3500 MPa, nu=0.36, yield=50 MPa','mesh_mm':[1.5,3],'element_order':1},f['results'])
add('FEM matches changed jaw','execute_code',{'compare':'MovingJaw.Shape.Volume versus FEM source volume'},r['fem_geometry_match'])
add('dimension binding','audit_hardcoded_dimensions; execute_code',{'document':'strawberry_head_v2'},r['expression_audit_readback'])
add('blade/pad gap and attachment','measure_distance; execute_code',{'parts':'all Category=printed/bought','clearance':'BladeZ minus V2Dims.MovingHeight'},r['realism'])
add('cable clearances','common_volume_along_path',{'moving_objects':['ClampCableRoute','CutCableRoute'],'obstacles':'other physical parts excluding servo housings'},r['cable_hardware_checks'])
add('mass and centre of mass','measure_volume; center_of_mass; spreadsheet_get_cells',{'sheet_name':'V2Mass','PLA_fill_fraction':.4,'servo_allowance_g_each':9},{'breakdown_g':r['total_mass'],'weighted_com':r['weighted_com'],'solid_envelope_g':130.38})
add('native BOM','execute_code',{'properties':['Category','MaterialNote']},r['parts_list'])
add('ten printed export pairs','export_step; export_stl',{'objects':m['printed'],'mesh_deviation_mm':.08},{'files':[str(p.relative_to(E)) for p in sorted((E/'parts').iterdir())]})
inspection=O/'stage3/export-inspection.json'
if inspection.exists():
 imported=json.loads(inspection.read_text())
 imported=json.loads(imported['message'].split('Output: ',1)[1].strip())
 assert len(imported)==11 and all(v['valid'] and v['matches'] for v in imported)
 add('head assembly export','export_step',{'selection':'physical head parts; exclude scene, fruit, wrist reference and measurement helpers','destination':'examples/strawberry-picker/assembly.step'},imported[0],'Stage 2b real export and native readback')
 add('STEP imports match native solids','execute_code',{'reader':'Part.Shape.read','files':[v['file'] for v in imported],'comparison':'validity and native solid volume'},imported,'Stage 2b native STEP inspection')
add('scripted pick motion','execute_code; spreadsheet_set_cells; set_expression',{'poses':['approach','clamp','cut','withdraw','tray'],'easing':'smoothstep','native_placement_correction':'retained Stage 2a rotor/body synchronization'},{'contact_physics':False,'tray_transfer_collision_checked':False,'capture':'real GUI; idle waiting trimmed'},'Stage 2b scripted replay')
poses=O/'stage3/wrist-poses.jsonl'
if poses.exists():
 records=[json.loads(line) for line in poses.read_text().splitlines()]
 add('rigid wrist replay reference','set_expression; execute_code',{'objects':['RobotWrist','WristPilotBoss'],'expressions':['Motion.HeadX','Motion.HeadY','Motion.HeadZ'],'compare':'wrist and adapter global placement'}, {'checked_refreshes':len(records),'maximum_offset_mm':max(v['offset_mm'] for v in records),'maximum_pilot_error_mm':max(v['pilot_error_mm'] for v in records),'maximum_rotation_error_rad':max(v['rotation_error_rad'] for v in records),'native_print_geometry_changed':False},'Stage 2b presentation rework')
reference=O/'stage3/reference-checkpoint.json'
if reference.exists():
 proof=json.loads(reference.read_text());assert proof['result']=='PASS' and proof['before']==proof['after']
 shutil.copyfile(reference,E/'evidence/reference-checkpoint.json')
 add('native wrist reference bindings','set_expression; save_document_as; execute_code',{'objects':['RobotWrist','WristPilotBoss'],'compare':'clean input versus saved reference-bound checkpoint'},proof,'Stage 2b presentation rework; printed geometry and sheet contents unchanged')
remesh=O/'stage3/replay-fem-remeshed.json'
if remesh.exists():
 shutil.copyfile(remesh,E/'evidence/fem-remesh.json')
 add('fresh coarse remesh variation','run_fem_analysis; execute_code',{'analysis_name':'JawAnalysis','note':'The public tool regenerates a mesh; the canonical comparison retains the Stage 2a mesh.'},json.loads(remesh.read_text()),'Stage 2b additional remesh; not the canonical comparison')
for name,tool in [('replay-build.json','spreadsheet_set_cells; recompute_document; execute_code'),('replay-clearance.json','measure_distance; common_volume_along_path'),('replay-narrow.json','measure_volume; common_volume_along_path'),('replay-fem.json','execute_code')]:
 p=O/'stage3'/name
 if p.exists():add(name,tool,{'see':'scripts/demo/replay_driver.py'},json.loads(p.read_text()),'Stage 2b live replay')
verification={'project':'freecad-mcp','runtime':'the companion FreeCAD fork','fork_revision':'a084e95695','addon_revision':'227db9d','addon_mount':'/mcpfix','replay':'Scripted replay; real MCP tools on the companion FreeCAD fork; no language model during replay. Saved parametric checkpoint regenerated, not a fresh conversational design. Idle waiting trimmed. Caption/readback panels restored in post; CAD viewport pixels unchanged.','forces':'forces from datasheets + FEM, not measured','checks':checks,'limitations':['Discrete collision samples; no continuous collision certificate','No physical grasp or cutting test','Tray transfer is a placement preview outside the tested approach/withdraw paths','Coarse isotropic FEM: print anisotropy, fatigue and mesh convergence untested','Sliced mass and cable strain relief unresolved','Controller and rear connector outside modeled head; no sensor or guarded enclosure implied']}
(E/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
# Import prompts without opening an MCP transport.
import ast
module=ast.parse((ROOT/'scripts/demo/replay_driver.py').read_text())
prompts=next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPTS' for t in n.targets))
(E/'prompts.md').write_text('# Prompts shown in the replay\n\nScripted replay using real MCP tools on the companion FreeCAD fork. No language model during replay.\n\n'+''.join(f'## {i}. {title}\n\nYou: {prompt}\n\nWhat this proves: {proof}\n\n' for i,(title,prompt,proof) in enumerate(prompts,1)))
rows=[]
for name,p in r['poses'].items():rows.append(f"| {name.replace('_',' ')} | `measure_distance`, `common_volume_along_path` | ≥{min(x['distance']['distance'] for x in p['clearances'].values()):.3f} mm; common 0 mm³ |")
text='''# Strawberry picking head

A small, spreadsheet-driven head holds a strawberry stem, cuts above the pad,
and withdraws the fruit. Ten printed parts carry two servo drives and a replaceable
39 mm blade. The native model includes the head, wrist reference, cluster and tray.

This is a **scripted replay**, with **real MCP tools on the companion FreeCAD fork**
and **no language model during replay**. It regenerates the retained parametric
checkpoint, changes/restores a jaw dimension and cluster spacing, then reveals the parts. GUI takes are joined at fixed poses and chapter boundaries. Idle waiting is trimmed; motion uses eased
spreadsheet poses. The relocated-tray transfer is an unvalidated placement preview.
freecad-mcp is its own project. The wrist reference and its pilot follow the head
in the native file; printed geometry and spreadsheet values retain the input design.
Caption/readback panels are restored in post to avoid GUI redraw damage; CAD
viewport pixels come from the real GUI capture.

**Forces from datasheets + FEM, not measured.** Nothing here reports a physical pick.

![Whole story](../../assets/strawberry-picker.gif)

[Prompts shown](prompts.md) · [Per-check tool arguments and results](verification.json) ·
[Native parametric model](strawberry-head.FCStd) · [Head assembly STEP](assembly.step) ·
[Ten per-part STEP/STL pairs](parts/) · [Retained design notes and gaps](evidence/design-notes.md)

## Parts to make and buy

| Part | Count | Material / purchase note |
|---|---:|---|
| WristAdapter, DriveHousingReady, NoseFrameReady | 1 each | PLA structure |
| MovingJaw, BladeLever, BladeClamp | 1 each | PLA working parts |
| ClampLink, CutLink | 1 each | PLA links |
| FixedTPU, MovingTPU | 1 each | TPU replaceable pads; adhesive backing |
| Servo drive | 2 | 9 g allowance each; 176 N mm stall torque input; confirm real capability |
| Servo horn | 2 | 6 mm radius; compatible with the chosen servo |
| Replaceable steel blade | 1 | 39 mm envelope; confirm tang, thickness and edge position |
| Wrist flange screw | 4 | Model uses M6 clearance; match engagement to the actual wrist |
| Column bolt | 2 | Match modeled housing and wrist plate; heads seat underneath |
| Nose frame bolt and nut | 2 sets | Match the modeled bores |
| Servo tab M2 screw and captive nut | 4 sets | Two per servo |
| Jaw/cutter M3 pivot pin and locknut | 2 sets | Include modeled spacers/shim; check free movement |
| Link pin and retaining head | 4 sets | Two per link; verify retention |
| Blade-clamp M2 screw and nut | 2 sets | Seat the blade securely |
| Servo cable route | 2 | 2 mm envelope in 2.5 mm passages; strain relief still to specify |

Fastener solids are simplified envelopes, not thread models or a complete purchase
specification. Resolve lengths and retention against actual bought parts before assembly.
The exhaustive native physical-part list and attachment witnesses are in
[verification.json](verification.json) and the [design notes](evidence/design-notes.md).

## Print notes

Print the eight rigid parts in PLA and the two pads in TPU. Use the XY flat face for
all except NoseFrameReady, which uses the rear Y face; support its transverse bores.
Minimum specified printed walls are 2 mm, with about 2.4 mm principal bearing
ligaments. MovingJaw is 5.7 mm thick; BladeLever is 3 mm; BladeClamp is 2.4 mm.
These are design witnesses, not a global wall-thickness or overhang certificate.

The per-part files retain native assembly coordinates. Orient each flat face on the
bed in the slicer. The STL mesh deviation is 0.08 mm. Confirm bore fits, blade seating,
cable passages, nut access, pad adhesion and unobstructed travel before fitting a blade.
Use at least 2 mm walls and establish a practical infill in the slicer. The 40% PLA
mass convention is only an estimate; thin links and backings will be substantially solid.

## Results and their scope

Nominal fruit is 30 × 35 mm; the actual spline envelope is 30.198 × 30.198 × 35.180 mm.
The nominal 10 mm setting therefore gives about 9.802 mm actual fruit spacing.
The nose fix removes the unused lower cheek extensions and shortens the carrier by
4 mm. Bridge, anvil, pivot forks, drive geometry, pads and blade are retained.

| Check | Real MCP tool | Result |
|---|---|---|
| Printed native solids | `validate_geometry` | All ten valid and closed; one solid each |
'''+ '\n'.join(rows)+'''
| Approach and withdrawal, 15/10 mm | `common_volume_along_path` | 24 samples total; 0 mm³ common |
| Mechanism travel | `common_volume_along_path` | Eight poses; 0 mm³ unintended common; pin contacts excluded |
| Blade crosses the target stem | `common_volume_along_path` | 0 to 2.212 mm³ common during cut; crossing established |
| Original 10 mm nose | `measure_volume`, `execute_code` | Fruit clash 583.615 / 583.602 mm³; neighbouring stem 3.195 mm³ |
| Blade underside to moving pad | `execute_code` | 6.7 − 5.7 = 1.0 mm |
| Cable to housing and hardware | `common_volume_along_path` | 0 mm³ common |
| Force budget | `spreadsheet_get_cells`, `execute_code` | Minimum clamp 23.138 N / cut 33.417 N; need 10 / 15 N |
| Changed jaw FEM | `create_object`, `run_fem_analysis`, `execute_code` | 1.367 MPa; 0.016613 mm; yield SF 36.57; 367 nodes / 1063 elements |
| FEM matches changed jaw | `execute_code` | Source and current jaw volume match |
| Dimension binding | `audit_hardcoded_dimensions`, `execute_code` | 530 reported dimensional constraints expression-bound; 0 unbound findings |
| Mass estimate | `measure_volume`, `center_of_mass`, `spreadsheet_get_cells` | 83.84 g at retained fill convention; 130.38 g all-solid envelope |
| Parts and print exports | `execute_code`, `export_step`, `export_stl` | Native BOM; head assembly STEP; ten STEP/STL pairs |

The force input is 176 N mm stall torque, derated by 2 to 88 N mm. The ideal force
is working torque / 6 mm horn × 24 mm input arm / output arm (15 mm jaw, 10.5 mm
cutter). Ideal values are 23.467 N / 33.524 N. The reported minima include linkage
transmission correction sampled every 0.1°. **Forces from datasheets + FEM, not measured.**

FEM uses the actual changed jaw with the M3 bore fixed and 10 N on the pad backing:
isotropic PLA, E = 3500 MPa, Poisson ratio 0.36, yield = 50 MPa, first-order 1.5–3 mm
mesh. The stress view uses actual solver nodal values. The setup and results are
retained in [jaw-fem.FCStd](evidence/jaw-fem.FCStd) and [fem.json](evidence/fem.json).

A fresh coarse remesh during recording made 1,061 elements and gave 1.379 MPa
and 0.016680 mm. The video instead re-solves the retained 1,063-element mesh,
reproducing **1.3673729 MPa and 0.0166125 mm** through the actual solver. This keeps
the Stage 2a comparison fixed; the mesh variation is recorded in
[fem-remesh.json](evidence/fem-remesh.json). No convergence study is claimed.

## Gaps left

No physical grip or cutting test has been done. Discrete collision samples do not
prove continuous clearance. The final tray transfer lies outside the tested paths;
its animation does not simulate contact, dropping or gravity. Expression-driven
poses do not claim a solved dynamic assembly. Fruit envelopes omit real variation
and compliance, leaves, and dense plant clutter.

Coarse isotropic FEM does not establish layer strength, fatigue, blade sharpness or
mesh convergence. Establish the actual sliced mass, print orientation and fixture
strength. Cable strain relief, servo controller and rear connector remain outside the
modeled head boundary. No sensor, controller or guarded operating enclosure is implied.
Native solid checks and attachment distances do not prove joint strength or retention.

## Bench test plan

1. **Free travel:** assemble without the blade; move both drives through their full
   ranges by hand, then at low drive effort. Check pins, nuts, cables, pad alignment
   and the 1.0 mm blade-to-pad gap. Record any binding or loosening.
2. **10 N grip:** clamp a dummy stem and pull with a spring scale to 10 N. Record
   slipping, pad damage and servo behaviour over repeated holds.
3. **15 N cut:** measure cutting force on real stems with a spring scale, aiming to
   establish a 15 N requirement. Record stem size, blade condition and failed cuts.
4. **Dummy clusters:** test at 15 mm, then 10 mm nominal spacing. Complete approach,
   clamp, cut, withdrawal and tray transfer; watch the neighbouring fruit, calyces,
   stems and cables. Record bruising, contact and loss of fruit.
5. **Closer berries:** reduce the spacing gradually below 10 mm. Record the first
   contact or failed pick, including fruit dimensions and pose; use that measured
   limit to set the next design requirement.

The fixture, blade handling and drive effort must suit the bench setup. These steps
are a proposed test plan, not completed results.

## Reproduce

See [scripts/demo/README.md](../../scripts/demo/README.md). The replay uses one
bounded container and one GUI; there are no builds. Both overview and chapter GIFs
are condensed previews. The full local video is `demo-out/strawberry-picker.mp4`
and is deliberately excluded from the paths to stage.
'''
(E/'README.md').write_text(text)
# Only replace the existing demo section; retain installation/project documentation.
p=ROOT/'README.md';s=p.read_text();a=s.index('## Demo');b=s.index('## Install addon',a)
s=s[:a]+'''## Demo: a strawberry picker

![Strawberry picker story](assets/strawberry-picker.gif)

A small head holds the stem, cuts above the pad, and withdraws the fruit.<br>
A tight cluster reveals a clash; a shorter nose clears the checked samples.<br>
Force estimates, jaw FEM and print files make the next bench test concrete.

Scripted replay: real MCP tools on the companion FreeCAD fork, with no language
model during replay. Forces from datasheets + FEM, not measured. Tray transfer is
an unvalidated placement preview; idle waiting is trimmed. Caption/readback panels
are restored in post; CAD viewport pixels come from the real GUI capture.

| Chapter | Preview | MCP tool and what it proved |
|---|---|---|
| 3 · Pick motion | ![Pick motion](assets/strawberry-picker-03-motion.gif) | `spreadsheet_set_cells`: spreadsheet poses move the parts through the scripted pick poses; tray transfer is a preview. |
| 5 · Tight cluster | ![Tight cluster](assets/strawberry-picker-05-clearance.gif) | `measure_volume`, `common_volume_along_path`: yellow original clash, then 0 mm³ common in the checked samples. |
| 6 · Jaw strength | ![Jaw FEM](assets/strawberry-picker-06-fem.gif) | `execute_code`: real solver replay on the retained mesh, 1.367 MPa at a 10 N pad load. |

[Model, parts, prompts, results and bench test plan](examples/strawberry-picker/)

'''+s[b:];p.write_text(s)
media_path=O/'stage3/media-report.json'
if media_path.exists():
 media=json.loads(media_path.read_text());seconds=media['duration_seconds']
 sizes=media['gifs_bytes']
 line=('Local video: **%d:%04.1f**, seven chapters. GIFs: overview **%.2f MB**; motion **%.2f MB**; tight cluster **%.2f MB**; FEM **%.2f MB**. All GIFs are 960 px at 10 fps.'%(int(seconds//60),seconds%60,*(sizes[n]/1_000_000 for n in ['strawberry-picker.gif','strawberry-picker-03-motion.gif','strawberry-picker-05-clearance.gif','strawberry-picker-06-fem.gif'])))
 p.write_text(p.read_text().replace('[Model, parts, prompts, results and bench test plan](examples/strawberry-picker/)','[Model, parts, prompts, results and bench test plan](examples/strawberry-picker/)\n\n'+line))
 with (E/'README.md').open('a') as dest:dest.write('\n'+line+'\n')
 guide=ROOT/'scripts/demo/README.md';guide_text=guide.read_text().split('\n<!-- generated media summary -->')[0]
 guide.write_text(guide_text.rstrip()+'\n\n<!-- generated media summary -->\n'+line+'\n')
 shutil.copyfile(media_path,E/'evidence/replay-media.json')
 review=O/'stage3/visual-review.json'
 if review.exists():shutil.copyfile(review,E/'evidence/presentation-review.json')
print('Packaged',sum(p.stat().st_size for p in E.rglob('*') if p.is_file()),'bytes')
