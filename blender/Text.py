import bpy
import math
from pathlib import Path

# Scene file:
# /blender/colorcloud.blend
blend_dir = Path(bpy.data.filepath).parent

# Target folder:
# /calib_out/captures
captures_dir = blend_dir.parent / "calib_out" / "captures"

# Delete currently imported PLY objects
for obj in list(bpy.context.scene.objects):
    if obj.name.lower().endswith(".ply") or obj.get("source_type") == "ply":
        bpy.data.objects.remove(obj, do_unlink=True)

# Find newest PLY
ply_files = list(captures_dir.glob("*.ply"))

if not ply_files:
    raise FileNotFoundError(f"No .ply files found in {captures_dir}")

newest_ply = max(ply_files, key=lambda p: p.stat().st_mtime)

# Import newest PLY
bpy.ops.wm.ply_import(filepath=str(newest_ply))

obj = bpy.context.object
obj["source_type"] = "ply"
obj["source_path"] = str(newest_ply)

# Move up 2 meters
obj.location = (0,0,2)

# Rotate
obj.rotation_euler = (
    math.radians(0),
    math.radians(-90),
    math.radians(0),
)

# Assign existing material preset
mat = bpy.data.materials.get("Pointcloud Color")
if mat:
    obj.data.materials.clear()
    obj.data.materials.append(mat)

# Assign existing Geometry Nodes preset
modifier = obj.modifiers.new("Pointcloud Geometry", "NODES")
node_group = bpy.data.node_groups.get("Pointcloud color Geometry Nodes")
if node_group:
    modifier.node_group = node_group
    
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for space in area.spaces:
            if space.type == 'VIEW_3D':
                space.shading.type = 'MATERIAL'

cam = bpy.context.scene.camera

# store original position
original_loc = cam.location.copy()

# move camera up 2 meters (Z axis)
cam.location.z += 2

original_lens = cam.data.lens

# zoom in (increase focal length = stronger zoom)
cam.data.lens += 50  # try 10–50 depending on effect


# Render screenshot
bpy.context.scene.render.resolution_x = 1920
bpy.context.scene.render.resolution_y = 1080
bpy.context.scene.render.filepath = str(blend_dir / "latest_capture_preview.png")

bpy.ops.render.render(write_still=True)

cam.location = original_loc
cam.data.lens = original_lens