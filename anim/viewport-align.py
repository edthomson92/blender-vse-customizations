import bpy
from mathutils import Matrix
import bpy_extras

#3 Align Object in Camera Viewport
##
## Blender Python script by Josh R (GitHub user Botmasher)

# Base implementation
# - determine point at center of camera x,y
# - determine focal point for camera z
# - place object at point
# - scale object to fit within frustum
#   - account for all points (or just normals) in mesh

def find_center(cam, offset=[0,0,0]):
    if cam.type != 'CAMERA': return
    point = [cam.location[x] + offset[x] for x in range(cam.location)]
    return point

def find_edges(cam):
    r = bpy.context.scene.render.resolution_x
    b = bpy.context.scene.render.resolution_y
    trbl = [0, r, b, 0]
    return trbl

def translatable(*objs):
    """Determine if the object exists and is movable"""
    for obj in objs:
        if not obj or not obj.location:
            return False
    return True

## TODO:
##  iterate on center_obj() to work this way:
##  FUTURE: determine when object scaled to fit within view
##      - requires point detection?
##      - allow adjusting scale within view (like calculate view size * 0.5)

## newer iteration on center align
def center_in_cam_view(obj=bpy.context.object, cam=bpy.context.scene.camera, distance=0.0, snap=False):
    if not translatable(obj, cam):
        return

    # move and rotate obj to cam
    obj.location = cam.location
    obj.rotation_euler = cam.rotation_euler
    v = (0.0, 0.0, -distance)

    # local move away cam using matrix translation
    # https://blender.stackexchange.com/questions/82265/move-object-along-local-axis-with-python-api
    if snap:
        # parent to camera
        obj.parent = cam
        obj.matrix_basis = Matrix.Translation(v)
    else:
        obj.matrix_basis *= Matrix.Translation(v)

    return obj

## test call
#center_in_cam_view(distance=5.0)

# Find object edges vs camera view edges

def get_frustum_loc(point, cam=bpy.context.scene.camera, scene=bpy.context.scene):
    """Determine location of a point within camera's rendered frame"""
    if not point or not cam or not scene:
        return
    # scene to use for frame size
    # Camera object
    # World space location (mathutils.Vector)
    uv_loc = bpy_extras.object_utils.world_to_camera_view(scene, cam, point)
    # returns a Vector magnitude 3 with valid cam positions between 0<=uv_loc<=1
    #   - values for index 0,1 greater than 1 are above top-right of frame
    #   - values at index 2 less than 0 are behind camera
    return uv_loc

def is_frustum_loc(point, cam=bpy.context.scene.camera, scene=bpy.context.scene):
    """Check if a point falls within camera's rendered frame"""
    if not point or not cam or not scene: return
    uv_loc = bpy_extras.object_utils.world_to_camera_view(scene, cam, point)
    return (0.0 <= uv_loc[0] <= 1.0 and 0.0 <= uv_loc[1] <= 1.0 and uv_loc[2] >= 0.0)

def has_mesh(obj):
    """Check if the object contains mesh data"""
    if hasattr(obj.data, 'vertices'):
        return True
    return False

def is_camera(obj):
    """Check if the object is a Camera"""
    if obj and hasattr(obj, 'type') and obj.type == 'CAMERA':
        return True
    return False

