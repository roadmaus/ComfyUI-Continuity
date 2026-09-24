// The image-to-3D tool's stage: a WebGL room with the mesh in it, and the
// picture it was lifted from standing where its camera stood.
//
// **The picture is in the scene, not beside it.** Pixal3D is pixel-aligned: it
// estimates the camera the photograph was taken with and back-projects each
// pixel into the volume along that camera's rays, so the picture has a real
// place relative to the mesh. Core's decoder hands the mesh back Y-up with the
// camera on +Z looking at the origin, at `pad · 0.5 / tan(fov / 2)` — pad 1 for
// one picture (its distance puts a unit-wide object across the frame), 1.1 for
// the multi-view rig (`_VIEW_PAD` in core). That is three.js's own default
// camera, so the picture's camera here is a plain PerspectiveCamera at
// (0, 0, d) with no conversion in between. Standing the picture on its image
// plane and drawing the frustum's four edges through it is the tool's thesis
// made visible; flying back to that camera and seeing the mesh sit exactly under
// its own photograph is the check that it worked.
//
// TRELLIS.2 is not aligned to any camera — its conditioning is a centred crop
// and a global embedding — so for it the caller passes no camera and the
// picture and its rays simply are not drawn.
//
// **Lit by its surroundings, and nothing else.** A mesh lifted from a photograph
// carries its own shading baked into the colour, and the one thing a stage
// light can add is a second, disagreeing sun. So there are no lamps of our own:
// the light is an environment — one of two Poly Haven HDRIs (`vendor/hdri`,
// `tools/vendor_hdri.py`) or three.js's procedural room — turned and dimmed as
// a whole, and the same picture can stand behind the mesh as its background.
//
// **The HDRI's sun is taken out of it and made a light** (`findSun`). Image
// based lighting in three.js is a prefiltered lookup, not a ray tracer: it
// gives colour and highlights from every direction but casts no shadow, so a
// noon sun would light the mesh from one side and leave nothing on the ground.
// The brightest compact patch of the picture is cut down to the sky around it
// in the copy that lights the scene, and exactly the energy removed becomes a
// directional light from that direction, which does cast shadows — onto the
// floor and onto the mesh itself. Nothing is counted twice and nothing is
// invented; the background keeps the untouched picture, sun and all. The
// ground also carries a contact shadow, which grounds the mesh whatever the
// light and says nothing about direction. Tone mapping
// is Khronos' PBR Neutral, which leaves a base colour the colour it was baked
// as; ACES, which this stage used before, shifted every photograph's hues.
//
// **What is shot is what the frame shows.** Photos and turntables are drawn
// through the frame the tool lays over the stage (`setFrame`): the stage's own
// camera with a view offset onto that rectangle, rendered at the shot's size on
// this same renderer. A second renderer would be a second WebGL context, and the
// environment and the shadow here are render targets that belong to this one:
// in any other context they are textures with nothing in them.
//
// **A photo can also be path traced** (`trace`), with three-gpu-pathtracer on
// a context of its own: light bounces, the mesh shades itself, reflections
// are real. It reads the same scene — the sky with its sun taken out and the
// sun as a light — so a render is the stage, traced, not a different set. It
// has no shadow catcher (upstream closed the request as not planned), so the
// ground is caught the way a renderer without one does it: a differential
// render (`trace`). And it needs an equirectangular picture to sample, so the
// procedural Neutral room cannot be traced.
//
// Everything three.js is vendored (`vendor/three`, `tools/vendor_three.py`);
// this module is the only one that imports it, so the rest of the pack never
// pays for 800 KB of WebGL it is not using.

import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";
import { RGBELoader } from "./vendor/three/RGBELoader.js";
import { RoomEnvironment } from "./vendor/three/RoomEnvironment.js";

const AMBER = 0xf0a63c;

/** The environments the stage can be lit by. `file` is under `vendor/hdri`;
 *  Neutral has none — it is the procedural room, blurred, as before. */
export const LIGHTS = {
  studio: { file: "studio_small_09_4k.hdr" },
  outdoor: { file: "noon_grass_4k.hdr" },
  neutral: { file: null },
};

/** The extra pictures a photo can be taken with, drawn from the geometry. */
export const PASSES = ["depth", "normals", "mask"];

// The contact shadow: how finely it is drawn, how far it is blurred, and how
// dark it lies. Fractions of the mesh's own size where they are distances.
const SHADOW_SIZE = 512;
const SHADOW_BLUR = 3.5;
const SHADOW_OPACITY = 0.7;
const SHADOW_SPREAD = 1.6;

// Where the picture stands along its own frustum, as a fraction of the camera's
// distance to the origin: most of the way from the lens to the subject, so the
// rays from it read as reaching *into* the object rather than as a card held at
// the camera. Past it they run on to this much beyond the origin.
const PLANE_AT = 0.42;
const RAYS_TO = 1.45;

/**
 * Smooth vertex normals for a mesh that came without any, welded by position.
 *
 * The GLBs the build writes carry no NORMAL attribute, and GLTFLoader answers
 * that by drawing the mesh flat-shaded. `computeVertexNormals` would not fix
 * it: an unwrapped mesh is split at every UV seam, so it would leave a crease
 * along each one. Here every copy of a point shares one normal — the
 * area-weighted sum of the faces around it — and the seams disappear.
 */
function smoothNormals(geometry) {
  const position = geometry.attributes.position;
  const count = position.count;
  geometry.computeBoundingBox();
  const size = geometry.boundingBox.getSize(new THREE.Vector3()).length() || 1;
  const scale = 1e6 / size;
  const weld = new Uint32Array(count);
  const seen = new Map();
  for (let v = 0; v < count; v += 1) {
    const key = `${Math.round(position.getX(v) * scale)},${Math.round(position.getY(v) * scale)},${Math.round(position.getZ(v) * scale)}`;
    let first = seen.get(key);
    if (first === undefined) seen.set(key, first = v);
    weld[v] = first;
  }
  const sums = new Float32Array(count * 3);
  const index = geometry.index;
  const faces = (index ? index.count : count) / 3;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let f = 0; f < faces; f += 1) {
    const i = index ? index.getX(f * 3) : f * 3;
    const j = index ? index.getX(f * 3 + 1) : f * 3 + 1;
    const k = index ? index.getX(f * 3 + 2) : f * 3 + 2;
    a.fromBufferAttribute(position, i);
    b.fromBufferAttribute(position, j).sub(a);
    c.fromBufferAttribute(position, k).sub(a);
    // Unnormalised on purpose: the cross product's length is twice the face's
    // area, so a sliver next to a big face barely moves the corner they share.
    b.cross(c);
    for (const v of [weld[i], weld[j], weld[k]]) {
      sums[v * 3] += b.x; sums[v * 3 + 1] += b.y; sums[v * 3 + 2] += b.z;
    }
  }
  const normals = new Float32Array(count * 3);
  for (let v = 0; v < count; v += 1) {
    const w = weld[v] * 3;
    a.set(sums[w], sums[w + 1], sums[w + 2]);
    if (a.lengthSq() === 0) a.set(0, 1, 0);
    a.normalize().toArray(normals, v * 3);
  }
  geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
}

