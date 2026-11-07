import * as THREE from 'three';
import './style.css';

const hostElement = document.querySelector<HTMLDivElement>('#scene');
if (!hostElement) throw new Error('Missing scene container');
const host: HTMLDivElement = hostElement;

const scene = new THREE.Scene();
scene.background = new THREE.Color('#101d2b');
scene.fog = new THREE.Fog('#101d2b', 32, 75);

const camera = new THREE.OrthographicCamera(-10, 10, 6, -6, 0.1, 120);
const focus = new THREE.Vector3(0, 4, 4);
camera.position.set(25, 19, 32);
camera.lookAt(focus);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
host.appendChild(renderer.domElement);

const ambient = new THREE.AmbientLight('#94b6d7', 1.35);
const moon = new THREE.DirectionalLight('#c3d8fa', 2.1);
moon.position.set(-7, 14, 12);
scene.add(ambient, moon);

const rockMat = new THREE.MeshStandardMaterial({ color: '#26313c', roughness: 1, flatShading: true });
const darkRockMat = new THREE.MeshStandardMaterial({ color: '#17212b', roughness: 1, flatShading: true });
const timberMat = new THREE.MeshStandardMaterial({ color: '#4b3324', roughness: 1 });
const yardMat = new THREE.MeshStandardMaterial({ color: '#3b3b34', roughness: 1 });
const grilleMat = new THREE.MeshStandardMaterial({ color: '#1d2225', metalness: 0.7, roughness: 0.65 });
const wolfMat = new THREE.MeshStandardMaterial({ color: '#65757b', roughness: 1, flatShading: true });
const wolfDarkMat = new THREE.MeshStandardMaterial({ color: '#303a3f', roughness: 1, flatShading: true });
const wolfEyeMat = new THREE.MeshBasicMaterial({ color: '#ffb65b' });
const glowMats: THREE.MeshStandardMaterial[] = [];
const warmLights: THREE.PointLight[] = [];

function box(parent: THREE.Object3D, w: number, h: number, d: number, x: number, y: number, z: number, material: THREE.Material) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  mesh.position.set(x, y, z);
  parent.add(mesh);
  return mesh;
}

function stone(parent: THREE.Object3D, x: number, y: number, z: number, sx: number, sy: number, sz: number, dark = false) {
  const mesh = new THREE.Mesh(new THREE.DodecahedronGeometry(1, 0), dark ? darkRockMat : rockMat);
  mesh.position.set(x, y, z);
  mesh.scale.set(sx, sy, sz);
  mesh.rotation.set(0.15 * x, 0.08 * y, 0.07 * x);
  parent.add(mesh);
}

// The prototype separates the back rock, accessible rooms and removable face.
const cliff = new THREE.Group();
scene.add(cliff);
box(cliff, 32, 20, 4.5, 0, 7.4, -2, darkRockMat);
const rockRowHeight = 3.6;
for (let i = 0; i < 84; i++) {
  const x = -15.7 + (i % 14) * 2.4 + (Math.floor(i / 14) % 2) * 0.5;
  const y = -1.5 + Math.floor(i / 14) * rockRowHeight;
  stone(cliff, x, y, -0.25 + (i % 3) * 0.35, 1.5 + (i % 4) * 0.22, 2.1 + (i % 3) * 0.3, 1.2);
}

