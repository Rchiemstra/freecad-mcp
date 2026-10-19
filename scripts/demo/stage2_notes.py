"""Write the design gate's evidence report from the recorded native MCP results."""
import json,hashlib,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'demo-out/stage2';ST=ROOT/'demo-out/stills2'
R=json.loads((OUT/'checks.json').read_text());F=json.loads((OUT/'fem.json').read_text());M=json.loads((OUT/'design-manifest.json').read_text())
lines=['# Design gate 2 — strawberry picking head','',
'freecad-mcp is its own project. The CAD runtime is the companion FreeCAD fork. This gate produces stills and CAD files only. Stage 1 sources and checks remain in scripts/demo/; no builds, video, GIFs, commits or pushes were performed.','',
'Runtime: the companion FreeCAD fork `a084e95695`; freecad-mcp add-on `227db9d`, mounted at `/mcpfix`. The FEM-capable image was run with `--rm --memory=2g --memory-swap=2g`, one FreeCAD process and no parallel CAD worker. The pre-FEM memory record shows 2180 MB available.','',
'## Design changes','',
'- Smooth native spline revolutions replace the segmented fruit profiles. Each calyx has six pointed sepals and a short 4 mm stem stub; the long, connected picking pedicel is retained. Display deviation is 0.025%.',
'- The nose cheeks now stop at Z = −4 mm instead of −28 mm. The bridge, anvil ties, pivot forks and frame bolts remain connected. Removing the unused extensions clears the fruit without deleting the working nose.',
'- The cutter carrier ends at local X = −26 mm instead of −30 mm. Both blade clamp screw centres remain within the carrier. The 39 mm bought blade, stem crossing, pads and drive geometry are retained.',
'- The moving jaw, backing and moving pad end at Z = 5.7 mm. The blade begins at Z = 6.7 mm, leaving the labeled 1.0 mm vertical clearance. The fixed anvil remains at Z = 6.6 mm for the bypass cut.',
'- Continuous 2 mm servo leads reach the rear pigtail through modeled 2.5 mm passages. The cutter lead bypasses the clamp servo screw; the minimum specified ligament at the column bolt is 2.05 mm. Added screw heads seat against the underside of the housing at the two column bolts.','',
'## Recorded numbers','']
lines += ['Working torque: `T_work = 176 / 2 = 88 N mm`. The spreadsheet and geometry share a 6 mm horn radius, 24 mm input arm, 15 mm jaw output arm and 10.5 mm cutter output arm.',
'Ideal force: `F = T_work / horn_radius * input_arm / output_arm`, giving 23.467 N clamp and 33.524 N cut. The swept budget multiplies this by `abs(sin(link_angle - follower_arm_angle)) / abs(sin(link_angle - horn_angle))`; the minima below include that transmission correction.','']
for tag in ['Clamp','Cut']:
 data=R['transmission'][tag];minimum=min(x['force'] for x in data);required=10 if tag=='Clamp' else 15
 lines.append(f'- {tag} force minimum: **{minimum:.3f} N**, **{minimum/required:.3f}×** required; sampled at 0.1° increments over the full commanded range. Stall torque 176 N mm, working torque 88 N mm (2× derating).')
baseline={n:{'volume_mm3':v} for n,v in R.get('baseline_archive',{}).get('whole_head_common_mm3',{}).items()} or R.get('baseline_narrow_volumes',{})
lines.append('- Original smooth-fruit baseline at 10 mm spacing: '+', '.join(f'{n}: {v["volume_mm3"]:.6f} mm³' for n,v in baseline.items())+'.')
f=F['results'];lines+= [f'- Changed jaw FEM: **{f["max_von_mises_MPa"]:.6f} MPa**, **{f["max_displacement_mm"]:.6f} mm**, yield SF **{f["safety_factor"]:.2f}**; {f["mesh_nodes"]} nodes / {f["mesh_volumes"]} solid elements.',
'- FEM uses the actual changed jaw, 10 N on its pad backing, the M3 pin bore fixed, isotropic PLA E = 3500 MPa, ν = 0.36, yield = 50 MPa. Mesh 1.5–3 mm, first order; real solver result data and input files are retained in stage2/fem_solver/.',
'- The stress view colors the solver mesh from the result object’s nodal von Mises values. The MPa legend uses the same range; no beam card or invented contour is used.','']
berry=R['realism']['berry_bbox_mm']
lines.append('- Nominal fruit is 30 × 35 mm; the smooth interpolation measures %.3f × %.3f × %.3f mm. All checks use that slightly larger actual shape. Thus the 10 mm nominal setting tests about %.3f mm minimum fruit-to-fruit spacing.'%(*berry,40-berry[0]))
mass=R['total_mass'];lines.append('Estimated head mass using the retained Stage 1 effective 40%% PLA fill convention: **%.2f g**. This is a CAD/BOM estimate, not a weighed part.'%mass['total_g'])
lines.append('Estimated material-weighted centre of mass (world mm): `'+json.dumps(R['weighted_com'])+'`.')
solid_pla=mass['printed_PLA_g']/.4;solid_total=mass['total_g']+solid_pla-mass['printed_PLA_g']
lines+=['The all-solid PLA envelope estimate is **%.2f g**. A slicer with ≥2 mm walls is needed to establish a more accurate mass; thin links and pad backings will be substantially solid. Purchased masses include simplified fastener envelopes and 9 g per servo.'%solid_total,'', '```json',json.dumps(mass,indent=2),'```','','## Per-check MCP tools and results','','| Check | MCP tool | Result |','|---|---|---|']
lines.append('| Native printed solids | validate_geometry | '+', '.join(n+': valid' for n,v in R['geometry_checks'].items())+' |')
for pose,data in R['poses'].items():
 vals=data['clearances'];mind=min(v['distance']['distance'] for v in vals.values());maxvol=max(v['intersection']['volume']['volume_mm3'] for v in vals.values())
 lines.append(f'| {pose}: fruit, calyx, neighbour stems | measure_distance; common_volume_along_path at current pose | minimum {mind:.6f} mm; max common {maxvol:.9f} mm³ |')
