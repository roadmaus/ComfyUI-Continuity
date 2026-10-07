"""The mannequin's joints, by what they do: `elbow_l.bend=90`, not `lowerarm_l=x,y,z`.

A pose is stored the way Pose Studio stores it (`pose.py`): per bone, an Euler
rotation in degrees, XYZ order, in the bone's parent frame. That is exact and it
is what the core draws, but it says nothing a person or an agent can reason
with: which of the three numbers bends an elbow, which way is forward, and
whether 60 is a lot. An agent writing those numbers guesses, renders, looks and
guesses again. This module is the vocabulary over them (spec §7.9, §11.3).

**A joint is a bone and three named motions.** `shoulder_l` is `upperarm_l`
turned by `forward`, `raise` and `twist`; `elbow_l` is `lowerarm_l` by `bend`,
`side` and `twist`. Each motion is a turn about an axis fixed in the rig, with
its sign chosen so that the positive direction is the one the name says: `raise`
lifts the arm away from the body, `bend` closes the elbow, `turn` on the head
looks to the figure's own left. Every joint also has limits, and a value past
them is refused rather than clamped, because a clamp would draw a pose the
caller did not ask for and say nothing.

**Angles are anatomical, not relative to the standing pose.** The mannequin
stands in an A-pose with its elbows already bent about 47°, its arms out about
40° and its legs a little apart. Relative to that, "a straight arm" would be
`bend=-47`, and nobody can write that from intuition. So each joint is read
against a *zero* configuration: the limb straight down (shoulder, hip), the
forearm in line with the upper arm (elbow), the calf in line with the thigh
(knee). `elbow_l.bend=0` is a straight arm, `90` a right angle;
`shoulder_l.raise=90` holds the arm out level, `180` overhead. A motion not
named keeps what the pose has, so `shoulder_l.forward=90` alone, on the
standing figure, points the arm ahead *and* 40° out; say `raise=0` too for
straight ahead. Centre joints
(spine, neck, head) and the ankle, wrist and toes are read against the
standing pose, which is already their natural zero.

**How the numbers become a rotation.** A joint has an orthonormal basis `B`
whose columns are its three motions' axes, in the rig's frame (X the figure's
left, Y up, Z its front; every bone's rest frame is the world's, checked in a
browser, see `web/creator/forge/mirror.js`), and a turn `Z` from the standing
pose to its zero configuration (the shortest turn from the bone's rest
direction to its zero direction). The bone's stored rotation is

    R = B · E(angles) · Bᵀ · Z

where `E` is the XYZ Euler matrix, so the motions compose in a fixed order
(the third first, then the second, then the first, each about the joint's own
axes as already turned). Reading inverts it: `E = Bᵀ · R · Zᵀ · B`. The order
matters only near a pole: at `shoulder.forward=90` the arm points straight
ahead, and `raise` then turns it about its own length. `raise=90, forward=45`
is an arm held level, half way between the side and the front.

**The rest directions are measured, once.** `REST` holds the bones' directions
as the mannequin pack's base mesh has them (joint heads and tails averaged from
the pack's joint vertex groups, as the morph runtime does). Body sliders move
them by a degree or two, which moves the anatomical zero by as much: `raise=90`
is level within a couple of degrees, not to the pixel. The joint vocabulary is
for saying what a pose is; exact numbers still go through raw `bones`.

**Right is left in a mirror.** Only the left joints are defined. A right bone's
rotation is read by reflecting it into the left (`[x, -y, -z]`, the rule
`mirror.js` rests on) and written by reflecting the answer back, so
`shoulder_r.raise=90` lifts the right arm to its own side and every sign means
the same on both sides.

**Hands are shapes.** Pose Studio ships three hand presets (open, chop, fist)
as finger quaternions in `vnccs_hand_presets.mjs`; `HANDS` is the left half of
that table, copied, and `tests/test_pose_joints.py` holds it against the
vendored file. A curl axis guessed per finger would be one more thing to get
wrong, and these three are the shapes the pose LoRAs were shown.

Standard library only, like the rest of the storage half.
"""

