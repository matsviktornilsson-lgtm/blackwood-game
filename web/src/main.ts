import * as THREE from 'three';
import { clawScrape, dryFireSound, enableAudio, hitSound, howl, playerHitSound, playReloadSounds, setMusicPlaying, shotSound, tripwireBellSound, wolfGrowl, wolfRoar } from './audio';
import { createRifleModel } from './rifle-model';
import { reloadDuration } from './rifle-reload';
import { buildLookout, cliffEntry, floorY, forestApproach, groundHeight, lookoutPosition } from './lookout';
import { createLedgeBarricade } from './ledge-barricade';
import { createTripwireBell } from './tripwire-bell';
import { applyValleyFog } from './valley-fog';
import { animateWolf, animateWolfFall, createWolf, resetWolfAnimation, strikeMoment, type WolfMotion } from './wolf';
import { planClimb, type ClimbPose } from './wolf-climb';
import { createLedgeAppearance, ledgeModelReady } from './wolf-ledge-model';
import './style.css';

const host = document.querySelector<HTMLDivElement>('#scene')!;
const app = document.querySelector<HTMLElement>('#app')!;
const intro = document.querySelector<HTMLElement>('#briefing')!;
const heading = document.querySelector<HTMLElement>('#briefing-title')!;
const briefing = document.querySelector<HTMLElement>('#briefing-copy')!;
const startButton = document.querySelector<HTMLButtonElement>('#start')!;
const scopeButton = document.querySelector<HTMLButtonElement>('#aim')!;
const reloadButton = document.querySelector<HTMLButtonElement>('#reload')!;
const musicButton = document.querySelector<HTMLButtonElement>('#music-toggle')!;
const status = document.querySelector<HTMLElement>('#status')!;
const ammunition = document.querySelector<HTMLElement>('#ammo')!;
const healthReadout = document.querySelector<HTMLElement>('#health')!;
const survivedReadout = document.querySelector<HTMLElement>('#watches-survived')!;
const killsReadout = document.querySelector<HTMLElement>('#total-kills')!;
const bestReadout = document.querySelector<HTMLElement>('#best-score')!;
const nightClock = document.querySelector<HTMLElement>('#night-clock')!;
const clockLabel = document.querySelector<HTMLElement>('#clock-label')!;
const walletReadout = document.querySelector<HTMLElement>('#wallet')!;
const cue = document.querySelector<HTMLElement>('#cue')!;
const nextNightButton = document.querySelector<HTMLButtonElement>('#next-night')!;
const buildPanel = document.querySelector<HTMLElement>('#build-panel')!;
const buildMessage = document.querySelector<HTMLElement>('#build-message')!;
const watchSummary = document.querySelector<HTMLDialogElement>('#watch-summary')!;
const summaryTitle = document.querySelector<HTMLElement>('#summary-title')!;
const summaryKills = document.querySelector<HTMLElement>('#summary-kills')!;
const summaryCoins = document.querySelector<HTMLElement>('#summary-coins')!;
const ammoButton = document.querySelector<HTMLButtonElement>('#buy-ammo')!;
const boltButton = document.querySelector<HTMLButtonElement>('#buy-bolt')!;
const healthButton = document.querySelector<HTMLButtonElement>('#buy-health')!;
const barricadeLanes = document.querySelector<HTMLElement>('#barricade-lanes')!;
const tripwireLanes = document.querySelector<HTMLElement>('#tripwire-lanes')!;
const ledgePreview = new URLSearchParams(window.location.search).get('preview') === 'ledge-wolf';

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(59, 1, 0.06, 620);
camera.position.copy(lookoutPosition);
camera.rotation.order = 'YXZ';
scene.add(camera);
const { blockers, cliff, sill, trees, glow, room, mistTime, moon } = buildLookout(scene);

let renderer: THREE.WebGLRenderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
} catch {
  heading.textContent = 'Could not start 3D graphics';
  briefing.textContent = 'Enable hardware acceleration or try a different browser.';
  startButton.disabled = true;
  nextNightButton.disabled = true;
  throw new Error('WebGL could not be initialized');
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.65));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.13;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
host.appendChild(renderer.domElement);

const { model: rifle, poseReload } = createRifleModel();
camera.add(rifle);

