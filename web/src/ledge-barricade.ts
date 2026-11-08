import * as THREE from 'three';
import { box } from './geometry';
import { weatheredWood } from './lookout-materials';

const plank = weatheredWood('#c8a888');
const brace = weatheredWood('#977b64');
const top = weatheredWood('#d4b99a');

export function createLedgeBarricade(room: THREE.Group, x: number, lane: string) {
  const barricade = new THREE.Group();
  barricade.name = lane + ' ledge barricade';
  barricade.position.set(x, 0, 0.41);
  for (const side of [-1, 1]) {
    box(barricade, 0.09, 0.52, 0.13, side * 0.53, 0.24, 0.05, brace).rotation.x = -0.18;
    box(barricade, 0.095, 0.10, 0.51, side * 0.53, 0.045, 0.17, brace);
    box(barricade, 1.23, 0.105, 0.095, 0, 0.28, -0.018, plank).rotation.z = side * 0.15;
  }
  box(barricade, 1.19, 0.105, 0.11, 0, 0.44, -0.025, top);
  barricade.children.forEach(part => { part.castShadow = part.receiveShadow = true; });
  barricade.visible = false;
  room.add(barricade);
  return barricade;
}