import math

from .problems import ForgeError

# ---- 3x3 rotations, as three.js composes them -----------------------------------
#
# Matrices are tuples of rows. Euler angles are radians here and degrees at the
# edges, XYZ order: matrix = Rx · Ry · Rz, three.js's `Euler` default and the
# order Pose Studio stores.


def _mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def _t(m):
    return tuple(tuple(m[j][i] for j in range(3)) for i in range(3))


def _apply(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    n = math.sqrt(_dot(v, v))
    return tuple(x / n for x in v)


def _det(m):
    return _dot(m[0], _cross(m[1], m[2]))


def axis_angle(axis, angle):
    """Rodrigues: the turn by `angle` radians about the unit `axis`."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


def euler_matrix(x, y, z):
    """XYZ Euler (radians) -> matrix, as `Matrix4.makeRotationFromEuler`."""
    a, b = math.cos(x), math.sin(x)
    c, d = math.cos(y), math.sin(y)
    e, f = math.cos(z), math.sin(z)
    ae, af, be, bf = a * e, a * f, b * e, b * f
    return ((c * e, -c * f, d),
            (af + be * d, ae - bf * d, -b * c),
            (bf - ae * d, be + af * d, a * c))


def matrix_euler(m):
    """Matrix -> XYZ Euler (radians), as `Euler.setFromRotationMatrix`."""
    m13 = max(-1.0, min(1.0, m[0][2]))
    y = math.asin(m13)
    if abs(m13) < 0.9999999:
        return math.atan2(-m[1][2], m[2][2]), y, math.atan2(-m[0][1], m[0][0])
    return math.atan2(m[2][1], m[1][1]), y, 0.0


def degrees_matrix(rotation):
    return euler_matrix(*(math.radians(v) for v in rotation))


def matrix_degrees(m):
    return [math.degrees(v) for v in matrix_euler(m)]


def quaternion_matrix(q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    return ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
            (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
            (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))


def matrix_quaternion(m):
    """Matrix -> unit quaternion `(x, y, z, w)`, as `Quaternion.setFromRotationMatrix`."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        return ((m[2][1] - m[1][2]) * s, (m[0][2] - m[2][0]) * s, (m[1][0] - m[0][1]) * s, 0.25 / s)
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])
        return (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    if m[1][1] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])
        return ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    s = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])
    return ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)


def slerp(a, b, t):
    """Quaternions `a` -> `b` at `t`, the short way round."""
    d = _dot(a, b)
    if d < 0:
        b, d = tuple(-v for v in b), -d
    if d > 0.9995:
        out = tuple(x + (y - x) * t for x, y in zip(a, b))
    else:
        theta = math.acos(d)
        s = math.sin(theta)
        wa, wb = math.sin((1 - t) * theta) / s, math.sin(t * theta) / s
        out = tuple(wa * x + wb * y for x, y in zip(a, b))
    n = math.sqrt(_dot(out, out))
    return tuple(v / n for v in out)


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def shortest_turn(a, b):
    """The smallest rotation taking unit direction `a` onto unit `b`."""
    axis = _cross(a, b)
    s = math.sqrt(_dot(axis, axis))
    if s < 1e-9:
        return IDENTITY
    return axis_angle(tuple(v / s for v in axis), math.atan2(s, _dot(a, b)))


# ---- the mirror ----------------------------------------------------------------
#
# The same reflection `web/creator/forge/mirror.js` makes, so the server can flip
# a frame the way the bench does; `tests/test_pose_symmetry.py` holds the two
# against each other.

SIDES = ("l", "r")


def twin(name):
    """`upperarm_l` -> `upperarm_r`; a centre bone or joint is its own twin."""
    if name.endswith("_l"):
        return name[:-2] + "_r"
    if name.endswith("_r"):
        return name[:-2] + "_l"
    return name


def side_of(name):
    return name[-1] if name[-2:] in ("_l", "_r") else None


def mirror_rotation(r):
    return [r[0], -r[1] + 0.0, -r[2] + 0.0]