const forestEntrySpeed = 2.05;
const forestRushSpeed = 4.35;
const entryPaceTime = 2.25;
const accelerationTime = 4.8;
const cliffBrakingTime = 0.44;
const accelerationLoss = (forestRushSpeed - forestEntrySpeed) * (entryPaceTime + accelerationTime * 0.5);
const brakingLoss = forestRushSpeed * cliffBrakingTime * 0.25;
const entries = [
  [[-8.1, -2.47], [-7.5, -2.02]],
  [[-0.65, -0.29], [0.65, 0.29]],
  [[7.5, 2.02], [8.1, 2.47]],
].map(lane => lane.map(([footX, lipX]) => {
  const entry = cliffEntry(footX, lipX);
  return { ...entry, holds: planClimb(entry.climb, cliff, sill), climbTime: entry.climb.getLength() / 2.1 };
}));
const laneNames = ['Left', 'Center', 'Right'];
const lanePositions = [-2.24, 0, 2.24];
const barricades = lanePositions.map((x, lane) => createLedgeBarricade(room.group, x, laneNames[lane]));
const tripwires = lanePositions.map((x, lane) => createTripwireBell(room.group, x, laneNames[lane]));
type Assault = {
  lane: number;
  entry: typeof entries[number][number];
  connector: THREE.CubicBezierCurve3;
  climbAt: number;
  climbTime: number;
  startedAt: number;
  pose: ClimbPose;
};
const lastEntry = entries.map(() => -1);
let lastLane = -1;
const sectors = ['left', 'center', 'right'] as const;
type ForestSector = typeof sectors[number];
const routes = ([
  { side: 0, path: [[-33, -57], [-25, -50], [-29, -45], [-23, -34], [-17, -27], [-13, -21]] },
  { side: 1, path: [[37, -58], [31, -53], [30, -48], [25, -39], [21, -31], [15, -23]] },
  { side: 0, path: [[-37, -62], [-33, -53], [-29, -45], [-20, -37], [-20, -29], [-15, -23]] },
  { side: 1, path: [[41, -65], [36, -59], [30, -54], [31, -46], [28, -38], [18, -30], [16, -23]] },
  { side: 0, path: [[-31, -70], [-38, -59], [-32, -50], [-33, -41], [-28, -33], [-25.5, -29.8], [-24.7, -27.8], [-18, -24]] },
  { side: 1, path: [[40, -60], [37, -56], [25, -50], [28, -43], [25, -33], [16, -24]] },
  { side: 0, path: [[-32, -56], [-25, -51], [-27, -46], [-26, -40], [-19, -34], [-18, -25], [-14.5, -21]] },
  { side: 1, path: [[44, -69], [36, -63], [29, -55], [33.8, -53], [36, -49], [36, -47], [30, -40], [23, -33], [18, -25]] },
  { side: 0, path: [[-10, -72], [-7, -68], [-10, -64], [-6, -60], [-3, -56], [-13, -45], [-14, -32], [-12, -23]] },
  { side: 1, path: [[12, -73], [10, -69], [5, -66], [5, -62], [4, -60], [5.5, -57.8], [10.3, -55.6], [14, -48], [15, -39], [13, -29], [12, -22]] },
  { side: 0, path: [[-2, -71], [0, -64], [-5, -60], [-1, -56], [-6, -49], [-11, -39], [-15, -28], [-12, -21]] },
  { side: 1, path: [[0, -69], [4, -65], [1, -61], [5, -57], [10, -52], [17, -44], [15, -32], [12, -23]] },
  { side: 0, path: [[10, -67], [7, -63], [2, -58], [-2, -54], [-10, -49], [-16, -40], [-16, -29], [-12, -22]] },
  { side: 1, path: [[-13, -68], [-12, -64], [-10, -62], [-3, -59], [2, -55], [10, -49], [15, -38], [14, -26]] },
  { side: 0, path: [[11, -76], [10.7, -72.3], [4, -70.1], [8, -66], [1, -61], [-8, -53], [-16, -42], [-15, -29], [-13, -22]] },
  { side: 1, path: [[-2, -78], [4, -73], [6, -66], [3, -62], [7, -57], [12, -49], [11.5, -47.5], [17, -39], [13, -26]] },
] as const).map(({ side, path }) => {
  const sector: ForestSector = path[0][0] < -18 ? 'left' : path[0][0] > 18 ? 'right' : 'center';
  return { side, path, sector };
});

type Approach = typeof routes[number];
const sectorBag: ForestSector[] = [];
const routeBags: Record<ForestSector, Approach[]> = { left: [], center: [], right: [] };
const sectorRoutes = {
  left: routes.filter(route => route.sector === 'left'),
  center: routes.filter(route => route.sector === 'center'),
  right: routes.filter(route => route.sector === 'right'),
};
let previousSector: ForestSector | undefined;
const previousRoutes: Partial<Record<ForestSector, Approach>> = {};

function drawFromBag<T>(bag: T[], choices: readonly T[], previous?: T) {
  if (!bag.length) bag.push(...choices);
  const eligible = bag.length > 1 ? bag.filter(choice => choice !== previous) : bag;
  const choice = eligible[Math.floor(Math.random() * eligible.length)];
  bag.splice(bag.indexOf(choice), 1);
  return choice;
}

function nextApproach() {
  const sector = drawFromBag(sectorBag, sectors, previousSector);
  const route = drawFromBag(routeBags[sector], sectorRoutes[sector], previousRoutes[sector]);
  previousSector = sector;
  previousRoutes[sector] = route;
  return route;
}

function addWolfToScene() {
  const wolf = createWolf();
  wolf.root.visible = false;
  wolf.root.traverse(part => {
    if (!(part instanceof THREE.Mesh)) return;
    const materials = Array.isArray(part.material) ? part.material : [part.material];
    materials.forEach(material => applyValleyFog(material, mistTime));
    if (!part.visible) return;
    part.castShadow = true;
    part.receiveShadow = true;
  });
  scene.add(wolf.root);
  return { ...wolf, showLedgeAppearance: createLedgeAppearance(wolf) };
}

type WolfKind = 'regular' | 'stalker' | 'climber';

function beginApproach(model: ReturnType<typeof addWolfToScene>, route: Approach, bornAt: number, kind: WolfKind) {
  const [x, z] = route.path[0];
  const drift = THREE.MathUtils.randFloatSpread(19);
  const direction = route.side === 0 ? -1 : 1;
  const startZ = z - THREE.MathUtils.randFloat(17, 28);
  const stageX = direction * THREE.MathUtils.randFloat(5.0, 8.3);
  const approach = forestApproach([
    [x + drift, startZ],
    [x + drift * 0.67 + THREE.MathUtils.randFloatSpread(6), (startZ + z) * 0.5],
    ...route.path,
    [stageX, -17.3],
  ], trees);
  const distance = approach.getLength();
  const stage = approach.getPointAt(1);
  const heading = approach.getTangentAt(1).setY(0).normalize();
  resetWolfAnimation(model);
  model.showLedgeAppearance(false);
  model.root.rotation.set(0, 0, 0);
  model.root.visible = false;
  return {
    ...model, bornAt, approach, distance, stage, heading, kind,
    approachTime: (distance + accelerationLoss + brakingLoss) / forestRushSpeed,
    assault: null as Assault | null,
    barricadeDelay: 0,
    warns: arrivals === 0,
    appeared: false, climbing: false, growled: false, entered: false,
    lastScrape: -1, strikes: 0, downAt: null as number | null,
  };
}

