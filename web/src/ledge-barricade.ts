import * as THREE from 'three';
import { box } from './geometry';
import { weatheredWood } from './lookout-materials';

const plank = weatheredWood('#c8a888');
const brace = weatheredWood('#977b64');
const iron = new THREE.MeshStandardMaterial({ color: '#3c3935', metalness: 0.65, roughness: 0.61 });

export function createLedgeBarricade(room: THREE.Group, x: number, lane: string) {
  const barricade = new THREE.Group();
  barricade.name = lane + ' ledge barricade';
  // The frame catches climbers on the outside of the cliff, beneath the lookout's sightline.
  barricade.position.set(x, 0, -0.79);
  box(barricade, 1.20, 0.15, 0.15, 0, -0.54, -0.07, plank);
  box(barricade, 1.14, 0.10, 0.12, 0, -0.92, -0.04, plank);
  for (const side of [-1, 1]) {
    const postX = side * 0.49;
    box(barricade, 0.10, 0.59, 0.13, postX, -0.76, 0.02, brace).rotation.x = -0.10;
    box(barricade, 0.10, 0.46, 0.085, postX, -0.77, 0.19, brace).rotation.x = -0.68;
    box(barricade, 0.14, 0.21, 0.04, postX, -0.53, -0.15, iron);
    // The straps run back over the sill to anchor the hanging frame to the cave floor.
    box(barricade, 0.13, 0.055, 0.83, postX, 0.051, 1.42, iron);
    box(barricade, 0.16, 0.11, 0.18, postX, 0.063, 1.79, iron);
  }
  box(barricade, 1.20, 0.15, 0.27, 0, 0.052, 1.67, plank);
  barricade.children.forEach(part => { part.castShadow = part.receiveShadow = true; });
  barricade.visible = false;
  room.add(barricade);
  return barricade;
}