for name,data in R['paths'].items():
 results=data['results'];maxvol=max(v['max_common_volume_mm3'] for v in results);lines.append(f'| {name} | common_volume_along_path | {len(results)} samples; max common {maxvol:.9f} mm³ |')
travel=R['travel'];maxvol=max(v['volume']['volume_mm3'] for p in travel for v in p['checks'].values())
lines.append(f'| Linkage / jaw / cutter / housing travel | common_volume_along_path; eight poses including full cut | max common {maxvol:.9f} mm³, intentional pin contacts excluded |')
lines.append('| Blade crosses target stem | common_volume_along_path at seven cutting angles | '+', '.join(f'{p["angle"]}°: {p["intersection"]["volume"]["volume_mm3"]:.6f} mm³' for p in R['blade_crossing'])+' |')
lines+=['| Force formulas and geometry | spreadsheet_get_cells; execute_code readback; linkage circle intersections | Force budget above; exact cells and residuals in checks.json |',
'| Dimension audit | audit_hardcoded_dimensions; execute_code ExpressionEngine readback | 530 reported dimensional constraints are expression-bound; 0 unbound findings. Raw audit false positives retained in checks.json |',
'| FEM | create_object (analysis/material/constraints/mesh); run_fem_analysis; execute_code result readback | '+str(f['mesh_volumes'])+' solid elements; actual result values above |',
'| Mass and BOM | measure_volume; center_of_mass; spreadsheet_get_cells; execute_code Category/MaterialNote enumeration | Updated mass above; full part list below |',
'| Printed exports | export_step; export_stl | Ten separate STEP and STL pairs in ../files/, mesh deviation 0.08 mm |','',
'Paths use a world-space head regenerated at zero translation, then absolute placements. Each sample checks both neighbouring fruit, calyces and stems, the truss and branches. Approach Z = 15, 12, 9, 6, 3, 0 mm; withdrawal Y = 0…−25 mm and Z = 0…20 mm. These are discrete samples, not a continuous collision certificate. The four poses are approach, clamp, cut and withdrawal, at both 15 and 10 mm nominal spacing. Target fruit is moved with the head after cutting. Intentional pad/stem contact is excluded from the obstacle list.','',
'## Realism review — every physical part','',
'All physical parts were enumerated from native Category/MaterialNote properties; native shape validity, solids and intended attachment are recorded below. A small gap or contact establishes geometric attachment only; it does not validate joint strength.','',
'| Part | Type / material | Valid / solids | Intended attachment | Distance mm |','|---|---|---|---|---:|']
for p in R['realism']['parts']:
 lines.append(f'| {p["name"]} | {p["category"]} / {p["material"]} | {p["valid"]} / {p["solids"]} | {p["nearest_part"]} | {p["nearest_distance_mm"]:.4f} |')