const wolves: ReturnType<typeof beginApproach>[] = [];
const wolfPool: ReturnType<typeof addWolfToScene>[] = [];
const nightDuration = 60;
const buildDuration = 30;
const startingCoins = 20;
const wolfBounty = 10;
const bodyDuration = 2.1;
const ammoBoxRounds = 3;
const ammoBoxCost = 15;
const boltCost = 30;
const barricadeCost = 20;
const barricadeDelay = 4;
const tripwireCost = 15;
const firstAidCost = 20;
const firstAidHealth = 35;
let arrivals = 0;
let nextArrival = 0;

type Phase = 'ready' | 'night' | 'summary' | 'build' | 'lost';
const chamberCapacity = 1;
const startingAmmo = 10;
const maxHealth = 100;
const clawDamage = 35;
const strikeInterval = 1.85;
const peekDuration = 2.55;
const lungeDuration = 0.62;
const chamberFloor = () => floorY;
let phase: Phase = 'ready';
let paused = false;
let buildRemaining = 0;
let wallet = startingCoins;
let night = 0;
let scoped = false;
let musicEnabled = true;
let rounds = chamberCapacity;
let reserve = startingAmmo - chamberCapacity;
let boltInstalled = false;
let health = maxHealth;
let damageRemaining = 0;
let survived = 0;
let totalKills = 0;
let watchKills = 0;
let elapsed = 0;
let reloadRemaining = 0;
let shotCooldown = 0;
let cueRemaining = 0;
let yaw = 0;
let pitch = -0.17;

const scoreKey = 'blackwood.night-watch.best';
type Score = { watches: number; kills: number };

function loadBest(): Score | null {
  try {
    const score = JSON.parse(localStorage.getItem(scoreKey) ?? 'null');
    if (score && Number.isSafeInteger(score.watches) && score.watches >= 0
      && Number.isSafeInteger(score.kills) && score.kills >= 0) return score;
  } catch {
    // Play still works when storage is unavailable.
  }
  return null;
}

let best = loadBest();

function scoreText(watches: number, kills: number) {
  return watches + (watches === 1 ? ' watch survived' : ' watches survived')
    + ' · ' + kills + (kills === 1 ? ' kill' : ' kills');
}

function recordScore() {
  if (ledgePreview) return;
  if (best && (survived < best.watches || (survived === best.watches && totalKills <= best.kills))) return;
  best = { watches: survived, kills: totalKills };
  try {
    localStorage.setItem(scoreKey, JSON.stringify(best));
  } catch {
    // Keep the score in memory for this session.
  }
}

function reloadTime() {
  return boltInstalled ? reloadDuration * 0.8 : reloadDuration;
}

function setScope(value: boolean) {
  scoped = value;
  app.classList.toggle('scoped', value);
  scopeButton.setAttribute('aria-pressed', String(value));
  scopeButton.textContent = value ? 'Lower scope' : 'Scope';
  camera.fov = value ? 16 : 59;
  camera.updateProjectionMatrix();
  rifle.visible = !value && phase !== 'build';
}

function look(dx: number, dy: number) {
  const sensitivity = scoped ? 0.00085 : 0.0024;
  const nextYaw = yaw - dx * sensitivity;
  yaw = phase === 'build' ? nextYaw : THREE.MathUtils.clamp(nextYaw, -1.08, 1.08);
  pitch = THREE.MathUtils.clamp(pitch - dy * sensitivity, phase === 'build' ? -1.45 : -0.78, phase === 'build' ? 0.8 : 0.48);
  camera.rotation.set(pitch, yaw, 0);
}

function updateClock() {
  const remaining = phase === 'ready' ? buildDuration : phase === 'build' ? buildRemaining : nightDuration - elapsed;
  const seconds = Math.max(0, Math.ceil(remaining));
  const time = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
  if (nightClock.textContent !== time) nightClock.textContent = time;
}

function updateHud() {
  updateClock();
  clockLabel.textContent = phase === 'ready' ? 'Build time' : phase === 'build' ? 'Nightfall in' : 'Dawn in';
  walletReadout.textContent = String(wallet);
  survivedReadout.textContent = String(survived);
  killsReadout.textContent = String(totalKills);
  bestReadout.hidden = best === null;
  if (best) bestReadout.textContent = 'Personal best · ' + scoreText(best.watches, best.kills);
  const outOfAmmo = rounds + reserve === 0;
  ammunition.textContent = outOfAmmo ? 'OUT OF AMMO' : rounds + ' loaded · ' + reserve + ' spare';
  app.classList.toggle('out-of-ammo', outOfAmmo);
  healthReadout.textContent = String(health);
  app.classList.toggle('wounded', health <= clawDamage);
  reloadButton.disabled = phase !== 'night' || reloadRemaining > 0 || rounds === chamberCapacity || reserve === 0;
  scopeButton.disabled = phase !== 'night' || reloadRemaining > 0;
  ammoButton.disabled = phase !== 'build' || wallet < ammoBoxCost;
  boltButton.disabled = phase !== 'build' || boltInstalled || wallet < boltCost;
  boltButton.textContent = boltInstalled ? 'Faster bolt installed' : 'Faster bolt · ' + boltCost + ' coins';
  const recovery = Math.min(firstAidHealth, maxHealth - health);
  healthButton.disabled = phase !== 'build' || recovery === 0 || wallet < firstAidCost;
  healthButton.textContent = recovery > 0 ? 'Restore ' + recovery + ' health · ' + firstAidCost + ' coins' : 'Health full';
  barricadeButtons.forEach((button, lane) => {
    button.disabled = phase !== 'build' || barricades[lane].visible || wallet < barricadeCost;
    button.textContent = laneNames[lane] + (barricades[lane].visible ? ' secured' : '');
  });
  tripwireButtons.forEach((button, lane) => {
    button.disabled = phase !== 'build' || tripwires[lane].visible || wallet < tripwireCost;
    button.textContent = laneNames[lane] + (tripwires[lane].visible ? ' armed' : '');
  });
}

