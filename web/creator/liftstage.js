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
// Everything three.js is vendored (`vendor/three`, `tools/vendor_three.py`);
// this module is the only one that imports it, so the rest of the pack never
// pays for 800 KB of WebGL it is not using.

import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/OrbitControls.js";
import { GLTFLoader } from "./vendor/three/GLTFLoader.js";
import { RoomEnvironment } from "./vendor/three/RoomEnvironment.js";

const AMBER = 0xf0a63c;

// Where the picture stands along its own frustum, as a fraction of the camera's
// distance to the origin: most of the way from the lens to the subject, so the
// rays from it read as reaching *into* the object rather than as a card held at
// the camera. Past it they run on to this much beyond the origin.
const PLANE_AT = 0.42;
const RAYS_TO = 1.45;

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
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer = renderer;

    const scene = new THREE.Scene();
    this.scene = scene;
    this.paintGround();
    const pmrem = new THREE.PMREMGenerator(renderer);
    this.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();
    scene.environment = this.environment;

    scene.add(new THREE.HemisphereLight(0xfff4e6, 0x30343c, 0.35));
    const key = new THREE.DirectionalLight(0xfff1dc, 1.6);
    key.position.set(1.6, 3, 2.2);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -1, right: 1, top: 1, bottom: -1, near: 0.2, far: 8 });
    scene.add(key);
    this.key = key;

    this.floor = new THREE.Mesh(new THREE.PlaneGeometry(12, 12), new THREE.ShadowMaterial({ opacity: 0.4 }));
    this.floor.rotation.x = -Math.PI / 2;
    this.floor.receiveShadow = true;
    scene.add(this.floor);
    this.grid = new THREE.GridHelper(6, 24, 0x3a3f48, 0x262a31);
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.7;
    scene.add(this.grid);

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
    this.pictureCamera = null;       // {position, fov} or null
    this.picture = null;
    this.rays = null;
    this.flight = null;

    this.resize();
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(host);
    this.frame = requestAnimationFrame((now) => this.tick(now));
  }

  /** The stage's ground follows the pack's surface, whatever palette is up. */
  paintGround() {
    const ground = getComputedStyle(this.host).getPropertyValue("--mmc-media-bg").trim() || "#0f1115";
    try { this.scene.background = new THREE.Color(ground); }
    catch { this.scene.background = new THREE.Color(0x0f1115); }
  }

  resize() {
    const { width, height } = this.host.getBoundingClientRect();
    if (!width || !height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  tick(now) {
    this.frame = requestAnimationFrame((next) => this.tick(next));
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
            part.castShadow = true;
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
    if (!root) return;
    this.scene.add(root);
    this.settleFloor(root);
    this.applyMode();
  }

  /** The grid and the shadow catcher go where the mesh stands. */
  settleFloor(root) {
    const box = new THREE.Box3().setFromObject(root);
    if (box.isEmpty()) return;
    const y = box.min.y - 0.002;
    this.floor.position.y = y;
    this.grid.position.y = y;
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
    this.dropWire();
    root.traverse((part) => {
      if (!part.isMesh) return;
      part.material = mode === "clay" ? this.clay
        : mode === "wire" ? this.dark
          : mode === "normals" ? this.normals
            : part.userData.own;
    });
    if (mode === "wire") {
      // A wireframe material over the same geometry rather than
      // WireframeGeometry: a 200k-face mesh as explicit line segments is a
      // second copy of every edge in memory, and this draws the same lines.
      this.wire = root.clone();
      this.wire.traverse((part) => {
        if (!part.isMesh) return;
        part.castShadow = false;
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

  // ---- a turntable ------------------------------------------------------------

  /**
   * Render one orbit of the mesh, frame by frame, at a fixed size. -> Blobs.
   *
   * Its own camera and its own renderer size, so what is written does not
   * depend on how big the tool's window happened to be; the scene is the one on
   * the stage, as it is drawn now, minus the picture and its rays.
   */
  async turntable({ frames = 96, width = 1024, height = 576, onFrame } = {}) {
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.setSize(width, height, false);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    const camera = new THREE.PerspectiveCamera(30, width / height, 0.01, 60);
    const box = new THREE.Box3().setFromObject(this.model);
    const centre = box.getCenter(new THREE.Vector3());
    const radius = box.getSize(new THREE.Vector3()).length() / 2;
    const distance = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.05;
    const pictureWas = this.picture?.visible;
    this.showPicture(false);
    const blobs = [];
    try {
      for (let index = 0; index < frames; index += 1) {
        const angle = (index / frames) * Math.PI * 2;
        camera.position.set(centre.x + Math.sin(angle) * distance, centre.y + distance * 0.22,
                            centre.z + Math.cos(angle) * distance);
        camera.lookAt(centre);
        renderer.render(this.scene, camera);
        blobs.push(await new Promise((done) => renderer.domElement.toBlob(done, "image/png")));
        onFrame?.(index + 1, frames);
      }
    } finally {
      this.showPicture(pictureWas);
      renderer.dispose();
    }
    return blobs;
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    this.controls.dispose();
    this.clearPicture();
    this.environment.dispose();
    this.renderer.dispose();
    this.canvas.remove();
  }
}