const UP = new THREE.Vector3(0, 1, 0);

// The sun, as `findSun` looks for it: the patch within this angle of the
// brightest point, cut down to the level of the ring of sky out to twice it.
const SUN_CONE = THREE.MathUtils.degToRad(6);

/**
 * Find an HDRI's sun and take it out. -> `{sky, sun}`.
 *
 * `sky` is a copy of the picture with every pixel near the brightest point cut
 * down to the average of the sky around it (the picture itself when there is
 * no sun to cut); `sun` is what was cut — its direction in the file's own
 * frame, its colour, its strength as a directional light, and its share of all
 * the light in the picture — or null.
 *
 * Strength is irradiance, the sum of radiance times solid angle over what was
 * removed, which is the unit three's directional light and its environment
 * lighting share: the light taken out of the one is exactly the light put back
 * by the other. A studio's brightest softbox is found the same way; it is
 * rarely much brighter than the room around it, so little is cut and the light
 * made of it is faint.
 *
 * The file is read on a grid about 1k wide to find the peak and the sky level,
 * and in full only across the band of rows the sun can be in.
 */
export function findSun(texture) {
  const { data, width, height } = texture.image;
  const channels = data.length / (width * height);
  const half = texture.type === THREE.HalfFloatType;
  const read = half ? (i) => THREE.DataUtils.fromHalfFloat(data[i]) : (i) => data[i];
  const luminance = (i) => 0.2126 * read(i) + 0.7152 * read(i + 1) + 0.0722 * read(i + 2);
  // Row 0 is the top of the sky (the loader flips it on upload), and a
  // column's longitude follows three's `equirectUv`.
  const toward = (row, col, into) => {
    const lat = (0.5 - (row + 0.5) / height) * Math.PI;
    const lon = ((col + 0.5) / width - 0.5) * 2 * Math.PI;
    return into.set(Math.cos(lat) * Math.cos(lon), Math.sin(lat), Math.cos(lat) * Math.sin(lon));
  };
  const step = Math.max(1, Math.round(width / 1024));
  let peak = -1;
  let peakAt = [0, 0];
  for (let row = 0; row < height; row += step) {
    for (let col = 0; col < width; col += step) {
      const value = luminance((row * width + col) * channels);
      if (value > peak) { peak = value; peakAt = [row, col]; }
    }
  }
  const centre = toward(peakAt[0], peakAt[1], new THREE.Vector3());
  const inner = Math.cos(SUN_CONE);
  const outer = Math.cos(SUN_CONE * 2);
  const at = new THREE.Vector3();
  let ring = 0;
  let ringWeight = 0;
  for (let row = 0; row < height; row += step) {
    for (let col = 0; col < width; col += step) {
      const dot = toward(row, col, at).dot(centre);
      if (dot >= inner || dot < outer) continue;
      const weight = Math.cos((0.5 - (row + 0.5) / height) * Math.PI);
      ring += luminance((row * width + col) * channels) * weight;
      ringWeight += weight;
    }
  }
  const level = ringWeight ? ring / ringWeight : peak;

  const cut = data.slice();
  const pixel = (2 * Math.PI / width) * (Math.PI / height);
  const removed = [0, 0, 0];
  const aim = new THREE.Vector3();
  const peakLat = (0.5 - (peakAt[0] + 0.5) / height) * Math.PI;
  const band = Math.ceil((SUN_CONE / Math.PI) * height) + 1;
  for (let row = Math.max(0, peakAt[0] - band); row <= Math.min(height - 1, peakAt[0] + band); row += 1) {
    const lat = (0.5 - (row + 0.5) / height) * Math.PI;
    if (Math.abs(lat - peakLat) > SUN_CONE) continue;
    const omega = pixel * Math.cos(lat);
    for (let col = 0; col < width; col += 1) {
      if (toward(row, col, at).dot(centre) < inner) continue;
      const i = (row * width + col) * channels;
      const value = luminance(i);
      if (value <= level) continue;
      const keep = level / value;
      for (let c = 0; c < 3; c += 1) {
        const was = read(i + c);
        removed[c] += was * (1 - keep) * omega;
        cut[i + c] = half ? THREE.DataUtils.toHalfFloat(was * keep) : was * keep;
      }
      aim.addScaledVector(at, (value - level) * omega);
    }
  }
  let total = 0;
  for (let row = 0; row < height; row += step) {
    const weight = Math.cos((0.5 - (row + 0.5) / height) * Math.PI) * pixel * step * step;
    for (let col = 0; col < width; col += step) total += luminance((row * width + col) * channels) * weight;
  }
  const strength = Math.max(...removed);
  if (!(strength > 0) || aim.lengthSq() === 0) return { sky: texture, sun: null };

  const sky = new THREE.DataTexture(cut, width, height, texture.format, texture.type);
  for (const key of ["mapping", "colorSpace", "flipY", "minFilter", "magFilter", "generateMipmaps"]) {
    sky[key] = texture[key];
  }
  sky.needsUpdate = true;
  const sunLight = 0.2126 * removed[0] + 0.7152 * removed[1] + 0.0722 * removed[2];
  return {
    sky,
    sun: {
      direction: aim.normalize(),
      color: new THREE.Color(removed[0] / strength, removed[1] / strength, removed[2] / strength),
      intensity: strength,
      share: total > 0 ? sunLight / total : 0,
    },
  };
}

const reduced = () => matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

export class LiftStage {
  /** @param {HTMLElement} host  the box the canvas fills; it is measured, not styled */
  constructor(host) {
    this.host = host;
    this.canvas = document.createElement("canvas");
    this.canvas.className = "mmc-lf-gl";
    host.appendChild(this.canvas);

    const renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.NeutralToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer = renderer;

    const scene = new THREE.Scene();
    this.scene = scene;
    this.paintGround();
    this.pmrem = new THREE.PMREMGenerator(renderer);
    this.lights = new Map();         // id -> Promise<{environment, background, sun}>
    this.light = null;               // the id on the stage now
    this.surroundings = false;       // whether the environment is the background too
    this.blur = 0;

    this.grid = new THREE.GridHelper(6, 24, 0x3a3f48, 0x262a31);
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.7;
    scene.add(this.grid);
    this.buildShadow();
    this.buildSun();

    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 60);
    this.camera.position.set(1.6, 0.9, 2.2);
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 0.4;
    this.controls.maxDistance = 8;
    this.controls.addEventListener("start", () => {
      this.flight = null;
      this.onLeave?.();
    });