function showCue(message: string, duration: number) {
  cue.textContent = message;
  cueRemaining = duration;
}

function hideBriefing() {
  intro.hidden = true;
  app.classList.add('playing');
}

function requestLook() {
  if (!host.requestPointerLock || document.pointerLockElement) return;
  try {
    const request = host.requestPointerLock();
    void request?.catch(() => {});
  } catch {
    // Drag-to-look is available when pointer lock is blocked.
  }
}

function prepareBuildView() {
  reloadRemaining = 0;
  shotCooldown = 0;
  damageRemaining = 0;
  drag = null;
  clearWolves();
  moon.shadow.needsUpdate = true;
  updateMusic();
  yaw = 0;
  pitch = -0.68;
  setScope(false);
  rifle.visible = false;
  look(0, 0);
  intro.hidden = true;
  app.classList.remove('playing');
  cue.textContent = '';
  if (document.pointerLockElement === host) document.exitPointerLock();
}

function finishNight() {
  phase = 'summary';
  survived++;
  recordScore();
  prepareBuildView();
  status.textContent = 'Dawn';
  summaryTitle.textContent = 'Watch ' + night + ' complete';
  summaryKills.textContent = String(watchKills);
  summaryCoins.textContent = String(watchKills * wolfBounty);
  updateHud();
  watchSummary.showModal();
}

function beginBuild() {
  phase = 'build';
  lastFrame = performance.now();
  buildRemaining = buildDuration;
  app.classList.add('building');
  buildPanel.hidden = false;
  nextNightButton.textContent = night === 0 ? 'Start Night Watch' : 'Start next night';
  buildMessage.textContent = night === 0
    ? 'Prepare the lookout before your first Night Watch.'
    : 'You survived Watch ' + survived + '. Restock and prepare for the next pack.';
  if (night > 0 && rounds + reserve === 0 && wallet < ammoBoxCost) {
    const relief = ammoBoxCost - wallet;
    wallet += relief;
    buildMessage.textContent = 'Dawn relief added ' + relief + ' coins so you can buy a box of ammo.';
  }
  status.textContent = 'Building';
  updateHud();
}

function updateBuild(delta: number) {
  buildRemaining = Math.max(0, buildRemaining - delta);
  if (buildRemaining <= 0.000001) startNight(false);
  else updateClock();
}

function updateMusic() {
  setMusicPlaying(musicEnabled && phase === 'night' && !paused);
}

function toggleMusic() {
  musicEnabled = !musicEnabled;
  musicButton.textContent = musicEnabled ? 'Music on' : 'Music off';
  musicButton.setAttribute('aria-pressed', String(musicEnabled));
  updateMusic();
}

function startRun() {
  if (phase !== 'ready' && phase !== 'lost') return;
  wallet = startingCoins;
  night = 0;
  elapsed = 0;
  survived = 0;
  totalKills = 0;
  health = maxHealth;
  rounds = chamberCapacity;
  reserve = startingAmmo - chamberCapacity;
  boltInstalled = false;
  barricades.forEach(barricade => { barricade.visible = false; });
  tripwires.forEach(tripwire => { tripwire.visible = false; });
  enableAudio();
  prepareBuildView();
  beginBuild();
}

function startNight(lockPointer = true) {
  if (phase !== 'build' && !(phase === 'night' && paused)) return;
  lastFrame = performance.now();
  if (paused) {
    paused = false;
    status.textContent = 'Watch ' + night;
    updateHud();
    hideBriefing();
    enableAudio();
    updateMusic();
    if (lockPointer) requestLook();
    return;
  }
  phase = 'night';
  night++;
  buildRemaining = 0;
  drag = null;
  buildPanel.hidden = true;
  app.classList.remove('building');
  elapsed = 0;
  watchKills = 0;
  damageRemaining = 0;
  moon.shadow.needsUpdate = true;
  reloadRemaining = 0;
  shotCooldown = 0;
  yaw = 0;
  pitch = ledgePreview ? -0.24 : -0.17;
  look(0, 0);
  setScope(false);
  clearWolves();
  arrivals = 0;
  nextArrival = 0.25;
  sectorBag.length = 0;
  for (const sector of sectors) routeBags[sector].length = 0;
  if (ledgePreview) {
    nextArrival = Infinity;
    const wolf = beginApproach(wolfPool.pop() ?? addWolfToScene(), nextApproach(), 0, 'regular');
    const { foot } = entries[1][0];
    reserveClimb(wolf, foot, new THREE.Vector3(0, 0, 1), 1);
    if (wolf.assault) wolf.assault.climbAt = 1.35 - wolf.assault.climbTime;
    wolf.warns = false;
    wolves.push(wolf);
  }
  hideBriefing();
  status.textContent = 'Watch ' + night;
  const watchCue = night === 1 ? 'Hold until dawn. Watch the gaps between the trees.' : 'Watch ' + night + ' · Hold until dawn.';
  const message = ledgePreview ? 'Watch the center of the ledge.' : watchCue;
  showCue(rounds === 0 && reserve > 0 ? 'Press R to chamber a round.' : message, 5);
  updateHud();
  enableAudio();
  updateMusic();
  if (lockPointer) requestLook();
}

function pauseNight() {
  if (phase !== 'night' || paused) return;
  paused = true;
  updateMusic();
  setScope(false);
  updateHud();
  status.textContent = 'Paused';
  heading.textContent = 'Night Watch paused';
  briefing.textContent = 'The werewolves will stay put until you resume.';
  startButton.textContent = 'Resume the night';
  intro.hidden = false;
  app.classList.remove('playing');
  if (document.pointerLockElement === host) document.exitPointerLock();
}