# Fit based on vertex extremes NOT object center
# - calculate obj vertex X-Y extremes
# - figure out their center and distance
# - use the VERTEX center to align object in cam
def fit_vertices_to_frustum(obj, cam):
    if not has_mesh(obj) or not is_camera(cam) or len(obj.data.vertices) < 1:
        return
    edges_uv = {'u': [None, None], 'v': [None, None]}
    edges_xy = {'x': [None, None], 'y': [None, None]}
    for v in obj.data.vertices:
        uv = get_frustum_loc(obj.matrix_world * v.co, cam=cam)
        # TODO add vertex to edges if it is more positive or negative than stored extreme edges
        # zeroth value for L/bottom of render screen, first value for R/top render screen
        if edges_uv['u'][0] is None or uv[0] < edges_uv['u'][0]:
            edges_uv['u'][0] = uv[0]
            edges_xy['x'][0] = obj.matrix_world * v.co[0]
        if edges_uv['u'][1] is None or uv[0] > edges_uv['u'][1]:
            edges_uv['u'][1] = uv[0]
            edges_xy['x'][1] = obj.matrix_world * v.co[0]
        if edges_uv['v'][0] is None or uv[1] < edges_uv['v'][0]:
            edges_uv['v'][0] = uv[1]
            edges_xy['y'][0] = obj.matrix_world * v.co[1]
        if edges_uv['v'][1] is None or uv[1] > edges_uv['v'][1]:
            edges_uv['v'][1] = uv[1]
            edges_xy['y'][1] = obj.matrix_world * v.co[1]
    # TODO then calculate this as a ratio of units needed to move
    # - how much must this object scale to fit within frustum?
    # - then, how much would it need to move for that scaled object to be entirely visible to current cam?
    width = edges_uv['u'][1] - edges_uv['u'][0]
    height = edges_uv['v'][1] - edges_uv['v'][0]
    overscale_x = width - 1.0
    overscale_y = height - 1.0
    # needs scaled
    overscale = 0
    if overscale_x > 0 or overscale_y > 0:
        # use highest x or y to scale down uniformly
        overscale = overscale_y if overscale_y > overscale_x else overscale_x
        obj.scale /= 1 + (overscale * 2)    # double to account for both sides
    # needs moved
    # TODO figure out object position vs vertices positions
    #   - move vs obj position
    move_highest_x = * edges_xy['x'][1]
    move_lowest_x = * edges_xy['x'][0]
    move_highest_y = * edges_xy['y'][1]
    move_lowest_y = * edges_xy['y'][0]
    obj.location.x - (move_highest_x * overscale_x)
    if width > 0 or height > 0:
        new_width = width * (1 + overscale)
        new_height = height * (1 + overscale)
        # Calculate the distance of mesh vs object center
        # - how far does object need to move until all vertices fit?r
    return obj

# TODO allow stretch (non-uniform scale)
# TODO move instead of scale if object could fit
#   - may want to move if object center is outside frustum
#   - alternatively guard check if obj inside frustum in the first place
def fit_to_frustum(obj, cam=bpy.context.scene.camera, move_into_view=True, margin=0.0, distance=5.0, distort=False):
    if not has_mesh(obj) or not is_camera(cam):
        return
    vertex_extremes = [0.0, 0.0, 0.0]
    # calculate mesh vertices far outside of viewport
    # TODO rework calculations here to store XY excess only at this step
    overflow_high = 0.0
    move_loc = obj.location
    for vertex in obj.data.vertices:
        uvz = get_frustum_loc(obj.matrix_world * vertex.co, cam=cam)
        # shallow Z location closest to camera (negative is behind)
        if uvz[2] < 0 and abs(uvz[2]) > abs(vertex_extremes[2]):
            # TODO handle Z index behind cam
            # use high negative w to move object in front of cam and recurse for u,v
            # move into cam view and retry
            center_in_cam_view(obj=obj, cam=cam, distance=distance)
            return fit_to_frustum(obj, cam=cam, move_into_view=False, margin=margin, distance=distance, distort=distort)
        # cut off and store excess (outside range 0-1)
        overflows = [max(0, d - 1.0) if d > 0 else d for d in uvz]
        # keep track of highest excess found so far
        vertex_extremes = [overflows[i] if abs(overflows[i]) > abs(vertex_extremes[i]) else vertex_extremes[i] for i in range(len(vertex_extremes))]
    # farthest XY locations outside UV render frame
    overflow_high = max(abs(overflows[0]), abs(overflows[1]))

    # use high UV to rescale object
    # TODO check meshes entirely out of viewport (move into view?)
    # adjust calc so mesh ends up fully inside (see vertex loop at top of method)
    # EITHER    double change to account for both sides (e.g. top AND bottom)
    # OR        move in opposite direction
    overflow_high *= 2              # account for excess on both sides
    obj.scale /= 1 + overflow_high
    #obj.location = move_loc        # move for both sides

    print("\nObj vertices in render space: {0}".format(vertex_extremes))
    print("Attempting to adjust by {0}".format(overflow_high))

    ## TODO move realign
    ##  - center first, check again then move
    ##  - centering first above avoids dealing with outside values
    #for i in range(len(vertex_extremes)):
    #    move_loc[i] *= vertex_extremes[i]

    return vertex_extremes

fit_to_frustum(bpy.context.object, margin=1.0)

# Work through detecting object in camera again:
# https://blender.stackexchange.com/questions/45146/how-to-find-all-objects-in-the-cameras-view-with-python/45324