def mirror_position(p):
    return [-p[0] + 0.0, p[1], p[2]]


def _resting(value):
    return not any(abs(v) > 1e-9 for v in value)


def flip_pose(pose):
    """The pose seen in a mirror: left and right swap, and each reflects."""
    x, y, z = pose.get("modelRotation") or [0.0, 0.0, 0.0]
    bones = {}
    for name, value in (pose.get("bones") or {}).items():
        reflected = mirror_rotation(value)
        if not _resting(reflected):
            bones[twin(name)] = reflected
    return {"bones": dict(sorted(bones.items())),
            "bonePositions": dict(sorted((twin(n), mirror_position(v))
                                         for n, v in (pose.get("bonePositions") or {}).items())),
            "modelRotation": [x, (360 - y) % 360, (360 - z) % 360]}


# ---- the rig, as measured ------------------------------------------------------

# Unit directions (head -> tail) of the left bones a joint needs, in the rig's
# frame: X the figure's left, Y up, Z its front. Measured from the base mesh of
# `pose_studio_makehuman.v2.bin.gz` (the morph runtime's `averageVertices` of
# each bone's head and tail joint groups); the right side is the mirror.
REST = {
    "clavicle_l": (0.932, 0.036, -0.362),
    "upperarm_l": (0.638, -0.770, -0.006),
    "lowerarm_l": (0.522, -0.460, 0.718),
    "hand_l": (-0.067, -0.727, 0.683),
    "thigh_l": (0.113, -0.992, 0.047),
    "calf_l": (0.161, -0.983, -0.086),
}
# Where the base of the index and little fingers sit on the left hand: the line
# between them runs across the palm, towards the thumb side.
INDEX_BASE = (4.496, 2.030, 2.644)
PINKY_BASE = (4.745, 1.764, 2.124)

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
DOWN = (0.0, -1.0, 0.0)


def _neg(v):
    return tuple(-x for x in v)


def _rest(bone):
    return _unit(REST[bone])


def _perpendicular(v, to):
    """`v` with its part along unit `to` removed, made unit."""
    return _unit(tuple(a - _dot(v, to) * b for a, b in zip(v, to)))


def _elbow_axes():
    upper, fore = _rest("upperarm_l"), _rest("lowerarm_l")
    bend = _unit(_cross(upper, fore))           # turns the upper arm's line onto the forearm
    # Twist is about the forearm pointing back to the elbow, so that + is the
    # palm turning up (checked on a render: about the hand-ward axis it turned
    # the palm down).
    return bend, _cross(bend, upper), _neg(upper)


def _knee_axes():
    thigh = _rest("thigh_l")
    bend = _perpendicular(X, thigh)              # about the figure's left: the calf swings back
    return bend, _cross(thigh, bend), thigh


def _wrist_axes():
    hand = _rest("hand_l")
    thumbward = _perpendicular(tuple(a - b for a, b in zip(INDEX_BASE, PINKY_BASE)), hand)
    palm = _unit(_cross(hand, thumbward))        # the palm's normal; the fingers curl towards it
    # side: towards the thumb; bend: towards the palm; twist: about the hand.
    return palm, _neg(thumbward), hand