function loseNight() {
  phase = 'lost';
  reloadRemaining = 0;
  updateMusic();
  setScope(false);
  app.classList.remove('playing');
  if (document.pointerLockElement === host) document.exitPointerLock();
  heading.textContent = 'The werewolves got you';
  briefing.textContent = 'Watch ' + night + ' · ' + watchKills + (watchKills === 1 ? ' kill' : ' kills')
    + ' · ' + watchKills * wolfBounty + ' coins earned. Run total · ' + scoreText(survived, totalKills) + '.';
  recordScore();
  status.textContent = 'You fell';
  cue.textContent = '';
  startButton.textContent = 'Play again';
  intro.hidden = false;
  updateHud();
}

function reload() {
  if (phase !== 'night' || paused || reloadRemaining > 0 || rounds === chamberCapacity || reserve === 0) return;
  reloadRemaining = reloadTime();
  setScope(false);
  showCue('Reloading…', reloadRemaining);
  updateHud();
}

const ray = new THREE.Raycaster();
const sight = new THREE.Vector2(0, 0);
function shoot() {
  if (phase !== 'night' || paused || shotCooldown > 0 || reloadRemaining > 0) return;
  if (rounds === 0) {
    dryFireSound();
    showCue(reserve > 0 ? 'Rifle empty · Press R to reload' : 'Out of ammo', 2);
    return;
  }
  rounds--;
  shotCooldown = 0.62;
  shotSound();
  updateHud();

  scene.updateMatrixWorld();
  ray.setFromCamera(sight, camera);
  const targets = wolves.filter(wolf => wolf.appeared && wolf.root.visible && wolf.downAt === null);
  const exposedHitboxes = targets.flatMap(wolf => wolf.hitboxes);
  const hit = ray.intersectObjects([...blockers, ...barricades.filter(item => item.visible), ...exposedHitboxes], true)[0];
  const wolf = targets.find(target => target.hitboxes.some(hitbox => hitbox === hit?.object));
  if (wolf) {
    wolf.downAt = elapsed;
    if (wolf.barricadeDelay > 0 && !wolf.entered && wolf.assault) breakBarricade(wolf.assault.lane);
    totalKills++;
    watchKills++;
    wallet += wolfBounty;
    recordScore();
    hitSound();
    showCue('Werewolf killed · +' + wolfBounty + ' coins', 1.1);
    updateHud();

  } else {
    showCue(reserve > 0 ? 'Miss · Press R to reload' : 'Miss · No ammo left', 1.25);
  }
}

const bearing = new THREE.Vector3();
const cameraRight = new THREE.Vector3();
function soundPan(position: THREE.Vector3, spread: number) {
  bearing.copy(position).sub(camera.position).normalize();
  cameraRight.set(1, 0, 0).applyQuaternion(camera.quaternion);
  return THREE.MathUtils.clamp(bearing.dot(cameraRight) * spread, -0.92, 0.92);
}

function takeDamage() {
  health = Math.max(0, health - clawDamage);
  damageRemaining = 0.42;
  playerHitSound();
  if (health === 0) {
    loseNight();
  } else {
    showCue('The werewolf struck you.', 1.25);
    updateHud();
  }
}

const tangent = new THREE.Vector3();
function forestTravel(age: number, duration: number) {
  const t = THREE.MathUtils.clamp((age - entryPaceTime) / accelerationTime, 0, 1);
  const fastTime = Math.max(0, age - entryPaceTime - accelerationTime);
  const speedGain = accelerationTime * t ** 3 * (1 - t * 0.5) + fastTime;
  const braking = Math.max(0, age - (duration - cliffBrakingTime));
  return forestEntrySpeed * age + (forestRushSpeed - forestEntrySpeed) * speedGain
    - forestRushSpeed * braking ** 2 / (4 * cliffBrakingTime);
}

function recycleWolf(index: number) {
  const [wolf] = wolves.splice(index, 1);
  if (wolf.barricadeDelay > 0 && !wolf.entered && wolf.assault) breakBarricade(wolf.assault.lane);
  if (wolf.climbing && wolf.root.visible) moon.shadow.needsUpdate = true;
  wolf.root.visible = false;
  wolfPool.push(wolf);
}

function clearWolves() {
  while (wolves.length > 0) recycleWolf(wolves.length - 1);
}

function breakBarricade(lane: number) {
  barricades[lane].visible = false;
  moon.shadow.needsUpdate = true;
}

function arrivalKind(): WolfKind {
  if (night >= 4 && arrivals % 7 === 2) return 'climber';
  if (night >= 3 && arrivals % 5 === 1) return 'stalker';
  return 'regular';
}

function updateArrivals() {
  for (let index = wolves.length - 1; index >= 0; index--) {
    const { downAt } = wolves[index];
    if (downAt !== null && elapsed - downAt >= bodyDuration) recycleWolf(index);
  }
  while (nextArrival <= elapsed) {
    const route = nextApproach();
    wolves.push(beginApproach(wolfPool.pop() ?? addWolfToScene(), route, nextArrival, arrivalKind()));
    arrivals++;
    const pressure = 1 + 1.25 * (1 - 0.88 ** (night - 1));
    nextArrival += THREE.MathUtils.lerp(3.15, 2.1, nextArrival / nightDuration) / pressure;
  }
}

