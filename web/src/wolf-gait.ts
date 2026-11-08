import * as THREE from 'three';
import { reach, type WolfLimb } from './wolf-rig';

export type HindLeg = WolfLimb & { toes: THREE.Group };

export function createPawTrack() {
  return {
    planted: new THREE.Vector3(),
    next: new THREE.Vector3(),
    pad: new THREE.Vector3(),
    ankle: new THREE.Vector3(),
    orientation: new THREE.Quaternion(),
    heading: 0,
    padHeading: 0,
    nextHeading: 0,
    pitch: 0,
    toeCurl: 0,
    startPitch: 0,
    swinging: false,
  };
}

type PawTrack = ReturnType<typeof createPawTrack>;
type Floor = (x: number, z: number) => number;

const { lerp, smoothstep, smootherstep } = THREE.MathUtils;
const up = new THREE.Vector3(0, 1, 0);
const across = new THREE.Vector3(1, 0, 0);
const surface = new THREE.Vector3();
const toeOffset = new THREE.Vector3();
const goal = new THREE.Vector3();
const pole = new THREE.Vector3();
const level = new THREE.Quaternion();
const yaw = new THREE.Quaternion();
const frame = new THREE.Quaternion();

function setContact(out: THREE.Vector3, root: THREE.Group, ground: Floor, side: number, width: number, lead: number) {
  const heading = root.rotation.y;
  const x = side * width;
  out.set(root.position.x + Math.cos(heading) * x - Math.sin(heading) * lead, 0,
    root.position.z - Math.sin(heading) * x - Math.cos(heading) * lead);
  out.y = ground(out.x, out.z) + 0.044;
}

export function initializePaw(track: PawTrack, root: THREE.Group, ground: Floor, side: number) {
  setContact(track.planted, root, ground, side, 0.245, -0.10 + side * 0.13);
  track.pad.copy(track.planted);
  track.heading = root.rotation.y + side * 0.075;
  track.padHeading = track.heading;
  track.pitch = 0;
  track.swinging = false;
  track.toeCurl = 0;
}

function swingPaw(track: PawTrack, progress: number, height: number) {
  const advance = smootherstep(progress, 0, 1);
  track.pad.lerpVectors(track.planted, track.next, advance);
  const turn = track.nextHeading - track.heading;
  track.padHeading = track.heading + Math.atan2(Math.sin(turn), Math.cos(turn)) * advance;
  const clear = smoothstep(progress, 0, 0.31) * (1 - smoothstep(progress, 0.32, 1));
  track.pad.y += clear * height;
  track.toeCurl = -0.28 * clear;
  track.pitch = lerp(track.startPitch, 0.055, advance)
    - smoothstep(progress, 0, 0.27) * (1 - smoothstep(progress, 0.36, 0.92)) * 0.34;
}

function finishStep(track: PawTrack) {
  track.planted.copy(track.next);
  track.heading = track.nextHeading;
  track.swinging = false;
}

export function stepPaw(
  track: PawTrack, root: THREE.Group, ground: Floor, phase: number,
  stride: number, duty: number, pace: number, side: number,
) {
  if (phase >= duty) {
    if (!track.swinging) {
      // Predict the body at touchdown, with the pad ahead to catch its weight.
      const lead = stride * (1 - phase + duty * 0.49) - 0.065;
      setContact(track.next, root, ground, side, lerp(0.237, 0.196, pace), lead);
      track.nextHeading = root.rotation.y + side * 0.075;
      track.startPitch = track.pitch;
      track.swinging = true;
    }
    swingPaw(track, (phase - duty) / (1 - duty), lerp(0.13, 0.31, pace));
    return;
  }

  if (track.swinging) finishStep(track);
  const support = phase / duty;
  const compress = smoothstep(support, 0, 0.22) * (1 - smoothstep(support, 0.28, 0.64));
  track.pitch = 0.055 + compress * lerp(0.13, 0.26, pace)
    - smoothstep(support, 0.55, 1) * (0.055 + lerp(0.37, 0.57, pace));
  track.pad.copy(track.planted);
  track.padHeading = track.heading;
}

export function settlePaw(track: PawTrack, root: THREE.Group, ground: Floor, side: number, progress: number, begin: boolean) {
  if (begin) {
    track.planted.copy(track.pad);
    track.startPitch = track.pitch;
    track.heading = track.padHeading;
    setContact(track.next, root, ground, side, 0.245, -0.12 + side * 0.13);
    track.nextHeading = root.rotation.y + side * 0.075;
    track.swinging = true;
  }
  if (track.swinging && progress >= 1) finishStep(track);
  if (track.swinging) {
    swingPaw(track, progress, 0.033);
  } else {
    track.pad.copy(track.planted);
    track.padHeading = track.heading;
    track.pitch *= 1 - progress;
  }
}

export function prepareHindLeg(limb: HindLeg, track: PawTrack, ground: Floor) {
  const { pad } = track;
  pad.y = Math.max(pad.y, ground(pad.x, pad.z) + 0.044);
  const x = ground(pad.x - 0.14, pad.z) - ground(pad.x + 0.14, pad.z);
  const z = ground(pad.x, pad.z - 0.14) - ground(pad.x, pad.z + 0.14);
  surface.set(x, 0.28, z).normalize();
  level.setFromUnitVectors(up, surface);
  yaw.setFromAxisAngle(up, track.padHeading);
  track.orientation.copy(level).multiply(yaw).multiply(frame.setFromAxisAngle(across, track.pitch));

  // Rotate the long metatarsus around the planted toe joint.
  toeOffset.copy(limb.toes.position).applyQuaternion(track.orientation);
  track.ankle.copy(pad).sub(toeOffset);
}

export function supportHeight(limb: HindLeg, track: PawTrack) {
  if (track.swinging) return 0;
  limb.frame.getWorldPosition(goal);
  const dx = goal.x - track.ankle.x;
  const dz = goal.z - track.ankle.z;
  const reach = limb.upper.length() + limb.lower.length() - 0.012;
  const available = Math.sqrt(Math.max(0, reach * reach - dx * dx - dz * dz));
  return Math.max(0, goal.y - track.ankle.y - available);
}

export function poseHindLeg(limb: HindLeg, track: PawTrack, side: number) {
  goal.copy(track.ankle);
  limb.frame.worldToLocal(goal);
  reach(limb, goal, pole.set(side * 0.12, 0, -1));
  limb.frame.getWorldQuaternion(frame).invert();
  limb.end.quaternion.multiply(frame).multiply(track.orientation);
  limb.toes.rotation.x = track.toeCurl - track.pitch;
}