class Joint:
    """One joint: the bone(s) it turns, its motions, their axes and limits.

    `axes` are three orthonormal unit vectors, in motion order. The first
    motion turns furthest (to ±180), the middle one only to ±90 — an Euler
    triple's middle angle cannot go further — so a motion that must pass 90
    (an arm raised overhead, a knee bent double) is never the middle one.
    Axes that make a left-handed basis are fine: in a mirror basis every turn
    runs the other way, so the angles' signs are flipped to match (`sense`).
    `zero` is the bone's direction in the zero configuration, or None
    when the standing pose is the zero. `bones` with more than one entry
    share the turn evenly (the spine).
    """

    def __init__(self, name, bones, motions, axes, limits, zero=None, rest=None, words=""):
        self.name = name
        self.bones = bones
        self.motions = motions
        self.basis = _t(tuple(_unit(a) for a in axes))   # columns are the axes
        if abs(abs(_det(self.basis)) - 1) > 1e-6:
            raise AssertionError(f"{name}'s axes are not orthonormal")
        self.sense = 1.0 if _det(self.basis) > 0 else -1.0
        self.limits = dict(zip(motions, limits))
        # From the standing pose to the zero configuration, and back.
        self.to_zero = shortest_turn(_unit(rest), _unit(zero)) if zero else IDENTITY
        self.words = words

    def read(self, rotation):
        """A left bone's stored rotation (degrees) -> this joint's angles."""
        m = _mul(_mul(_mul(_t(self.basis), degrees_matrix(rotation)), _t(self.to_zero)), self.basis)
        return {motion: self.sense * v for motion, v in zip(self.motions, matrix_degrees(m))}

    def write(self, angles):
        """This joint's angles (degrees, all three) -> the left bone's stored rotation."""
        e = degrees_matrix([self.sense * angles[m] for m in self.motions])
        return matrix_degrees(_mul(_mul(_mul(self.basis, e), _t(self.basis)), self.to_zero))


def _joints():
    elbow, knee, wrist = _elbow_axes(), _knee_axes(), _wrist_axes()
    centre = (X, _neg(Z), Y)       # bend: front, lean: own left, turn: own left
    limb = (_neg(X), Z, Y)          # forward, raise (outward), twist (outward)
    arm = (Z, _neg(X), Y)           # raise first, so it reaches overhead
    return [
        Joint("spine", ("spine_01", "spine_02", "spine_03"), ("bend", "lean", "turn"), centre,
              ((-40, 90), (-45, 45), (-70, 70)),
              words="the back, shared by its three bones: bend forward (+) or back (-), lean to its "
                    "own left (+) or right (-), turn the chest to its own left (+) or right (-)"),
        Joint("neck", ("neck_01",), ("bend", "lean", "turn"), centre, ((-45, 60), (-40, 40), (-70, 70)),
              words="as the spine, for the neck"),
        Joint("head", ("head",), ("bend", "lean", "turn"), centre, ((-45, 45), (-35, 35), (-60, 60)),
              words="nod down (+) or tip back (-), tilt to its own left (+), look to its own left (+)"),
        Joint("collar", ("clavicle",), ("shrug", "forward", "twist"), (Z, _neg(Y), X),
              ((-15, 40), (-25, 30), (-20, 20)),
              words="the collarbone: shrug the shoulder up (+), bring it forward (+)"),
        Joint("shoulder", ("upperarm",), ("raise", "forward", "twist"), arm,
              ((-20, 180), (-70, 90), (-90, 90)), zero=DOWN, rest=REST["upperarm_l"],
              words="raise 0, forward 0 is the arm hanging straight down (standing, it is raised 40). "
                    "raise 90: out to the side, level; 180: overhead. forward 90: pointing ahead, level; "
                    "with raise 90, forward swings the level arm round to the front. twist (+) turns it outward"),
        Joint("elbow", ("lowerarm",), ("bend", "side", "twist"), elbow,
              ((0, 150), (-15, 15), (-90, 90)), zero=REST["upperarm_l"], rest=REST["lowerarm_l"],
              words="bend 0 is a straight arm, 90 a right angle (standing, it is bent 47); "
                    "twist (+) turns the palm up"),
        Joint("wrist", ("hand",), ("side", "bend", "twist"), wrist, ((-25, 35), (-70, 80), (-30, 30)),
              words="bend (+) towards the palm, side (+) towards the thumb"),
        Joint("hip", ("thigh",), ("forward", "raise", "twist"), limb,
              ((-40, 130), (-30, 90), (-45, 45)), zero=DOWN, rest=REST["thigh_l"],
              words="forward 0, raise 0 is the leg straight down (standing, it is raised 6). forward 90: "
                    "thigh level in front; raise: out to the side; twist (+) turns the knee outward"),
        Joint("knee", ("calf",), ("bend", "side", "twist"), knee,
              ((0, 150), (-10, 10), (-30, 30)), zero=REST["thigh_l"], rest=REST["calf_l"],
              words="bend 0 is a straight leg; the calf swings back"),
        Joint("ankle", ("foot",), ("point", "roll", "out"), centre, ((-35, 60), (-30, 30), (-35, 35)),
              words="point (+) the toes down, (-) up; roll (+) turns the sole inward; out (+) turns the toes outward"),
        Joint("toes", ("ball",), ("bend", "side", "twist"), limb, ((-40, 70), (-10, 10), (-10, 10)),
              words="bend (+) the toes up, as in pushing off"),
    ]