lines+=['','Cable/housing common-volume readback: `'+json.dumps(R['realism']['cable_housing_common_mm3'])+'` mm³.','',
'| Printed part | Minimum specified material | Flat print face and attachment |','|---|---|---|',
'| WristAdapter | 6 mm plate, ≥2 mm around holes | XY underside; four flange screws and two column bolts |',
'| DriveHousingReady | 3 mm floor; 2 mm below cable channel; ≥2.4 mm main walls | XY underside; integral columns/pockets; servo tab screws and nose bolts |',
'| NoseFrameReady | 2 mm fork plates; ≥2.4 mm principal ligaments | Rear Y face; integral anvil/ties; two frame bolts and retained M3 pivot pins |',
'| MovingJaw | 5.7 mm thick; ≥2.4 mm bearing ligament | XY face; M3 axle with spacer and locknut, retained link pin |',
'| BladeLever | 3 mm thick; ≥2 mm hole-edge material | XY face; M3 axle and locknut, retained link pin |',
'| BladeClamp | 2.4 mm thick; 2.3 mm at screw edge | XY face; two M2 screws and nuts |',
'| ClampLink / CutLink | 2 mm thick; 2.3 mm bore ligament | XY face; captive pins and heads |',
'| FixedTPU / MovingTPU | 2 mm thick | Flat adhesive backing; replaceable cartridges |','',
'These are design dimension witnesses and visual/native-solid checks, not an automatic global wall-thickness or overhang certification. Nose transverse bores need print supports. The pads use adhesive; the adhesive allowance is in the mass estimate. Bought blade and hardware may be thinner than 2 mm; they are not printed parts.','',
'## Failures, recovery and remaining gaps','',
'- Reopening Stage 1 produced internal document name strawberry_head; the driver now handles open_document without injecting doc_name, and the Stage 2 wrapper uses the observed document name.',
'- Animated camera calls affected the top/section captures; explicit camera rotations with navigation animation disabled fixed them. The final contact detail uses the actual anvil cropped to the contact region, with the rear drive and pivot hardware hidden. Target-specific readiness and an explicit recompute after presentation prevent unrelated documents from blocking capture.',
'- Coincident surfaces obscured the original clash colors. The original nose is shown as a wire outline; the actual native common solids use a yellow material override and a small depth bias. This changes rendering only, not their measured volume.',
'- Adding optional FEM/minimum-wall properties to existing bodies was refused by the native stable-boundary guard. The optional properties were omitted; existing PrintFace metadata was updated and the real FEM/current-jaw volume match is recorded in checks.json.',
'- The first viewport pass hid the assembly parent and retained old per-face colors. The renderer now enables parent groups first and then applies an explicit visibility list and face colors. Baseline copies come from the saved native pre-fix model, with parent placements preserved.',
'- Replacing the first Qt renderer from a worker thread caused a Qt timer error and closed FreeCAD. The bounded container was restarted, Stage 1 reopened, and fruit changes reapplied once to the fresh document. New renderer retirement occurs on the GUI thread.',
'- A legacy Dims edit returned SPREADSHEET_SET_CELLS_TRANSPORT_UNCERTAIN and stayed in notification replay. The process was stopped without saving that edit, and the known pre-edit checkpoint was reopened. The successful final design uses a small separate V2Dims sheet and explicit feature bindings; its dimensions were read back. No uncertain mutation was blindly repeated. Exact calls and recovery evidence are in stage2/calls.jsonl and recoveries.jsonl.',
'- The bulk geometry self-check was blocked by the tool’s GUI-loop guard before execution; it was replaced by bounded typed distance, validation and common-volume calls. No analysis worker was launched alongside the GUI. Existing Stage 1 diagnostic Boolean names were already present. Their measured live volumes were read back; current pose/travel checks use the read-only common_volume_along_path tool and create no duplicate Boolean objects.',
'- The archived Mass sheet already existed and its measured cells were read-only. The refreshed mass formulas and readback are in the separate V2Mass sheet. The optional parts library is unavailable; the BOM comes from actual native physical-part properties. Expression-driven poses are retained from Stage 1; they do not claim a successfully solved dynamic assembly.',
'- The tray is shifted beside the head for the scene. Transfer/drop motion to that relocated tray is outside the tested approach/withdrawal paths. Printed exports retain native assembly coordinates; choose the documented flat face when preparing each part for printing.',
'- Remaining engineering gaps: no physical grasp/cutting test; isotropic coarse FEM does not validate print anisotropy, fatigue, blade sharpness or mesh convergence; actual sliced mass and cable strain-relief specification remain to be established. Servo controller and rear connector are outside this head’s modeled boundary. No sensor, controller or guarded operating enclosure is implied.','',
'## Evidence files','',
'- Seven 1600 × 1000 PNGs in this directory; no panels, popup, cursor or navigation cube.',
'- ../strawberry-head-v2.FCStd is the updated native parametric assembly; ../files/ contains printed-part exports.',
'- ../stage2/fem.FCStd and fem_solver/ retain the real FEM setup, mesh, loads, constraints, solver input and results.',
'- ../stage2/checks.json, fem.json, design-manifest.json and calls.jsonl are the detailed machine-readable evidence. scripts/demo/stage2_*.py and stage2_inside.sh reproduce this gate.','']
manifest={}
for path in sorted(ST.glob('*.png')):
 data=path.read_bytes();w,h=struct.unpack('>II',data[16:24]);assert (w,h)==(1600,1000),(path,w,h)
 manifest[path.name]={'width':w,'height':h,'sha256':hashlib.sha256(data).hexdigest()}
assert len(manifest)==7,manifest
(OUT/'artifacts.json').write_text(json.dumps(manifest,indent=2));(ST/'design-notes.md').write_text('\n'.join(lines))
print(json.dumps({'mass_40pct_g':mass['total_g'],'solid_envelope_g':solid_total,'FEM':f,'stills':list(manifest)},indent=2))