function reserveClimb(wolf: typeof wolves[number], position: THREE.Vector3, direction: THREE.Vector3, preferredLane?: number) {
  const openLanes = entries.flatMap((_, lane) =>
    wolves.some(other => other.downAt === null && other.assault?.lane === lane) ? [] : [lane],
  );
  if (!openLanes.length) return;
  const options = openLanes.length > 1 ? openLanes.filter(lane => lane !== lastLane) : openLanes;
  const lane = preferredLane ?? options[Math.floor(Math.random() * options.length)];
  const choices = entries[lane];
  const index = preferredLane !== undefined ? 0
    : lastEntry[lane] < 0 ? Math.floor(Math.random() * choices.length) : 1 - lastEntry[lane];
  const entry = choices[index];
  lastEntry[lane] = index;
  lastLane = lane;
  const connector = new THREE.CubicBezierCurve3(
    position.clone(),
    position.clone().addScaledVector(direction, 1.45),
    entry.foot.clone().add(new THREE.Vector3(0, 0, -2.2)),
    entry.foot.clone(),
  );
  wolf.assault = {
    lane, entry, connector,
    climbTime: entry.climbTime * (wolf.kind === 'climber' ? 0.73 : 1),
    startedAt: elapsed,
    climbAt: elapsed + connector.getLength() / forestRushSpeed,
    pose: { holds: entry.holds, progress: 0, reveal: 0 },
  };
}

function waitBelowCliff(wolf: typeof wolves[number], waitTime: number) {
  const angle = waitTime * 1.6;
  const forward = Math.sin(angle) * 1.6;
  const turnSide = Math.sign(wolf.stage.x);
  const sideways = (1 - Math.cos(angle)) * 1.6 * turnSide;
  const { x, z } = wolf.heading;
  wolf.root.position.copy(wolf.stage);
  wolf.root.position.x += x * forward - z * sideways;
  wolf.root.position.z += z * forward + x * sideways;
  tangent.set(x * Math.cos(angle) - z * turnSide * Math.sin(angle), 0,
    z * Math.cos(angle) + x * turnSide * Math.sin(angle));
}