const rooms = new THREE.Group();
scene.add(rooms);
const roomPositions = [
  { x: 0, y: 10 - 2 * rockRowHeight, label: 'Utkik' },
];
for (const room of roomPositions) {
  const group = new THREE.Group();
  group.position.set(room.x, room.y, 1.65);
  group.scale.setScalar(0.55);
  group.name = room.label;
  rooms.add(group);
  box(group, 3.25, 2.15, 0.25, 0, 0, -0.6, darkRockMat);
  box(group, 3.35, 0.2, 1.4, 0, -1.12, 0.08, rockMat);
  box(group, 0.14, 2.25, 1.3, -1.68, 0, 0, timberMat);
  box(group, 0.14, 2.25, 1.3, 1.68, 0, 0, timberMat);
  box(group, 3.45, 0.14, 1.3, 0, 1.14, 0, timberMat);
  const glow = new THREE.MeshStandardMaterial({ color: '#b36628', emissive: '#ed7d22', emissiveIntensity: 1.8, side: THREE.DoubleSide });
  glowMats.push(glow);
  box(group, 2.9, 1.8, 0.05, 0, 0, -0.45, glow);
  for (const x of [-0.9, 0, 0.9]) box(group, 0.07, 1.95, 0.1, x, 0, 0.5, grilleMat);
  for (const y of [-0.55, 0.55]) box(group, 3.05, 0.07, 0.1, 0, y, 0.5, grilleMat);
  const lamp = new THREE.PointLight('#f7a858', 5.5, 6, 2);
  lamp.position.set(0, 0.3, 0.7);
  warmLights.push(lamp);
  group.add(lamp);
}

const frontCover = new THREE.Group();
scene.add(frontCover);
for (const room of roomPositions) {
  stone(frontCover, room.x, room.y, 1.55, 1.25, 1.1, 1, true);
}
frontCover.visible = false;

// A timber fence marks the outer defence line on the ground in front of the cliff.
const outerDefence = new THREE.Group();
scene.add(outerDefence);
const groundY = -2.6;
box(outerDefence, 10.8, 0.12, 5.8, 0, groundY - 0.07, 6.5, yardMat);
function fenceRun(fromX: number, fromZ: number, toX: number, toZ: number) {
  const length = Math.hypot(toX - fromX, toZ - fromZ);
  const steps = Math.ceil(length / 0.75);
  const direction = new THREE.Vector3(toX - fromX, 0, toZ - fromZ).normalize();
  for (let i = 0; i <= steps; i++) {
    const x = fromX + (toX - fromX) * i / steps;
    const z = fromZ + (toZ - fromZ) * i / steps;
    const postHeight = i % 4 === 0 ? 1.55 : 1.25;
    box(outerDefence, 0.16, postHeight, 0.16, x, groundY + postHeight / 2, z, timberMat);
  }
  for (const railHeight of [0.45, 0.95]) {
    const rail = box(outerDefence, 0.12, 0.1, length, (fromX + toX) / 2, groundY + railHeight, (fromZ + toZ) / 2, timberMat);
    rail.rotation.y = Math.atan2(direction.x, direction.z);
  }
}
fenceRun(-5.5, 3.5, 5.5, 3.5);
fenceRun(-5.5, 3.5, -5.5, 9.5);
fenceRun(5.5, 3.5, 5.5, 9.5);
fenceRun(-5.5, 9.5, -1.4, 9.5);
fenceRun(1.4, 9.5, 5.5, 9.5);
// A gate makes the enclosed area read as a usable defensive position.
box(outerDefence, 2.6, 1.25, 0.13, 0, groundY + 0.65, 9.5, timberMat);
for (const x of [-1.4, 1.4]) box(outerDefence, 0.24, 1.8, 0.24, x, groundY + 0.9, 9.5, darkRockMat);
const fenceLight = new THREE.PointLight('#a8c7dc', 8, 12, 1.6);
fenceLight.position.set(0, 0.4, 10.7);
scene.add(fenceLight);

type Wolf = {
  root: THREE.Group;
  legs: THREE.Group[];
  head: THREE.Group;
  tail: THREE.Group;
  start: THREE.Vector3;
  target: THREE.Vector3;
  delay: number;
  speed: number;
};