JOINTS = {j.name: j for j in _joints()}
SIDED = frozenset(n for n, j in JOINTS.items() if not j.bones[0].startswith(("spine", "neck", "head")))

# ---- hands -----------------------------------------------------------------------

FINGERS = tuple(f"{finger}_0{n}" for finger in ("thumb", "index", "middle", "ring", "pinky") for n in (1, 2, 3))

# Pose Studio's hand presets (`vnccs_hand_presets.mjs`, `preset_l`), as local
# quaternions (x, y, z, w) per finger bone. The right hand is the mirror.
HANDS = {
    "open": {
        "thumb_01": (-0.13720544603689652, 0.10832398879715235, -0.17580927980515873, 0.9687784453440746),
        "thumb_02": (-0.05073807952974384, -0.010904239028835985, -0.14398792100708405, 0.9882177004389737),
        "thumb_03": (-0.0637184002115847, 0.08495340746584812, -0.07434587313668746, 0.9915621892659893),
        "index_01": (-0.18234548871101025, 0.07987600886016208, 0.0645467550369696, 0.9778566675998643),
        "index_02": (-0.054076966382105754, 0.05773364889806841, 0.04057683006309617, 0.9960401740662139),
        "index_03": (-0.034890609282494586, 0.03675636544924377, 0.026039372049134892, 0.9983754634836259),
        "middle_01": (-0.10180816789187547, 0.05364754816917245, 0.0871395333763862, 0.9895270280537474),
        "middle_02": (-0.047787723735679556, 0.05070542056845075, 0.06608072411900397, 0.9953786373461342),
        "middle_03": (-0.02147954349366744, 0.012870906166594505, 0.03274114477321023, 0.9991501320746019),
        "ring_01": (-0.024972380031255, 0.04547248598795393, 0.07280411141909462, 0.9959960816258896),
        "ring_02": (-0.024094828084863396, 0.01597407822649981, 0.04781195937058897, 0.9984379222693416),
        "ring_03": (-0.01637596191407609, 0.013539067765845682, 0.029545060453725003, 0.9993375860629912),
        "pinky_01": (-0.017747511998309422, 0.10553741261840383, 0.11822536627994708, 0.9872029391789992),
        "pinky_02": (-0.008488710903683314, 0.02600225118234192, 0.05697757769446566, 0.9980006915632451),
        "pinky_03": (-0.007769622339505466, 0.02050446043022238, 0.05258939022149892, 0.9983754584860838),
    },
    "chop": {
        "thumb_01": (-0.11218644155700765, 0.26479669437222025, -0.08909711451086874, 0.9536029662108639),
        "thumb_02": (0.057344540005484654, 0.07153417240516512, 0.16354501068376068, 0.9822665093498384),
        "thumb_03": (0.012223997584035825, 0.02912359129726497, 0.03243518445665448, 0.9989746488886884),
        "index_01": (0.0546686762627437, 0.08260588526258357, 0.19136776270029965, 0.9765070316975428),
        "index_02": (-0.030550669522877945, 0.027534536948391627, 0.0024436179834006794, 0.9991509068193315),
        "index_03": (0.0, 0.0, 0.0, 1.0),
        "middle_01": (-0.04932888545866675, -0.020429162672349024, 0.10591666025580966, 0.9929405679355476),
        "middle_02": (-0.02009234645784536, 0.046897453635141, 0.022970206356045034, 0.9984334209532042),
        "middle_03": (-0.021479543493667437, 0.012870906166594502, 0.03274114477321024, 0.9991501320746019),
        "ring_01": (-0.0888433661177363, -0.09753072233118655, 0.0690138310639133, 0.9888537331781221),
        "ring_02": (-0.0240948280848634, 0.01597407822649981, 0.04781195937058897, 0.9984379222693416),
        "ring_03": (-0.01637596191407609, 0.013539067765845686, 0.02954506045372501, 0.9993375860629912),
        "pinky_01": (-0.21856008800812737, -0.10206694426370616, 0.1541545848533417, 0.9581493572440798),
        "pinky_02": (-0.008488710903683312, 0.026002251182341923, 0.05697757769446568, 0.9980006915632451),
        "pinky_03": (-0.0077696223395054675, 0.020504460430222384, 0.05258939022149892, 0.9983754584860838),
    },
    "fist": {
        "thumb_01": (0.0, 0.0, 0.0, 1.0),
        "thumb_02": (0.132405316320699, 0.18585495078131112, 0.035111519417413445, 0.9729819888796979),
        "thumb_03": (0.31377198210388674, 0.03568240519045323, 0.16222440955442846, 0.934856753813727),
        "index_01": (0.31172006505305605, -0.3378254961753802, -0.23015993265766227, 0.8577475972430334),
        "index_02": (0.20284497436828702, -0.2137431141961466, -0.2191275173404543, 0.9301348980935351),
        "index_03": (0.17198799239138954, -0.3089858589261866, -0.43370142393479594, 0.8287647098747367),
        "middle_01": (0.14893446505579772, -0.36184653220883345, -0.3434640941582824, 0.8537669636797945),
        "middle_02": (0.24238181556250415, -0.1432582695336492, -0.5297479002676369, 0.8000595514440648),
        "middle_03": (0.14158699069803765, -0.10226732887207433, -0.2617885362323039, 0.9491898017824424),
        "ring_01": (0.15112867852248044, -0.27503519493065415, -0.540359982583664, 0.7807220076952411),
        "ring_02": (0.3042555445355691, 0.07194596043331655, -0.34567127310849854, 0.8847393476862221),
        "ring_03": (0.2701215748785559, -0.146710265022109, -0.36337515130716824, 0.8794708251754368),
        "pinky_01": (0.028430342490078378, -0.13765409582877344, -0.44215976249586564, 0.8858542825753338),
        "pinky_02": (0.18528716241427967, -0.10423428923627678, -0.27993270839024453, 0.9361845753723862),
        "pinky_03": (0.20503355408368013, -0.0659909896866002, -0.3494226159266155, 0.9118718476074358),
    },
}
# `rest`: the fingers as the mannequin stands, every finger rotation cleared.
SHAPES = ("rest",) + tuple(HANDS)