function updateNight(delta: number) {
  elapsed = Math.min(nightDuration, elapsed + delta);
  updateClock();
  if (elapsed >= nightDuration - 0.000001) {
    elapsed = nightDuration;
    finishNight();
    return;
  }
  updateArrivals();
  shotCooldown = Math.max(0, shotCooldown - delta);
  if (reloadRemaining > 0) {
    const duration = reloadTime();
    const previous = 1 - reloadRemaining / duration;
    reloadRemaining = Math.max(0, reloadRemaining - delta);
    playReloadSounds(previous, 1 - reloadRemaining / duration, reloadDuration / duration);
    if (reloadRemaining === 0) {
      const loaded = Math.min(chamberCapacity - rounds, reserve);
      rounds += loaded;
      reserve -= loaded;
      updateHud();
    }
  }
  if (cueRemaining > 0) {
    cueRemaining -= delta;
    if (cueRemaining <= 0) cue.textContent = '';
  }

  for (const wolf of wolves) {
    const age = elapsed - wolf.bornAt;
    const forestAge = age * (wolf.kind === 'stalker' ? 1.12 : 1);
    if (wolf.climbing && wolf.root.visible) moon.shadow.needsUpdate = true;
    if (wolf.downAt !== null) {
      const fall = THREE.MathUtils.clamp((elapsed - wolf.downAt) / 0.42, 0, 1);
      animateWolfFall(wolf, fall);
      wolf.showLedgeAppearance(wolf.climbing);
      continue;
    }

    if (!wolf.assault && forestAge >= wolf.approachTime) {
      waitBelowCliff(wolf, forestAge - wolf.approachTime);
      reserveClimb(wolf, wolf.root.position, tangent);
    }
    const assault = wolf.assault;
    const entry = assault?.entry;
    const climbAge = assault ? elapsed - assault.climbAt : -1;
    const peekAge = climbAge - (assault?.climbTime ?? 0);
    const warningTime = wolf.kind === 'climber' ? 1.65 : peekDuration;
    const reveal = THREE.MathUtils.smoothstep(peekAge, 0.72, warningTime);
    if (assault && peekAge >= warningTime && !wolf.entered && !wolf.barricadeDelay && barricades[assault.lane].visible) {
      wolf.barricadeDelay = barricadeDelay;
      showCue(laneNames[assault.lane] + ' barricade is holding a werewolf back.', 2.7);
    }
    const lungeAge = peekAge - warningTime - wolf.barricadeDelay;
    const attackAge = lungeAge - lungeDuration;
    let motion: WolfMotion;
    let mistVisibility = 1;
    if (entry && attackAge >= 0) {
      motion = 'strike';
      wolf.root.position.copy(entry.landing);
      tangent.subVectors(lookoutPosition, wolf.root.position);
    } else if (entry && lungeAge >= 0) {
      motion = 'lunge';
      const progress = lungeAge / lungeDuration;
      entry.lunge.getPoint(progress, wolf.root.position);
      tangent.subVectors(lookoutPosition, wolf.root.position);
    } else if (entry && peekAge >= 0) {
      motion = 'peek';
      const rise = THREE.MathUtils.smoothstep(peekAge, 0, 0.52);
      wolf.root.position.lerpVectors(entry.ledge, entry.peek, rise);
      const { lerp, smoothstep } = THREE.MathUtils;
      wolf.root.position.y = lerp(wolf.root.position.y, entry.launch.y, reveal);
      wolf.root.position.z = lerp(wolf.root.position.z, entry.launch.z, smoothstep(reveal, 0.20, 1));
      wolf.root.position.x = lerp(wolf.root.position.x, entry.launch.x, reveal);
      tangent.subVectors(lookoutPosition, wolf.root.position);
    } else if (assault && climbAge >= 0) {
      motion = 'climb';
      const progress = climbAge / assault.climbTime;
      const { cycles, path } = assault.pose.holds;
      const pulls = progress * cycles * 2;
      const interval = pulls % 1;
      const pull = Math.floor(pulls) + THREE.MathUtils.lerp(interval, THREE.MathUtils.smoothstep(interval, 0, 1), 0.43);
      const pulse = 1 - THREE.MathUtils.smoothstep(peekAge, -1.85, -0.95);
      path.getPoint(THREE.MathUtils.lerp(progress, pull / (cycles * 2), pulse), wolf.root.position);
      assault.entry.climb.getTangentAt(progress, tangent);
    } else if (assault) {
      motion = 'rush';
      const progress = (elapsed - assault.startedAt) / (assault.climbAt - assault.startedAt);
      assault.connector.getPointAt(progress, wolf.root.position);
      assault.connector.getTangentAt(progress, tangent);
    } else if (forestAge >= wolf.approachTime) {
      motion = 'creep';
    } else {
      const stalker = wolf.kind === 'stalker';
      motion = forestAge < entryPaceTime + accelerationTime * (stalker ? 0.82 : 0.29) ? 'creep' : 'rush';
      const distance = forestTravel(forestAge, wolf.approachTime);
      const progress = distance / wolf.distance;
      wolf.approach.getPointAt(progress, wolf.root.position);
      wolf.approach.getTangentAt(progress, tangent);
      mistVisibility = THREE.MathUtils.smoothstep(distance, stalker ? 9 : 1.1, stalker ? 23 : 11);
    }

    const position = wolf.root.position;
    if (climbAge < 0) position.y = groundHeight(position.x, position.z);
    let heading = Math.atan2(-tangent.x, -tangent.z);
    const crest = THREE.MathUtils.smoothstep(peekAge, -1.2, 0);
    if (entry && (motion === 'climb' || motion === 'peek')) {
      const ledgeHeading = Math.atan2(entry.peek.x, entry.peek.z - lookoutPosition.z);
      const difference = ledgeHeading - heading;
      heading += Math.atan2(Math.sin(difference), Math.cos(difference)) * crest;
    }
    if (wolf.appeared) {
      const difference = heading - wolf.root.rotation.y;
      const turn = Math.atan2(Math.sin(difference), Math.cos(difference));
      wolf.root.rotation.y += THREE.MathUtils.clamp(turn * (1 - Math.exp(-8 * delta)), -4.2 * delta, 4.2 * delta);
    } else {
      wolf.root.rotation.y = heading;
    }
    wolf.root.rotation.x = motion === 'climb'
      ? -0.32 * THREE.MathUtils.smoothstep(climbAge, 0, 0.38) * (1 - crest)
      : 0;
    const peeking = motion === 'peek';
    const nearLedge = !!assault && peekAge >= -0.46;
    wolf.root.visible = (motion !== 'climb' || nearLedge) && mistVisibility > 0.02;
    wolf.setMistVisibility(mistVisibility);
    if (assault) {
      assault.pose.progress = THREE.MathUtils.clamp(climbAge / assault.climbTime, 0, 1);
      assault.pose.reveal = reveal;
    }
    let poseTime = age + wolf.bornAt * 0.37;
    if (motion === 'lunge') poseTime = lungeAge / lungeDuration;
    if (motion === 'strike') poseTime = (attackAge / strikeInterval + strikeMoment) % 1;
    animateWolf(wolf, poseTime, motion, delta, motion === 'strike' ? chamberFloor : groundHeight, assault?.pose);
    wolf.showLedgeAppearance(nearLedge);

    if (!wolf.appeared) {
      wolf.appeared = true;
      if (wolf.warns) {
        howl(soundPan(position, 0.65));
        showCue('A distant howl breaks the silence.', 2.4);
      }
    }
    if (motion === 'climb' && assault) {
      if (!wolf.climbing) {
        wolf.climbing = true;
        const { lane } = assault;
        if (tripwires[lane].visible) {
          tripwireBellSound((lane - 1) * 0.78);
          showCue(laneNames[lane] + ' tripwire bell rings.', 3);
        } else {
          showCue('Claws scrape against the rock.', 3);
        }
      }
      const { holds, progress } = assault.pose;
      const grip = Math.floor(progress * holds.cycles);
      if (grip > wolf.lastScrape) {
        clawScrape(soundPan(position, 1.45), progress);
        wolf.lastScrape = grip;
      }
    }
    if (peeking && peekAge >= 0.60 && !wolf.growled) {
      wolf.growled = true;
      wolfGrowl(soundPan(position, 1.65));
      showCue('A low growl at the ledge.', 2.15);
    }
    if (lungeAge >= 0 && !wolf.entered) {
      wolf.entered = true;
      if (wolf.barricadeDelay > 0 && assault) breakBarricade(assault.lane);
      wolfRoar(soundPan(position, 1.8));
      showCue('A werewolf lunges!', 1.6);
    }
    if (attackAge >= wolf.strikes * strikeInterval) {
      wolf.strikes++;
      takeDamage();
      if (health === 0) return;
    }
  }
}

startButton.addEventListener('click', () => {
  if (paused) startNight();
  else {
    startRun();
    if (ledgePreview) startNight();
  }
});
if (ledgePreview) {
  heading.textContent = 'Werewolf at the ledge';
  briefing.textContent = 'One werewolf is already climbing the center approach. Watch it grip the ledge, rise, and lunge.';
  startButton.textContent = 'Preview encounter';
  startButton.disabled = true;
  void ledgeModelReady.then(ready => {
    startButton.disabled = !ready;
    if (!ready) briefing.textContent = 'The werewolf model could not load. Reload the page to retry.';
  });
}
nextNightButton.addEventListener('click', () => { if (phase === 'build') startNight(); });
watchSummary.addEventListener('close', () => { if (phase === 'summary') beginBuild(); });
function toggleScope() {
  if (phase === 'night' && !paused && reloadRemaining === 0) setScope(!scoped);
}

scopeButton.addEventListener('click', toggleScope);
reloadButton.addEventListener('click', reload);
musicButton.addEventListener('click', toggleMusic);