// The werewolves run over the ground toward the fence, then paw at it.
const wolves: Wolf[] = [];
function createWolf(index: number) {
  const root = new THREE.Group();
  const body = new THREE.Mesh(new THREE.IcosahedronGeometry(0.65, 0), wolfMat);
  body.scale.set(0.65, 1.05, 0.6);
  body.position.set(0, 0.98, 0.1);
  body.rotation.x = -0.18;
  root.add(body);

  const shoulders = new THREE.Mesh(new THREE.IcosahedronGeometry(0.42, 0), wolfDarkMat);
  shoulders.scale.set(1.45, 0.75, 0.8);
  shoulders.position.set(0, 1.39, -0.06);
  root.add(shoulders);

  const head = new THREE.Group();
  head.position.set(0, 1.67, -0.32);
  root.add(head);
  const skull = new THREE.Mesh(new THREE.IcosahedronGeometry(0.36, 0), wolfMat);
  skull.scale.set(0.85, 0.82, 1.1);
  head.add(skull);
  const muzzle = new THREE.Mesh(new THREE.ConeGeometry(0.17, 0.46, 5), wolfDarkMat);
  muzzle.rotation.x = -Math.PI / 2;
  muzzle.position.set(0, -0.14, -0.46);
  head.add(muzzle);
  for (const side of [-1, 1]) {
    const ear = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.35, 4), wolfDarkMat);
    ear.position.set(side * 0.23, 0.33, -0.11);
    head.add(ear);
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.055, 6, 4), wolfEyeMat);
    eye.position.set(side * 0.23, 0.07, -0.29);
    head.add(eye);
  }

  const legs: THREE.Group[] = [];
  for (const x of [-0.27, 0.27]) {
    const leg = new THREE.Group();
    leg.position.set(x, 0.68, 0.18);
    box(leg, 0.23, 0.67, 0.27, 0, -0.34, 0, wolfDarkMat);
    box(leg, 0.28, 0.12, 0.38, 0, -0.67, -0.08, wolfDarkMat);
    root.add(leg);
    legs.push(leg);
  }
  for (const x of [-0.47, 0.47]) {
    const arm = new THREE.Group();
    arm.position.set(x, 1.35, -0.13);
    box(arm, 0.2, 0.78, 0.22, 0, -0.39, 0, wolfDarkMat);
    const claw = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.28, 4), wolfDarkMat);
    claw.rotation.x = Math.PI;
    claw.position.set(0, -0.85, -0.03);
    arm.add(claw);
    root.add(arm);
    legs.push(arm);
  }

  const tail = new THREE.Group();
  tail.position.set(0, 0.78, 0.42);
  const tailFur = new THREE.Mesh(new THREE.ConeGeometry(0.2, 0.65, 5), wolfDarkMat);
  tailFur.rotation.x = Math.PI / 2.7;
  tailFur.position.z = 0.3;
  tail.add(tailFur);
  root.add(tail);

  root.scale.setScalar(0.95 + (index % 3) * 0.04);
  const targetX = [-4.3, -2.8, -1.3, 1.3, 2.8, 4.3][index];
  const start = new THREE.Vector3(targetX + (index % 2 ? 1.2 : -1.2), groundY, 16 + (index % 3) * 1.2);
  const target = new THREE.Vector3(targetX, groundY, 10.8);
  root.position.copy(start);
  root.rotation.y = -Math.atan2(target.x - start.x, start.z - target.z);
  root.visible = false;
  scene.add(root);
  wolves.push({ root, legs, head, tail, start, target, delay: index * 0.55, speed: 1.4 + (index % 3) * 0.16 });
}
for (let i = 0; i < 6; i++) createWolf(i);

const forest = new THREE.Group();
scene.add(forest);
function scatter(seed: number) {
  const value = Math.sin(seed * 127.1) * 43758.5453;
  return value - Math.floor(value);
}
for (let i = 0; i < 150; i++) {
  const x = -22 + scatter(i + 1) * 44;
  const z = 10.5 + scatter(i + 181) * 14;
  if (Math.abs(x) < 8 && z < 19) continue;
  const height = 1.15 + scatter(i + 371) * 1.65;
  box(forest, 0.12, height, 0.12, x, -2.6 + height / 2, z, timberMat);
  const crown = new THREE.Mesh(new THREE.ConeGeometry(0.5 + (i % 3) * 0.12, height * 1.4, 6), darkRockMat);
  crown.position.set(x, -2.6 + height * 1.1, z);
  forest.add(crown);
}

let night = false;
let cutaway = true;
let lightsOn = true;
let elapsed = 0;
const status = document.querySelector<HTMLElement>('#status')!;
const phaseButton = document.querySelector<HTMLButtonElement>('#phase-button')!;
const cutawayButton = document.querySelector<HTMLButtonElement>('#cutaway-button')!;
const lightButton = document.querySelector<HTMLButtonElement>('#light-button')!;