def hand_bones(side, shape):
    """A hand shape -> `{finger bone: rotation}` for that side; rest is all zeros."""
    out = {}
    for finger in FINGERS:
        if shape == "rest":
            rotation = [0.0, 0.0, 0.0]
        else:
            rotation = matrix_degrees(quaternion_matrix(HANDS[shape][finger]))
        out[f"{finger}_{side}"] = rotation if side == "l" else mirror_rotation(rotation)
    return out


# ---- reading and writing a pose by joints ---------------------------------------


def _parts(name):
    """`shoulder_l` -> (Joint, "l"); `spine` -> (Joint, None)."""
    side = side_of(name)
    joint = JOINTS.get(name[:-2] if side else name)
    if joint is None or (joint.name in SIDED) != bool(side):
        known = sorted([j for j in JOINTS if j not in SIDED] + [f"{j}_{s}" for j in SIDED for s in SIDES])
        raise ForgeError(f"there is no joint called {name!r}; the joints are {', '.join(known)}",
                         "pose.joint", joint=name, joints=known)
    return joint, side


def _bone_names(joint, side):
    return [f"{b}_{side}" if side else b for b in joint.bones]


def _angles(bones, joint, side):
    """A joint's angles in `{bone: rotation}`, unrounded; a shared joint's
    bones add up."""
    total = dict.fromkeys(joint.motions, 0.0)
    for bone in _bone_names(joint, side):
        rotation = bones.get(bone, [0.0, 0.0, 0.0])
        for motion, value in joint.read(mirror_rotation(rotation) if side == "r" else rotation).items():
            total[motion] += value
    return total