ammoButton.addEventListener('click', () => {
  if (phase !== 'build' || wallet < ammoBoxCost) return;
  wallet -= ammoBoxCost;
  reserve += ammoBoxRounds;
  buildMessage.textContent = 'Bought ' + ammoBoxRounds + ' spare rounds.';
  updateHud();
});

boltButton.addEventListener('click', () => {
  if (phase !== 'build' || boltInstalled || wallet < boltCost) return;
  wallet -= boltCost;
  boltInstalled = true;
  buildMessage.textContent = 'Faster bolt installed for this run.';
  updateHud();
});

healthButton.addEventListener('click', () => {
  if (phase !== 'build' || health >= maxHealth || wallet < firstAidCost) return;
  const restored = Math.min(firstAidHealth, maxHealth - health);
  wallet -= firstAidCost;
  health += restored;
  buildMessage.textContent = 'Recovered ' + restored + ' health.';
  updateHud();
});

const barricadeButtons = laneNames.map((name, lane) => {
  const button = document.createElement('button');
  button.type = 'button';
  button.addEventListener('click', () => {
    const barricade = barricades[lane];
    if (phase !== 'build' || barricade.visible || wallet < barricadeCost) return;
    wallet -= barricadeCost;
    barricade.visible = true;
    moon.shadow.needsUpdate = true;
    buildMessage.textContent = name + ' barricade installed.';
    updateHud();
  });
  barricadeLanes.append(button);
  return button;
});

const tripwireButtons = laneNames.map((name, lane) => {
  const button = document.createElement('button');
  button.type = 'button';
  button.addEventListener('click', () => {
    const tripwire = tripwires[lane];
    if (phase !== 'build' || tripwire.visible || wallet < tripwireCost) return;
    wallet -= tripwireCost;
    tripwire.visible = true;
    buildMessage.textContent = name + ' tripwire bell armed.';
    updateHud();
  });
  tripwireLanes.append(button);
  return button;
});

document.addEventListener('pointerlockchange', () => {
  if (phase === 'build') {
    if (document.pointerLockElement === host) document.exitPointerLock();
    return;
  }
  if (document.pointerLockElement === host) {
    status.textContent = 'Watch ' + night;
  } else {
    pauseNight();
  }
});
window.addEventListener('blur', pauseNight);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) pauseNight();
  if (phase === 'build') lastFrame = performance.now();
});

document.addEventListener('keydown', event => {
  if (event.repeat) return;
  if (event.code === 'KeyM') {
    toggleMusic();
    return;
  }
  if (paused) return;
  if (phase !== 'night') return;
  if (event.code === 'KeyR') reload();
  if (event.code === 'KeyQ') toggleScope();
  if (event.code === 'Escape' && !document.pointerLockElement) pauseNight();
  if (event.code === 'Space' && !(event.target instanceof HTMLButtonElement)) {
    event.preventDefault();
    shoot();
  }
});
host.addEventListener('contextmenu', event => event.preventDefault());

let drag: { id: number; x: number; y: number; distance: number } | null = null;
host.addEventListener('pointerdown', event => {
  if (event.button === 2) {
    toggleScope();
    return;
  }
  if (event.button !== 0 || !event.isPrimary || paused || (phase !== 'build' && phase !== 'night')) return;
  if (document.pointerLockElement === host) {
    shoot();
  } else {
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, distance: 0 };
    host.setPointerCapture(event.pointerId);
  }
});
host.addEventListener('pointermove', event => {
  if (paused || (phase !== 'build' && phase !== 'night')) return;
  if (document.pointerLockElement === host) {
    look(event.movementX, event.movementY);
  } else if (drag?.id === event.pointerId) {
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    drag.distance += Math.hypot(dx, dy);
    if (drag.distance > 4) look(dx, dy);
    drag.x = event.clientX;
    drag.y = event.clientY;
  }
});
host.addEventListener('pointerup', event => {
  if (drag?.id !== event.pointerId) return;
  const clicked = drag.distance <= 4;
  drag = null;
  if (clicked && phase === 'night') shoot();
});
host.addEventListener('lostpointercapture', () => { drag = null; });

function resize() {
  const width = host.clientWidth;
  const height = host.clientHeight;
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
  renderer.setSize(width, height, false);
}
window.addEventListener('resize', resize);
resize();
look(0, 0);
setScope(false);
updateHud();

let lastFrame = performance.now();
renderer.setAnimationLoop(now => {
  let remaining = Math.max(0, (now - lastFrame) / 1000);
  lastFrame = now;
  damageRemaining = Math.max(0, damageRemaining - remaining);
  while (remaining > 0.000001 && phase === 'night' && !paused) {
    const step = Math.min(remaining, 0.08, nightDuration - elapsed);
    updateNight(step);
    remaining -= step;
  }
  if (phase === 'build' && !document.hidden) updateBuild(remaining);
  app.classList.toggle('hurt', damageRemaining > 0);
  const recoil = Math.max(0, shotCooldown - 0.43) * 1.45;
  const reloadProgress = reloadRemaining > 0 ? 1 - reloadRemaining / reloadTime() : 0;
  const ease = THREE.MathUtils.smoothstep;
  const present = ease(reloadProgress, 0, 0.15) * (1 - ease(reloadProgress, 0.89, 1));
  rifle.position.set(0.267 - present * 0.176, -0.349 + present * 0.194, -0.751 + recoil * 0.39 + present * 0.046);
  rifle.rotation.set(0.042 + recoil + present * 0.135, 0.183 + present * 0.32, -0.088 + present * 1.04);
  poseReload(reloadProgress);
  glow.intensity = 12.5 + Math.sin(now * 0.006) * 0.73 + Math.sin(now * 0.017) * 0.36;
  app.classList.toggle('shot', phase === 'night' && !paused && shotCooldown > 0.56);
  mistTime.value = now / 1000;
  renderer.render(scene, camera);
});