function refresh() {
  scene.background = new THREE.Color(night ? '#07101a' : '#26384a');
  scene.fog = new THREE.Fog(night ? '#07101a' : '#26384a', 32, 75);
  ambient.intensity = night ? 0.78 : 1.35;
  moon.intensity = night ? 1.25 : 2.1;
  frontCover.visible = !cutaway;
  rooms.visible = cutaway;
  for (const light of warmLights) light.intensity = lightsOn ? (night ? 5.5 : 3.5) : 0;
  for (const material of glowMats) material.emissiveIntensity = lightsOn ? (night ? 1.8 : 0.9) : 0;
  status.textContent = night ? 'Natt — varulvarna rusar mot stängslet' : 'Dag — förbered försvaret';
  phaseButton.textContent = night ? 'Avsluta natt' : 'Starta natt';
  cutawayButton.textContent = cutaway ? 'Dölj fönstret' : 'Visa fönstret';
  cutawayButton.setAttribute('aria-pressed', String(cutaway));
  lightButton.textContent = lightsOn ? 'Släck ljus' : 'Tänd ljus';
  lightButton.setAttribute('aria-pressed', String(lightsOn));
}
phaseButton.addEventListener('click', () => { night = !night; elapsed = 0; refresh(); });
cutawayButton.addEventListener('click', () => { cutaway = !cutaway; refresh(); });
lightButton.addEventListener('click', () => { lightsOn = !lightsOn; refresh(); });
refresh();

let zoom = 19.5;
function resize() {
  const width = host.clientWidth;
  const height = host.clientHeight;
  camera.left = -zoom * width / height;
  camera.right = zoom * width / height;
  camera.top = zoom;
  camera.bottom = -zoom;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}
window.addEventListener('resize', resize);
host.addEventListener('wheel', event => {
  event.preventDefault();
  zoom = THREE.MathUtils.clamp(zoom * (event.deltaY > 0 ? 1.1 : 0.9), 7, 32);
  resize();
}, { passive: false });
let dragging = false;
let lastX = 0;
let lastY = 0;
host.addEventListener('pointerdown', event => { dragging = true; lastX = event.clientX; lastY = event.clientY; host.setPointerCapture(event.pointerId); });
host.addEventListener('pointerup', () => { dragging = false; });
host.addEventListener('pointermove', event => {
  if (!dragging) return;
  const dx = (event.clientX - lastX) * 0.012;
  const dy = (event.clientY - lastY) * 0.012;
  focus.x -= dx;
  focus.y += dy;
  camera.position.x -= dx;
  camera.position.y += dy;
  camera.lookAt(focus);
  lastX = event.clientX;
  lastY = event.clientY;
});
resize();

const clock = new THREE.Clock();
function frame() {
  requestAnimationFrame(frame);
  const delta = Math.min(clock.getDelta(), 0.05);
  if (night) elapsed += delta;
  wolves.forEach((wolf, i) => {
    const runningTime = elapsed - wolf.delay;
    wolf.root.visible = night && runningTime >= 0;
    if (!wolf.root.visible) return;
    const distance = wolf.start.distanceTo(wolf.target);
    const progress = THREE.MathUtils.clamp(runningTime * wolf.speed / distance, 0, 1);
    wolf.root.position.copy(wolf.start).lerp(wolf.target, progress);
    const stride = runningTime * 12 + i;
    const legSwing = progress < 1 ? 0.48 : 0.12;
    wolf.legs.forEach((leg, legIndex) => {
      leg.rotation.x = Math.sin(stride + (legIndex === 0 || legIndex === 3 ? 0 : Math.PI)) * legSwing;
    });
    wolf.root.position.y = groundY + Math.abs(Math.sin(stride)) * (progress < 1 ? 0.045 : 0.015);
    wolf.head.rotation.x = Math.sin(stride * 0.5) * (progress < 1 ? 0.05 : 0.13);
    wolf.tail.rotation.y = Math.sin(stride * 0.38) * 0.35;
  });
  renderer.render(scene, camera);
}
frame();