def joint_angles(pose, name):
    """One joint's three angles in a pose, in degrees, rounded to a tenth."""
    joint, side = _parts(name)
    return {m: round(v, 1) + 0.0 for m, v in _angles(pose["bones"], joint, side).items()}


def read(pose):
    """Every joint of a pose -> `{joint: {motion: degrees}}`."""
    names = [j for j in JOINTS if j not in SIDED] + [f"{j}_{s}" for j in JOINTS if j in SIDED for s in SIDES]
    return {name: joint_angles(pose, name) for name in names}


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value \
            or value in (float("inf"), float("-inf")):
        raise ForgeError(f"{what} must be a number of degrees", "pose.value")
    return float(value)


def set_joints(pose, motions):
    """`{"elbow_l.bend": 90, "hand_r": "fist", …}` -> the pose with those set.

    Motions not named keep the angle they had, read from the pose, so
    `elbow_l.bend=90` leaves the forearm's twist alone. A value past a joint's
    limits is refused with the range, never clamped.
    """
    if not isinstance(motions, dict) or not motions:
        raise ForgeError("joints is an object of joint.motion: degrees, or hand_l/hand_r: a shape",
                         "pose.shape")
    bones = dict(pose["bones"])
    wanted = {}
    for key, value in motions.items():
        if key in ("hand_l", "hand_r"):
            if value not in SHAPES:
                raise ForgeError(f"a hand is one of {', '.join(SHAPES)}; got {value!r}", "pose.hand",
                                 hand=key, shapes=list(SHAPES))
            bones.update(hand_bones(key[-1], value))
            continue
        name, dot, motion = key.partition(".")
        joint, _ = _parts(name)
        if not dot or motion not in joint.motions:
            raise ForgeError(f"{name} moves by {', '.join(joint.motions)}; got {key!r}", "pose.motion",
                             joint=name, motions=list(joint.motions))
        degrees = _number(value, key)
        low, high = joint.limits[motion]
        if not low <= degrees <= high:
            raise ForgeError(f"{key} goes from {low} to {high} degrees; got {degrees:g}", "pose.limit",
                             joint=name, motion=motion, low=low, high=high)
        wanted.setdefault(name, {})[motion] = degrees
    for name, chosen in wanted.items():
        joint, side = _parts(name)
        # The joint's other motions as the pose has them now, unrounded.
        angles = {**_angles(bones, joint, side), **chosen}
        share = {m: v / len(joint.bones) for m, v in angles.items()}
        rotation = joint.write(share)
        for bone in _bone_names(joint, side):
            bones[bone] = mirror_rotation(rotation) if side == "r" else rotation
    return {**pose, "bones": {k: [v + 0.0 for v in r] for k, r in sorted(bones.items()) if not _resting(r)}}


def mirrored_keys(motions):
    """The same motions for the other side as well: what `--mirror` sends. A
    centre joint is its own twin and is left as given."""
    out = dict(motions)
    for key, value in motions.items():
        name, dot, motion = key.partition(".")
        other = twin(name)
        if other != name:
            out.setdefault(f"{other}{dot}{motion}", value)
    return out


def vocabulary():
    """What `forge.py joints` prints: every joint, its motions, limits and words."""
    out = []
    for joint in JOINTS.values():
        out.append({"joint": f"{joint.name}_l/_r" if joint.name in SIDED else joint.name,
                    "bones": list(joint.bones),
                    "motions": {m: list(joint.limits[m]) for m in joint.motions},
                    "means": joint.words})
    out.append({"joint": "hand_l/_r", "shapes": list(SHAPES),
                "means": "the fingers: Pose Studio's hand presets, or rest"})
    return out