    this.loader = new GLTFLoader();
    this.loaded = new Map();         // url -> Promise<THREE.Object3D>
    this.model = null;               // what is on the stage now
    this.wire = null;
    this.mode = "textured";
    this.shading = "smooth";
    this.pictureCamera = null;       // {position, fov} or null
    this.picture = null;
    this.rays = null;
    this.flight = null;
    this.frame = null;               // {aspect, insets} while a frame is laid over the stage

    this.resize();
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(host);
    this.raf = requestAnimationFrame((now) => this.tick(now));
  }

  /** The stage's ground follows the pack's surface, whatever palette is up. */
  paintGround() {
    const ground = getComputedStyle(this.host).getPropertyValue("--mmc-media-bg").trim() || "#0f1115";
    try { this.scene.background = new THREE.Color(ground); }
    catch { this.scene.background = new THREE.Color(0x0f1115); }
  }

  // ---- the light ---------------------------------------------------------------

  /** Light the stage with one of `LIGHTS`. Resolves once it is up. */
  async setLight(id) {
    if (!LIGHTS[id]) throw new Error(`no light called ${id}`);
    this.light = id;
    const light = await this.readLight(id);
    if (this.light !== id || !this.pmrem) return;   // another was picked meanwhile, or closed
    this.scene.environment = light.environment;
    this.sunOf = light.sun;
    this.placeSun();
    this.paintBackground();
  }

  /** One environment, prefiltered once per open: `{environment, background, sun}`.
   *  `environment` is lit from the picture with its sun taken out; `sun` is
   *  that sun as `findSun` measured it, or null when there is none. */
  readLight(id) {
    if (!this.lights.has(id)) {
      const { file } = LIGHTS[id];
      this.lights.set(id, (file
        ? new RGBELoader().loadAsync(new URL(`./vendor/hdri/${file}`, import.meta.url).href)
          .then((texture) => {
            texture.mapping = THREE.EquirectangularReflectionMapping;
            const { sky, sun } = findSun(texture);
            const environment = this.pmrem.fromEquirectangular(sky).texture;
            // The sky stays in memory for `trace`; only its upload is let go.
            if (sky !== texture) sky.dispose();
            return { environment, background: texture, sky, sun };
          })
        : Promise.resolve().then(() => {
            const environment = this.pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
            return { environment, background: environment, sky: null, sun: null };
          })
      ).catch((error) => {
        this.lights.delete(id);
        throw error;
      }));
    }
    return this.lights.get(id);
  }

  /** Turn the light around the mesh, in degrees. The background turns with it. */
  setTurn(degrees) {
    const y = THREE.MathUtils.degToRad(degrees);
    this.turn = y;
    this.scene.environmentRotation.set(0, y, 0);
    this.scene.backgroundRotation.set(0, y, 0);
    this.placeSun();
  }

  /** How strongly the environment lights the mesh, and how bright it shows behind.
   *  The sun is part of the environment, so it follows. */
  setBrightness(value) {
    this.brightness = value;
    this.scene.environmentIntensity = value;
    this.scene.backgroundIntensity = value;
    this.placeSun();
  }

  // ---- the sun -----------------------------------------------------------------

  buildSun() {
    this.turn = 0;
    this.brightness = 1;
    this.sunStrength = 1;
    this.sunOf = null;
    const sun = new THREE.DirectionalLight(0xffffff, 0);
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0003;
    sun.shadow.normalBias = 0.01;
    this.sun = sun;
    this.scene.add(sun, sun.target);
    // What catches the sun's shadow on the floor: nothing but the darkening.
    this.catcher = new THREE.Mesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
                                  new THREE.ShadowMaterial({ opacity: 0.5, depthWrite: false }));
    this.catcher.receiveShadow = true;
    this.catcher.renderOrder = 1;
    this.ground.add(this.catcher);
  }

  /** How much of the HDRI's sun is let back in as a light: 1 is all of it, 0
   *  none — which leaves the scene that much darker, since it was taken out of
   *  the environment. */
  setSunStrength(value) {
    this.sunStrength = value;
    this.placeSun();
  }

  /**
   * Aim the sun, size its shadow to the mesh, and set how strong it is.
   *
   * The environment is looked up at `R(-turn) · direction` (three negates the
   * rotation before it reaches the shader), so a patch of the picture seen
   * along `d` in the file is seen along `R(turn) · d` in the room; the sun
   * turns the same way.
   */
  placeSun() {
    const sun = this.sun;
    const found = this.sunOf;
    if (!sun) return;
    const direction = found ? found.direction.clone().applyAxisAngle(UP, this.turn) : null;
    // A sun under the floor is behind the floor.
    const lit = !!found && direction.y > 0.02 && this.sunStrength > 0;
    sun.visible = lit;
    sun.castShadow = lit;
    this.catcher.visible = lit;
    if (!lit) return;
    sun.color.copy(found.color);
    sun.intensity = found.intensity * this.brightness * this.sunStrength;
    const box = this.model ? new THREE.Box3().setFromObject(this.model) : null;
    const centre = box && !box.isEmpty() ? box.getCenter(new THREE.Vector3()) : new THREE.Vector3();
    const radius = box && !box.isEmpty() ? box.getSize(new THREE.Vector3()).length() / 2 : 0.5;
    sun.target.position.copy(centre);
    sun.position.copy(centre).addScaledVector(direction, radius * 4);
    // A low sun throws a long shadow; the frustum is wide enough for one to
    // about three mesh-lengths.
    const reach = radius * (1 + Math.min(3, 1 / Math.max(direction.y, 0.25)));
    Object.assign(sun.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach,
                                       near: radius * 0.5, far: radius * 8 });
    sun.shadow.camera.updateProjectionMatrix();
    sun.shadow.normalBias = radius * 0.01;
    sun.target.updateMatrixWorld();
    // The shadow on the floor is as dark as the sun is a share of the light.
    this.catcher.material.opacity = Math.min(0.75, 0.2 + found.share * this.sunStrength * 0.8);
  }

  /** Whether the environment stands behind the mesh, and how soft it is there. */
  setSurroundings(on, blur = this.blur) {
    this.surroundings = !!on;
    this.blur = blur;
    this.paintBackground();
  }

  async paintBackground() {
    const light = this.light && await this.lights.get(this.light)?.catch(() => null);
    if (this.surroundings && light) {
      this.scene.background = light.background;
      this.scene.backgroundBlurriness = this.blur;
    } else {
      this.paintGround();
      this.scene.backgroundBlurriness = 0;
    }
    // A grid in front of a field reads as a fence; the ground is the shadow.
    this.grid.visible = !this.surroundings;
  }

  // ---- the ground ----------------------------------------------------------------

  /**
   * The contact shadow: the mesh drawn from below as depth, blurred twice, and
   * laid on the floor as darkness — three.js's own contact-shadow example, in
   * the pack's words. Drawn once per mesh (`bakeShadow`), not per frame: the
   * mesh does not move and nothing the light does changes it.
   */
  buildShadow() {
    const target = () => {
      const made = new THREE.WebGLRenderTarget(SHADOW_SIZE, SHADOW_SIZE);
      made.texture.generateMipmaps = false;
      return made;
    };
    this.shadowTarget = target();
    this.shadowBlurTarget = target();
    const plane = new THREE.PlaneGeometry(1, 1).rotateX(Math.PI / 2);
    this.shadow = new THREE.Mesh(plane, new THREE.MeshBasicMaterial({
      map: this.shadowTarget.texture, transparent: true, opacity: SHADOW_OPACITY, depthWrite: false,
      toneMapped: false }));
    // The plane is turned to face down; the flip turns it back up, and with it
    // the depth render that was drawn looking up at the mesh from below.
    this.shadow.scale.y = -1;
    this.shadow.renderOrder = 1;
    this.shadowCamera = new THREE.OrthographicCamera(-0.5, 0.5, 0.5, -0.5, 0, 1);
    this.shadowCamera.rotation.x = Math.PI / 2;
    // A group of their own, so the plane's size is its scale and the camera
    // (sized by its frustum) is never scaled with it.
    this.ground = new THREE.Group();
    this.ground.add(this.shadow, this.shadowCamera);
    this.ground.visible = false;
    this.scene.add(this.ground);
    this.shadowOn = true;

    // Depth as darkness: what touches the floor is black, what stands a
    // mesh-height above it is nothing.
    this.shadowDepth = new THREE.MeshDepthMaterial({ depthTest: false, depthWrite: false });
    this.shadowDepth.onBeforeCompile = (shader) => {
      shader.fragmentShader = shader.fragmentShader.replace(
        "gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );",
        "gl_FragColor = vec4( vec3( 0.0 ), pow( 1.0 - fragCoordZ, 1.6 ) );");
    };
    this.shadowScene = new THREE.Scene();
    this.shadowScene.overrideMaterial = this.shadowDepth;
    this.blurMaterial = new THREE.ShaderMaterial({
      uniforms: { map: { value: null }, step: { value: new THREE.Vector2() } },
      vertexShader: "varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
      // Nine taps of a Gaussian along `step`.
      fragmentShader: `uniform sampler2D map; uniform vec2 step; varying vec2 vUv;
        void main() {
          vec4 sum = texture2D(map, vUv) * 0.1633;
          sum += (texture2D(map, vUv - step) + texture2D(map, vUv + step)) * 0.1531;
          sum += (texture2D(map, vUv - 2.0 * step) + texture2D(map, vUv + 2.0 * step)) * 0.12245;
          sum += (texture2D(map, vUv - 3.0 * step) + texture2D(map, vUv + 3.0 * step)) * 0.0918;
          sum += (texture2D(map, vUv - 4.0 * step) + texture2D(map, vUv + 4.0 * step)) * 0.051;
          gl_FragColor = sum;
        }`,
      depthTest: false, depthWrite: false,
    });
    this.blurQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.blurMaterial);
    this.blurCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  }

  /** Whether the mesh casts its contact shadow. */
  setShadow(on) {
    this.shadowOn = !!on;
    this.ground.visible = this.shadowOn && !!this.model;
  }

  /** Lay the shadow under the mesh on the stage now. */
  bakeShadow() {
    const root = this.model;
    this.ground.visible = false;
    if (!root) return;
    const box = new THREE.Box3().setFromObject(root);
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    const span = Math.max(size.x, size.z) * SHADOW_SPREAD + size.y * 0.5;
    this.ground.position.set(centre.x, box.min.y + 0.001, centre.z);
    this.shadow.scale.set(span, -1, span);
    this.catcher.scale.set(span * 6, 1, span * 6);
    this.catcher.position.y = -0.0005;
    Object.assign(this.shadowCamera, { left: -span / 2, right: span / 2, top: span / 2,
                                        bottom: -span / 2, near: 0, far: Math.max(size.y, 1e-3) });
    this.shadowCamera.updateProjectionMatrix();
    this.ground.updateMatrixWorld(true);

    const renderer = this.renderer;
    const clear = renderer.getClearAlpha();
    const parent = root.parent;
    this.shadowScene.add(root);
    renderer.setClearAlpha(0);
    renderer.setRenderTarget(this.shadowTarget);
    renderer.clear();
    renderer.render(this.shadowScene, this.shadowCamera);
    parent?.add(root);
    for (const amount of [SHADOW_BLUR, SHADOW_BLUR * 0.4]) {
      this.blurPass(this.shadowTarget, this.shadowBlurTarget, amount, 0);
      this.blurPass(this.shadowBlurTarget, this.shadowTarget, 0, amount);
    }
    renderer.setRenderTarget(null);
    renderer.setClearAlpha(clear);
    this.ground.visible = this.shadowOn;
  }

  blurPass(from, into, x, y) {
    this.blurMaterial.uniforms.map.value = from.texture;
    this.blurMaterial.uniforms.step.value.set(x / SHADOW_SIZE, y / SHADOW_SIZE);
    this.renderer.setRenderTarget(into);
    this.renderer.render(this.blurQuad, this.blurCamera);
  }

  resize() {
    const { width, height } = this.host.getBoundingClientRect();
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  tick(now) {
    this.raf = requestAnimationFrame((next) => this.tick(next));
    if (this.flight) this.flight(now);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  // ---- the picture and its camera --------------------------------------------

  /**
   * Stand the picture where it was taken from — or take it away.
   *
   * @param {{fov: number, pad: number}|null} camera  horizontal fov in degrees
   * @param {string|null} url  the square crop the model was conditioned on
   */
  setPicture(camera, url) {
    this.clearPicture();
    if (!camera?.fov) { this.pictureCamera = null; return; }
    const fov = camera.fov;
    const half = THREE.MathUtils.degToRad(fov) / 2;
    const distance = (camera.pad ?? 1) * 0.5 / Math.tan(half);
    // The crop is square, so its horizontal field of view is its vertical one
    // too — which is the one a three.js camera is specified by.
    this.pictureCamera = { position: new THREE.Vector3(0, 0, distance), fov };

    const group = new THREE.Group();
    const at = distance * PLANE_AT;
    const side = 2 * at * Math.tan(half);
    if (url) {
      const texture = new THREE.TextureLoader().load(url);
      texture.colorSpace = THREE.SRGBColorSpace;
      const plane = new THREE.Mesh(
        new THREE.PlaneGeometry(side, side),
        new THREE.MeshBasicMaterial({ map: texture, transparent: true, toneMapped: false,
                                      side: THREE.DoubleSide, depthWrite: false }));
      plane.position.set(0, 0, distance - at);
      group.add(plane);
      this.plane = plane;
    }
    const edge = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.PlaneGeometry(side, side)),
      new THREE.LineBasicMaterial({ color: 0xdde1e6, transparent: true, opacity: 0.45 }));
    edge.position.set(0, 0, distance - at);
    group.add(edge);

    // The four rays: lens to the picture's corners in amber, and on past the
    // subject fading out. They are the back-projection, drawn.
    const eye = new THREE.Vector3(0, 0, distance);
    const points = [];
    const colors = [];
    const lit = new THREE.Color(AMBER);
    const fade = new THREE.Color(0x14161a);
    for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      const corner = new THREE.Vector3(sx * side / 2, sy * side / 2, distance - at);
      const far = eye.clone().lerp(corner, RAYS_TO * distance / at);
      points.push(eye, corner, corner.clone(), far);
      colors.push(...lit.toArray(), ...lit.toArray(), ...lit.toArray(), ...fade.toArray());
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    this.rays = new THREE.LineSegments(geometry,
      new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.8 }));
    group.add(this.rays);

    this.picture = group;
    this.scene.add(group);
  }

  clearPicture() {
    if (!this.picture) return;
    this.scene.remove(this.picture);
    this.picture.traverse((part) => {
      part.geometry?.dispose?.();
      part.material?.map?.dispose?.();
      part.material?.dispose?.();
    });
    this.picture = null;
    this.plane = null;
    this.rays = null;
  }

  /** Whether the picture and its rays are drawn. The camera stays known either way. */
  showPicture(on) {
    if (this.picture) this.picture.visible = !!on;
  }

  /** How much of the picture shows: half at its own camera, so the mesh
   *  underneath can be checked against it; whole everywhere else. */
  pictureOpacity(value) {
    if (this.plane) this.plane.material.opacity = value;
  }

  /** Fly to the picture's camera. Resolves when the view is there. */
  toPicture() {
    if (!this.pictureCamera) return Promise.resolve(false);
    return this.flyTo(this.pictureCamera.position, new THREE.Vector3(0, 0, 0),
                      this.pictureCamera.fov).then(() => true);
  }

  /** A three-quarter view that shows the picture, its rays and the mesh at once. */
  toOverview() {
    const d = this.pictureCamera?.position.z ?? 1.4;
    return this.flyTo(new THREE.Vector3(d * 1.25, d * 0.55, d * 0.95), new THREE.Vector3(0, 0, 0), 40);
  }

  flyTo(position, target, fov) {
    return new Promise((done) => {
      const p0 = this.camera.position.clone();
      const t0 = this.controls.target.clone();
      const f0 = this.camera.fov;
      const start = performance.now();
      const ms = reduced() ? 0 : 700;
      this.flight = (now) => {
        const k = ms ? Math.min(1, (now - start) / ms) : 1;
        const e = 1 - Math.pow(1 - k, 3);
        this.camera.position.lerpVectors(p0, position, e);
        this.controls.target.lerpVectors(t0, target, e);
        this.camera.fov = f0 + (fov - f0) * e;
        this.camera.updateProjectionMatrix();
        if (k >= 1) { this.flight = null; done(); }
      };
    });
  }

  // ---- the mesh ---------------------------------------------------------------

  /** Load a GLB once. Every stage's file is fetched at most once per open. */
  load(url) {
    if (!this.loaded.has(url)) {
      this.loaded.set(url, new Promise((resolve, reject) => {
        this.loader.load(url, (gltf) => {
          const root = gltf.scene;
          root.traverse((part) => {
            if (!part.isMesh) return;
            if (!part.geometry.attributes.normal) smoothNormals(part.geometry);
            part.castShadow = true;
            part.receiveShadow = true;
            part.userData.own = part.material;
          });
          resolve(root);
        }, undefined, (error) => {
          this.loaded.delete(url);
          reject(error);
        });
      }));
    }
    return this.loaded.get(url);
  }

  /**
   * Put a mesh on the stage. `look` is how a stage's file is meant to be
   * seen: "clay" for geometry that carries no colour yet (the voxels, the
   * shape), "own" for what it carries (vertex colours, baked maps).
   */
  async show(url, look = "own") {
    const root = url ? await this.load(url) : null;
    if (this.model && this.model !== root) this.scene.remove(this.model);
    this.dropWire();
    this.model = root;
    this.look = look;
    if (!root) { this.ground.visible = false; return; }
    this.scene.add(root);
    const box = new THREE.Box3().setFromObject(root);
    if (!box.isEmpty()) this.grid.position.y = box.min.y - 0.002;
    this.bakeShadow();
    this.placeSun();
    this.applyMode();
  }

  /** How its normals are read: "smooth" across faces, or "flat" per face. */
  setShading(shading) {
    this.shading = shading;
    this.applyMode();
  }

  /** How the mesh is drawn: textured, clay, wire or normals. */
  setMode(mode) {
    this.mode = mode;
    this.applyMode();
  }

  applyMode() {
    const root = this.model;
    if (!root) return;
    const mode = this.look === "clay" && this.mode === "textured" ? "clay" : this.mode;
    this.clay ??= new THREE.MeshStandardMaterial({ color: 0xb9b4ac, roughness: 0.85 });
    this.dark ??= new THREE.MeshStandardMaterial({ color: 0x2a2e35, roughness: 0.9 });
    this.normals ??= new THREE.MeshNormalMaterial();
    const flat = this.shading === "flat";
    this.dropWire();
    root.traverse((part) => {
      if (!part.isMesh) return;
      part.material = mode === "clay" ? this.clay
        : mode === "wire" ? this.dark
          : mode === "normals" ? this.normals
            : part.userData.own;
      // Flat is the shader's own derivative normal rather than a split copy of
      // the geometry: nothing new in memory, and every face reads as one plane
      // whatever the file's normals say.
      for (const material of [].concat(part.material)) {
        if (material.flatShading === flat) continue;
        material.flatShading = flat;
        material.needsUpdate = true;
      }
    });
    if (mode === "wire") {
      // A wireframe material over the same geometry rather than
      // WireframeGeometry: a 200k-face mesh as explicit line segments is a
      // second copy of every edge in memory, and this draws the same lines.
      this.wire = root.clone();
      this.wire.traverse((part) => {
        if (!part.isMesh) return;
        part.castShadow = false;
        part.receiveShadow = false;
        part.material = this.wireMaterial ??= new THREE.MeshBasicMaterial({
          color: 0xdde1e6, wireframe: true, transparent: true, opacity: 0.35 });
      });
      this.scene.add(this.wire);
    }
  }

  dropWire() {
    if (!this.wire) return;
    this.scene.remove(this.wire);
    this.wire = null;
  }

  // ---- the frame and the shots ---------------------------------------------------

  /**
   * Lay a frame over the stage, or take it away. `aspect` is width over
   * height; `insets` is the room the tool's own controls take along each edge
   * of the canvas, in CSS pixels, so the frame sits in what is left of it.
   */
  setFrame(frame) {
    this.frame = frame ? { aspect: frame.aspect, insets: { top: 0, right: 0, bottom: 0, left: 0,
                                                           ...frame.insets } } : null;
  }

  /** The frame's rectangle on the canvas in CSS pixels, or null without one. */
  frameRect() {
    if (!this.frame) return null;
    const { width, height } = this.host.getBoundingClientRect();
    const { top, right, bottom, left } = this.frame.insets;
    const room = { w: Math.max(1, width - left - right), h: Math.max(1, height - top - bottom) };
    const w = Math.min(room.w, room.h * this.frame.aspect);
    const h = w / this.frame.aspect;
    return { x: left + (room.w - w) / 2, y: top + (room.h - h) / 2, w, h, width, height };
  }

  /** The stage's camera, looking through the frame: a view offset onto its
   *  rectangle, so the shot is exactly what the frame shows. */
  shotCamera(base = this.camera) {
    const camera = base.clone();
    const rect = this.frameRect();
    if (rect) {
      camera.aspect = rect.width / rect.height;
      camera.setViewOffset(rect.width, rect.height, rect.x, rect.y, rect.w, rect.h);
    }
    camera.updateProjectionMatrix();
    return camera;
  }

  /** A shot's pixel size: `long` along the frame's longer side, both even. */
  shotSize(long) {
    const aspect = this.frame?.aspect ?? this.camera.aspect;
    const even = (n) => Math.max(2, Math.round(n / 2) * 2);
    return aspect >= 1 ? { width: even(long), height: even(long / aspect) }
      : { width: even(long * aspect), height: even(long) };
  }

  /**
   * Draw one picture at `width` × `height` into a 2D canvas, on this renderer.
   *
   * The drawing buffer is resized, drawn into and copied out in one go, with no
   * await in between, so the page never composites the canvas at the shot's
   * size and the copy never finds the buffer cleared.
   */
  snap(camera, width, height) {
    const renderer = this.renderer;
    const ratio = renderer.getPixelRatio();
    const size = renderer.getSize(new THREE.Vector2());
    const out = document.createElement("canvas");
    out.width = width;
    out.height = height;
    try {
      renderer.setPixelRatio(1);
      renderer.setSize(width, height, false);
      renderer.render(this.scene, camera);
      out.getContext("2d").drawImage(this.canvas, 0, 0);
    } finally {
      renderer.setPixelRatio(ratio);
      renderer.setSize(size.x, size.y, false);
    }
    return out;
  }

  /** Hide what is the stage's and not the scene's for the length of `draw`:
   *  the picture and its rays, and the grid. */
  async staged(draw) {
    const was = { picture: this.picture?.visible, grid: this.grid.visible };
    this.showPicture(false);
    this.grid.visible = false;
    try {
      return await draw();
    } finally {
      this.showPicture(was.picture);
      this.grid.visible = was.grid;
    }
  }

  /**
   * Take a photo through the frame. -> `{beauty, depth?, normals?, mask?}`,
   * each a PNG Blob. `passes` names the extras, from `PASSES`.
   *
   * The passes are the mesh alone on black, drawn from its geometry: depth is
   * near-bright and far-dark across the mesh's own depth, the way the
   * blockout bench and Depth Anything draw it; normals are view-space, red
   * right, green up and blue toward the camera; the mask is the silhouette.
   * Black is no normal at all, so a normals pass says where the mesh is too.
   */
  async photo({ long = 2048, passes = [], beauty = true } = {}) {
    if (!this.model) throw new Error("there is no mesh on the stage");
    const { width, height } = this.shotSize(long);
    const camera = this.shotCamera();
    return this.staged(async () => {
      const shots = beauty ? { beauty: this.snap(camera, width, height) } : {};
      const wanted = PASSES.filter((pass) => passes.includes(pass));
      if (wanted.length) {
        const kept = { background: this.scene.background, blur: this.scene.backgroundBlurriness,
                       ground: this.ground.visible, wire: this.wire?.visible };
        this.scene.background = new THREE.Color(0x000000);
        this.scene.backgroundBlurriness = 0;
        this.ground.visible = false;
        if (this.wire) this.wire.visible = false;
        try {
          for (const pass of wanted) {
            this.scene.overrideMaterial = this.passMaterial(pass, camera);
            shots[pass] = this.snap(camera, width, height);
          }
        } finally {
          this.scene.overrideMaterial = null;
          this.scene.background = kept.background;
          this.scene.backgroundBlurriness = kept.blur;
          this.ground.visible = kept.ground;
          if (this.wire) this.wire.visible = kept.wire;
        }
      }
      const blobs = {};
      for (const [name, canvas] of Object.entries(shots)) {
        blobs[name] = await new Promise((done) => canvas.toBlob(done, "image/png"));
      }
      return blobs;
    });
  }

  /** Whether `trace` can render the stage as it is set now, and if not, why. */
  traceable() {
    if (!this.model) return "no mesh";
    if (this.light === "neutral") return "neutral";
    if (this.mode === "wire" || this.mode === "normals") return "mode";
    return null;
  }

  /**
   * Path trace a photo through the frame. -> a PNG Blob, or null if stopped.
   *
   * `onSample(done, of)` reports progress across every pass; `stopped()` is
   * asked between samples.
   *
   * **The ground is a differential render.** three-gpu-pathtracer has no
   * shadow catcher — `ShadowMaterial` means nothing to it, and its `matte`
   * hides a surface's shadows along with the surface — so with the ground
   * shadow on, three pictures are traced with the same noise sequence
   * (`stableNoise`): the mesh on a floor, the floor alone, and the background
   * alone. Where the floor is, the first over the second is exactly what the
   * mesh does to it — its shadow, and whatever light it bounces — and that
   * ratio is laid onto the background. The floor itself is never seen. The
   * mesh is the first picture, over the rest by its coverage. All of it is
   * done in linear light, from the tracer's float targets, and tone mapped
   * once at the end with the stage's own curve.
   *
   * The tracer gets a renderer of its own, sized to the photo, so the stage
   * keeps drawing while it works; everything it reads — the mesh's buffers and
   * pictures, the sky's pixels — is on the CPU and uploads to any context.
   */
  async trace({ long = 2048, samples = 256, onSample, stopped } = {}) {
    const refused = this.traceable();
    if (refused) throw new Error(`this stage cannot be path traced (${refused})`);
    const light = await this.lights.get(this.light);
    const { WebGLPathTracer } = await import("./vendor/three/three-gpu-pathtracer.module.js");
    const { width, height } = this.shotSize(long);
    const camera = this.shotCamera();
    const renderer = new THREE.WebGLRenderer({ antialias: false });
    renderer.setPixelRatio(1);
    renderer.setSize(width, height, false);
    const tracer = new WebGLPathTracer(renderer);
    Object.assign(tracer, { renderDelay: 0, fadeDuration: 0, minSamples: 1, rasterizeScene: false,
                            dynamicLowRes: false, renderScale: 1, renderToCanvas: false, stableNoise: true });
    tracer.tiles.set(2, 2);

    let floor = null;
    if (this.shadowOn) {
      const box = new THREE.Box3().setFromObject(this.model);
      floor = new THREE.Mesh(
        new THREE.CircleGeometry(box.getSize(new THREE.Vector3()).length() * 20, 96).rotateX(-Math.PI / 2),
        new THREE.MeshStandardMaterial({ color: 0xcccccc, roughness: 1 }));
      floor.position.y = box.min.y;
      floor.updateMatrixWorld();
    }
    // The background is the same in every pass and needs few samples; the two
    // the ratio is taken between need the same count, or their noise stops
    // cancelling.
    const passes = floor
      ? [{ name: "full", model: true, floor: true, count: samples },
         { name: "floor", model: false, floor: true, count: samples },
         { name: "sky", model: false, floor: false, count: Math.max(16, samples >> 2) }]
      : [{ name: "full", model: true, floor: false, count: samples }];
    const total = passes.reduce((sum, pass) => sum + pass.count, 0);
    const traced = {};
    let before = 0;
    try {
      for (const pass of passes) {
        this.lend(() => tracer.setScene(this.scene, camera), light.sky, pass.model, pass.floor && floor);
        while (tracer.samples < pass.count) {
          if (stopped?.()) return null;
          tracer.renderSample();
          onSample?.(before + Math.min(pass.count, Math.floor(tracer.samples)), total);
          await new Promise((next) => requestAnimationFrame(next));
        }
        before += pass.count;
        const pixels = new Float32Array(width * height * 4);
        renderer.readRenderTargetPixels(tracer.target, 0, 0, width, height, pixels);
        traced[pass.name] = pixels;
      }
    } finally {
      // Not `tracer.dispose()`: in 0.0.23 it reaches for a `_renderQuad` the
      // class never makes, and throws. The context going is what frees it all.
      renderer.dispose();
      renderer.forceContextLoss();
    }

    const linear = floor ? this.caught(traced, camera, width, height, floor) : traced.full;
    floor?.geometry.dispose();
    floor?.material.dispose();
    return this.developed(linear, width, height);
  }

  /** Hand the scene to the tracer for one pass: the sky it can sample for the
   *  environment, the stage's furniture out of it, the mesh and the floor in
   *  or out as the pass wants. Put back as soon as it has been read. */
  lend(read, sky, model, floor) {
    const scene = this.scene;
    const kept = { environment: scene.environment, ground: this.ground.visible,
                   wire: this.wire?.visible, picture: this.picture?.visible, model: this.model.visible };
    try {
      scene.environment = sky;
      this.ground.visible = false;
      if (this.wire) this.wire.visible = false;
      this.showPicture(false);
      this.model.visible = model;
      if (floor) scene.add(floor);
      read();
    } finally {
      if (floor) scene.remove(floor);
      scene.environment = kept.environment;
      this.ground.visible = kept.ground;
      if (this.wire) this.wire.visible = kept.wire;
      this.showPicture(kept.picture);
      this.model.visible = kept.model;
    }
  }

  /**
   * Put the traced ground under the traced mesh. -> linear RGBA, bottom row first.
   *
   * Everywhere but the mesh: the background, times what the mesh did to the
   * floor there (full ÷ floor alone) where there is floor. Over that, the
   * mesh, by its coverage. Coverage comes from the rasteriser at the same size
   * and through the same camera, antialiased, so the edges blend.
   */
  caught({ full, floor: bare, sky }, camera, width, height, floor) {
    const mesh = this.coverage(camera, width, height, true, null);
    const ground = this.coverage(camera, width, height, false, floor);
    const out = new Float32Array(width * height * 4);
    const tiny = 1e-4;
    for (let y = 0; y < height; y += 1) {
      // The traced targets start at the bottom row; the coverage canvases at the top.
      const flipped = (height - 1 - y) * width;
      for (let x = 0; x < width; x += 1) {
        const i = (y * width + x) * 4;
        const on = mesh[flipped + x];
        const under = ground[flipped + x];
        for (let c = 0; c < 3; c += 1) {
          const shade = under * ((full[i + c] + tiny) / (bare[i + c] + tiny)) + (1 - under);
          out[i + c] = on * full[i + c] + (1 - on) * sky[i + c] * shade;
        }
        out[i + 3] = 1;
      }
    }
    return out;
  }

  /** How much of each pixel the mesh, or the floor, covers: 0..1, top row
   *  first, drawn white on black through the stage's own renderer. */
  coverage(camera, width, height, model, floor) {
    const scene = this.scene;
    const kept = { background: scene.background, blur: scene.backgroundBlurriness, ground: this.ground.visible,
                   wire: this.wire?.visible, picture: this.picture?.visible, model: this.model.visible,
                   grid: this.grid.visible };
    try {
      scene.background = new THREE.Color(0x000000);
      scene.backgroundBlurriness = 0;
      scene.overrideMaterial = this.passMaterial("mask", camera);
      this.ground.visible = false;
      this.grid.visible = false;
      if (this.wire) this.wire.visible = false;
      this.showPicture(false);
      this.model.visible = model;
      if (floor) scene.add(floor);
      const drawn = this.snap(camera, width, height).getContext("2d").getImageData(0, 0, width, height).data;
      const covered = new Float32Array(width * height);
      for (let i = 0; i < covered.length; i += 1) covered[i] = drawn[i * 4] / 255;
      return covered;
    } finally {
      if (floor) scene.remove(floor);
      scene.overrideMaterial = null;
      scene.background = kept.background;
      scene.backgroundBlurriness = kept.blur;
      this.ground.visible = kept.ground;
      this.grid.visible = kept.grid;
      if (this.wire) this.wire.visible = kept.wire;
      this.showPicture(kept.picture);
      this.model.visible = kept.model;
    }
  }

  /** Linear light, bottom row first -> a PNG Blob, through the stage's own
   *  curve: three's PBR Neutral tone mapping, then sRGB. */
  developed(linear, width, height) {
    const exposure = this.renderer.toneMappingExposure;
    const start = 0.8 - 0.04;
    const desaturate = 0.15;
    const encode = (v) => {
      const c = Math.min(1, Math.max(0, v));
      return Math.round(255 * (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055));
    };
    const out = document.createElement("canvas");
    out.width = width;
    out.height = height;
    const context = out.getContext("2d");
    const image = context.createImageData(width, height);
    const rgb = [0, 0, 0];
    for (let y = 0; y < height; y += 1) {
      const from = (height - 1 - y) * width;
      for (let x = 0; x < width; x += 1) {
        const i = (from + x) * 4;
        for (let c = 0; c < 3; c += 1) rgb[c] = linear[i + c] * exposure;
        const low = Math.min(rgb[0], rgb[1], rgb[2]);
        const offset = low < 0.08 ? low - 6.25 * low * low : 0.04;
        for (let c = 0; c < 3; c += 1) rgb[c] -= offset;
        const peak = Math.max(rgb[0], rgb[1], rgb[2]);
        if (peak >= start) {
          const d = 1 - start;
          const top = 1 - (d * d) / (peak + d - start);
          const g = 1 - 1 / (desaturate * (peak - top) + 1);
          for (let c = 0; c < 3; c += 1) rgb[c] = rgb[c] * (top / peak) * (1 - g) + top * g;
        }
        const o = (y * width + x) * 4;
        image.data[o] = encode(rgb[0]);
        image.data[o + 1] = encode(rgb[1]);
        image.data[o + 2] = encode(rgb[2]);
        image.data[o + 3] = 255;
      }
    }
    context.putImageData(image, 0, 0);
    return new Promise((done) => out.toBlob(done, "image/png"));
  }

  /** The material a pass is drawn with, fitted to where `camera` stands. */
  passMaterial(pass, camera) {
    this.passMaterials ??= {
      mask: new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }),
      depth: new THREE.ShaderMaterial({
        uniforms: { near: { value: 0 }, far: { value: 1 } },
        vertexShader: `varying float vDepth;
          void main() {
            vec4 view = modelViewMatrix * vec4(position, 1.0);
            vDepth = -view.z;
            gl_Position = projectionMatrix * view;
          }`,
        // The blockout bench's curve, so a depth map from either reads alike.
        fragmentShader: `uniform float near; uniform float far; varying float vDepth;
          void main() {
            float v = pow(clamp(1.0 - (vDepth - near) / (far - near), 0.0, 1.0), 1.3);
            gl_FragColor = vec4(vec3((8.0 + v * 247.0) / 255.0), 1.0);
          }`,
      }),
      normals: new THREE.ShaderMaterial({
        vertexShader: `varying vec3 vNormal; varying vec3 vView;
          void main() {
            vec4 view = modelViewMatrix * vec4(position, 1.0);
            vView = view.xyz;
            vNormal = normalMatrix * normal;
            gl_Position = projectionMatrix * view;
          }`,
        fragmentShader: `varying vec3 vNormal; varying vec3 vView;
          void main() {
            #ifdef FLAT
              vec3 n = normalize(cross(dFdx(vView), dFdy(vView)));
            #else
              vec3 n = normalize(vNormal) * (gl_FrontFacing ? 1.0 : -1.0);
            #endif
            gl_FragColor = vec4(n * 0.5 + 0.5, 1.0);
          }`,
      }),
    };
    const material = this.passMaterials[pass];
    if (pass === "depth") {
      // Near and far are the mesh's bounding sphere seen from the camera, so the
      // whole grey scale is spent on the mesh rather than on the room around it.
      const sphere = new THREE.Box3().setFromObject(this.model).getBoundingSphere(new THREE.Sphere());
      const forward = camera.getWorldDirection(new THREE.Vector3());
      const along = sphere.center.clone().sub(camera.position).dot(forward);
      material.uniforms.near.value = Math.max(camera.near, along - sphere.radius);
      material.uniforms.far.value = along + sphere.radius;
    }
    if (pass === "normals") {
      const flat = this.shading === "flat";
      if (!!material.defines.FLAT !== flat) {
        if (flat) material.defines.FLAT = ""; else delete material.defines.FLAT;
        material.needsUpdate = true;
      }
    }
    return material;
  }

  /**
   * One orbit through the frame, as the stage is lit and staged now. -> Blobs.
   *
   * The orbit is the one the stage's own controls make: around the point they
   * turn about, at the camera's distance, height and lens, starting from the
   * view on the stage — so the first frame of the clip is the frame on screen.
   */
  async turntable({ frames = 96, long = 1024, onFrame } = {}) {
    if (!this.model) throw new Error("there is no mesh on the stage");
    const { width, height } = this.shotSize(long);
    const target = this.controls.target.clone();
    const offset = this.camera.position.clone().sub(target);
    const up = new THREE.Vector3(0, 1, 0);
    const orbit = this.camera.clone();
    return this.staged(async () => {
      const blobs = [];
      for (let index = 0; index < frames; index += 1) {
        const angle = (index / frames) * Math.PI * 2;
        orbit.position.copy(target).add(offset.clone().applyAxisAngle(up, angle));
        orbit.lookAt(target);
        const canvas = this.snap(this.shotCamera(orbit), width, height);
        blobs.push(await new Promise((done) => canvas.toBlob(done, "image/png")));
        onFrame?.(index + 1, frames);
      }
      return blobs;
    });
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.observer.disconnect();
    this.controls.dispose();
    this.clearPicture();
    for (const pending of this.lights.values()) {
      pending.then(({ environment, background }) => {
        environment.dispose();
        background.dispose();
      }, () => {});
    }
    this.pmrem.dispose();
    this.pmrem = null;
    this.shadowTarget.dispose();
    this.shadowBlurTarget.dispose();
    this.renderer.dispose();
    this.canvas.remove();
  }
}
