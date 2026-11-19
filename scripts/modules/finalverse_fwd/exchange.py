# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""FWD → Blender → material refinement → GLB/FWD → Cycles preview.

Explicitly offline. Publication and world mutations are not exposed.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid

from . import SCHEMA, VERSION
from .glb import MAX_BYTES, compare, parse, unique_object

PALETTES = {'urban_clay': (0.46, 0.21, 0.12, 1.0),
            'aetheria_slate': (0.10, 0.29, 0.38, 1.0)}


def _read(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Input must be a bounded regular file, not a symbolic link')
    for parent in path.absolute().parents:
        if parent.is_symlink():
            raise ValueError('Symbolic links in input path are refused')
    with path.open('rb') as stream:
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ValueError('Input exceeds byte limit')
    return data


def native_validate(validator, definition, cas_root):
    """Run only the explicitly configured canonical validator, without a shell."""
    validator = Path(validator).absolute()
    if not validator.is_file() or not os.access(validator, os.X_OK):
        raise ValueError('A built canonical finalverse-fwd validator is required')
    result = subprocess.run([str(validator), 'validate', str(definition), str(cas_root)],
                            capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise ValueError('Canonical FWD validation failed: ' + (result.stderr+result.stdout).decode(errors='replace')[-1000:])
    if len(result.stdout) > 128 * 1024:
        raise ValueError('Validator receipt exceeded its limit')
    return json.loads(result.stdout)


def _write_json(path, document):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(document, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def _new_output(path):
    path = Path(path).absolute()
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError('Output must not traverse a symbolic link')
    path.mkdir(parents=False, exist_ok=False)
    return path


def _render(scene, objects, path, samples, size):
    import bpy
    from mathutils import Vector
    # Preview-only lights, ground and camera are never included in the GLB export.
    points = [obj.matrix_world @ Vector(c) for obj in objects for c in obj.bound_box]
    lo = Vector(tuple(min(v[a] for v in points) for a in range(3)))
    hi = Vector(tuple(max(v[a] for v in points) for a in range(3)))
    center = (lo+hi)*0.5
    extent = max((hi-lo).length, 1.0)
    camera_data = bpy.data.cameras.new('Finalverse FWD Preview Camera')
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((0.95, -1.2, 1.0))*extent
    camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = extent*1.4
    scene.camera = camera
    light_data = bpy.data.lights.new('Finalverse FWD Preview Sun', 'SUN')
    light_data.energy = 2.6
    light_data.angle = 0.15
    light = bpy.data.objects.new(light_data.name, light_data)
    light.rotation_euler = (math.radians(23), math.radians(-30), math.radians(-25))
    scene.collection.objects.link(light)
    world = bpy.data.worlds.new('Finalverse FWD Preview Environment')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.32, 0.43, 0.52, 1.0)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.65
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 4
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    scene.cycles.seed = 1729
    scene.render.resolution_x = size
    scene.render.resolution_y = size*3//4
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return {'engine': 'Cycles', 'device': 'CPU', 'threads': 2, 'samples': samples,
            'backend_version': bpy.app.version_string,
            'backend_build_hash': bpy.app.build_hash.decode(errors='replace'),
            'width': size, 'height': size*3//4,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'claim': 'Offline material and geometry preview; generated materials and lighting; not photographic reconstruction'}


def roundtrip(definition, cas_root, output, validator, asset_id=None,
              palette='urban_clay', render=True, samples=16, size=512, cycles_binary=None):
    """Create a fresh candidate and a fresh Blender scene, preserving prior scenes.

    Input definition and referenced CAS files are never modified. Every asset is
    admitted by Core's native validator before Blender processes the selected GLB.
    FWD transforms stay outside the GLB and are copied exactly into the new version.
    """
    import bpy
    started = time.monotonic()
    if palette not in PALETTES or type(samples) is not int or not 1 <= samples <= 64:
        raise ValueError('Invalid material palette or Cycles sample budget')
    if type(size) is not int or not 128 <= size <= 1024 or size % 4:
        raise ValueError('Preview size must be 128..1024, divisible by four')
    if render and not bpy.app.build_options.cycles and not cycles_binary:
        raise ValueError('This Studio binary has Cycles disabled. Configure an explicit Cycles-enabled Blender backend or disable rendering.')
    if cycles_binary:
        cycles_binary = Path(cycles_binary).absolute()
        if not cycles_binary.is_file() or not os.access(cycles_binary, os.X_OK):
            raise ValueError('Cycles backend must be an explicitly configured executable')
    definition = Path(definition).absolute()
    cas_root = Path(cas_root).absolute()
    source_bytes = _read(definition, 2 * 1024 * 1024)
    doc = json.loads(source_bytes, object_pairs_hook=unique_object)
    if doc.get('schema') != SCHEMA:
        raise ValueError('Unsupported FWD schema')
    admission = native_validate(validator, definition, cas_root)
    if _read(definition, 2 * 1024 * 1024) != source_bytes:
        raise ValueError('Definition changed during native admission')
    choices = doc['assets']
    if asset_id:
        choices = [asset for asset in choices if asset['id'] == asset_id]
    if len(choices) != 1:
        raise ValueError('Select exactly one FWD asset ID for this bounded round-trip')
    selected = choices[0]
    if any(binding['asset_id'] == selected['id'] for binding in doc.get('simulation_bindings', [])):
        raise ValueError('A bound simulation asset requires separate reviewed rebinding; Studio cannot authorize it')
    frame = next(frame for frame in doc['frames'] if frame['id'] == selected['frame_id'])
    if frame['kind'] not in ('local_cartesian', 'object_local') or frame['units'] != 'metre':
        raise ValueError('Studio geographic exchange requires an explicit local Cartesian metre frame')
    data = _read(cas_root/selected['sha256'], MAX_BYTES)
    if len(data) != selected['bytes'] or hashlib.sha256(data).hexdigest() != selected['sha256']:
        raise ValueError('Asset changed after FWD admission')
    before = parse(data)
    preflight_s = time.monotonic()-started
    destination = _new_output(output)
    result = {'schema': 'finalverse.studio-fwd-roundtrip/0.1', 'state': 'processing',
              'published': False, 'world_mutations': 0,
              'studio_version': bpy.app.version_string,
              'studio_build_hash': bpy.app.build_hash.decode(errors='replace'),
              'source_definition_sha256': hashlib.sha256(source_bytes).hexdigest(),
              'source_asset_sha256': selected['sha256'], 'source_admission': admission,
              'asset_frame': copy.deepcopy(frame), 'asset_transform': copy.deepcopy(selected['transform']),
              'source_geometry': before['summary'],
              'refinement': {'operation': 'base-color-tint', 'palette': palette, 'tint_fraction': 0.2,
                             'classification': 'procedural', 'geometry_changes': False},
              'timings_seconds': {'preflight': preflight_s}}
    scene = bpy.data.scenes.new('Finalverse FWD Geographic Candidate')
    previous_scene = bpy.context.window.scene
    bpy.context.window.scene = scene
    try:
        # GLB's extension-free, embedded-buffer subset was validated before import.
        import_path = destination/'source.glb'
        import_path.write_bytes(data)
        (destination/'source-fwd.json').write_bytes(source_bytes)
        t = time.monotonic()
        bpy.ops.import_scene.gltf(filepath=str(import_path), import_pack_images=True,
                                  import_shading='NORMALS')
        objects = [obj for obj in scene.objects if obj.type == 'MESH']
        if not objects or len(objects) > 256:
            raise ValueError('Imported mesh object budget exceeded')
        if any(obj.type not in ('MESH', 'EMPTY') for obj in scene.objects):
            raise ValueError('Unexpected imported camera/light/other object')
        generated_materials = []
        for obj in objects:
            slots = list(obj.data.materials) or [None]
            replacements = []
            for source_material in slots:
                color = PALETTES[palette]
                if source_material and source_material.use_nodes:
                    old_bsdf = next((node for node in source_material.node_tree.nodes
                                     if node.type == 'BSDF_PRINCIPLED'), None)
                    if old_bsdf:
                        source_color = old_bsdf.inputs['Base Color'].default_value
                        color = tuple(0.8*source_color[i]+0.2*color[i] for i in range(3))+(1.0,)
                ordinal = len(generated_materials)
                material = bpy.data.materials.new(f'Finalverse generated {palette} {ordinal}')
                material.use_nodes = True
                material.diffuse_color = color
                bsdf = material.node_tree.nodes.get('Principled BSDF')
                bsdf.inputs['Base Color'].default_value = color
                bsdf.inputs['Roughness'].default_value = 0.72
                bsdf.inputs['Metallic'].default_value = 0
                replacements.append(material)
                generated_materials.append({'id': f'studio-{palette}-{ordinal}',
                    'base_color': list(color), 'metallic': 0, 'roughness': 0.72,
                    'classification': 'procedural'})
            if not obj.data.materials:
                obj.data.materials.append(replacements[0])
            else:
                for i, material in enumerate(replacements):
                    obj.data.materials[i] = material
        bpy.ops.object.select_all(action='DESELECT')
        for obj in scene.objects:
            obj.select_set(obj.type in ('MESH', 'EMPTY'))
        result['timings_seconds']['import_and_refine'] = time.monotonic()-t
        t = time.monotonic()
        raw_output = destination/'refined.glb'
        bpy.ops.export_scene.gltf(filepath=str(raw_output), export_format='GLB',
            use_selection=True, use_active_scene=True, export_animations=False, export_skins=False,
            export_morph=False, export_cameras=False, export_lights=False,
            export_extras=False, export_yup=True, export_draco_mesh_compression_enable=False)
        output_bytes = _read(raw_output, MAX_BYTES)
        after = parse(output_bytes)
        result['roundtrip'] = compare(before, after)
        result['output_geometry'] = after['summary']
        result['timings_seconds']['export_and_geometry_validation'] = time.monotonic()-t
        output_sha = hashlib.sha256(output_bytes).hexdigest()
        output_cas = destination/'objects'
        output_cas.mkdir()
        (output_cas/output_sha).write_bytes(output_bytes)
        for asset in doc['assets']:
            if asset is selected:
                continue
            preserved = _read(cas_root/asset['sha256'], MAX_BYTES)
            if len(preserved) != asset['bytes'] or hashlib.sha256(preserved).hexdigest() != asset['sha256']:
                raise ValueError('Unselected asset changed after FWD admission')
            target = output_cas/asset['sha256']
            if not target.exists():
                target.write_bytes(preserved)
        derived = copy.deepcopy(doc)
        derived['version'] += 1
        source_id = 'studio-input-'+selected['sha256'][:16]
        licenses = sorted({source['license'] for source in doc['sources'] if source['id'] in selected['source_ids']})
        if not licenses:
            raise ValueError('Selected asset requires declared source licensing')
        if source_id not in {source['id'] for source in derived['sources']}:
            derived['sources'].append({'id': source_id,
                'uri': 'urn:sha256:'+selected['sha256'], 'license': ' AND '.join(licenses),
                'sha256': selected['sha256'], 'version': str(doc['version']),
                'classification': 'derived', 'attribution': 'Input GLB before Studio material refinement'})
        output_asset = next(asset for asset in derived['assets'] if asset['id'] == selected['id'])
        output_asset['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 'finalverse:studio-fwd:'+output_sha))
        output_asset.update({'sha256': output_sha, 'bytes': len(output_bytes),
                             'classification': 'derived', 'source_ids': [*selected['source_ids'], source_id]})
        for semantic in derived.get('semantics', []):
            if semantic['asset_id'] == selected['id']:
                semantic['asset_id'] = output_asset['id']
        material_ids = {material['id'] for material in generated_materials}
        materials = derived.setdefault('materials', [])
        materials[:] = [m for m in materials if m['id'] not in material_ids]
        materials.extend(generated_materials)
        derived['generation'] = {'generator': 'finalverse-studio-fwd', 'version': VERSION,
                                'seed': doc['generation']['seed'],
                                'operations': ['import-validated-glb', 'generated-material:'+palette,
                                               'geometry-preserving-gltf-roundtrip',
                                               'source-definition-sha256:'+result['source_definition_sha256']]}
        _write_json(destination/'world.fwd.json', derived)
        result['output_admission'] = native_validate(validator, destination/'world.fwd.json', output_cas)
        if render:
            t = time.monotonic()
            if cycles_binary:
                worker = Path(__file__).with_name('render_worker.py')
                command = [str(cycles_binary), '--background', '--factory-startup',
                    '--python-exit-code', '1', '--python', str(worker), '--',
                    str(destination/'world.fwd.json'), str(output_cas), str(validator),
                    str(destination/'cycles-preview.png'), str(samples), str(size)]
                backend_env = os.environ.copy()
                for name in ('OCIO', 'PYTHONPATH', 'PYTHONHOME', 'BLENDER_SYSTEM_PYTHON',
                             'BLENDER_SYSTEM_SCRIPTS', 'BLENDER_SYSTEM_DATAFILES',
                             'BLENDER_USER_SCRIPTS', 'BLENDER_USER_CONFIG', 'BLENDER_USER_DATAFILES'):
                    backend_env.pop(name, None)
                completed = subprocess.run(command, capture_output=True, timeout=120,
                                           check=False, env=backend_env)
                (destination/'cycles-backend.log').write_bytes(completed.stdout+completed.stderr)
                if completed.returncode:
                    raise ValueError('Configured Cycles backend failed; inspect cycles-backend.log')
                result['render'] = json.loads((destination/'cycles-preview.png.json').read_text())
                result['render']['backend'] = 'explicit-external-blender-cycles'
                result['render']['backend_executable'] = str(cycles_binary)
            else:
                result['render'] = _render(scene, objects, destination/'cycles-preview.png', samples, size)
                result['render']['backend'] = 'studio-built-in-cycles'
            result['timings_seconds']['cycles_render'] = time.monotonic()-t
        # Write only our candidate scene and dependencies. Saving the entire current
        # user document could inadvertently include unrelated private authoring work.
        scene['finalverse.fwd_source_sha256'] = result['source_definition_sha256']
        scene['finalverse.fwd_frame'] = json.dumps(frame, sort_keys=True)
        scene['finalverse.fwd_transform'] = json.dumps(selected['transform'], sort_keys=True)
        bpy.data.libraries.write(str(destination/'editable.blend'), {scene}, fake_user=True)
        result['state'] = 'validated-offline-candidate'
        result['output_definition_sha256'] = hashlib.sha256((destination/'world.fwd.json').read_bytes()).hexdigest()
        result['output_asset_id'] = output_asset['id']
        result['output_asset_sha256'] = output_sha
        result['timings_seconds']['total'] = time.monotonic()-started
        _write_json(destination/'receipt.json', result)
        return result
    except Exception as error:
        result.update({'state': 'failed', 'error': str(error), 'timings_seconds': {'total': time.monotonic()-started}})
        _write_json(destination/'FAILED.json', result)
        raise
    finally:
        bpy.context.window.scene = previous_scene
