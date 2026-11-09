import * as THREE from 'three';
import { DRACO_GLTF_CONFIG, DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { clone } from 'three/addons/utils/SkeletonUtils.js';
import type { createWolf } from './wolf';
import wolfAsset from './assets/werewolf/ledge-wolf.glb?url';
import coatGrainUrl from './assets/werewolf/short-hair.webp';
import leatherGrainUrl from './assets/werewolf/hide.webp';

let template: THREE.Group | undefined;
const draco = new DRACOLoader().setDecoderPath(DRACO_GLTF_CONFIG).setWorkerLimit(2);
const closeupLights = THREE.ShaderChunk.lights_fragment_begin.replace(
  'getPointLightInfo( pointLight, geometryPosition, directLight );',
  'getPointLightInfo( pointLight, geometryPosition, directLight ); directLight.color *= 0.48;',
);
export const ledgeModelReady = new GLTFLoader().setDRACOLoader(draco).loadAsync(wolfAsset).then(({ scene }) => {
  const loader = new THREE.TextureLoader();
  const coatGrain = loader.load(coatGrainUrl);
  const leatherGrain = loader.load(leatherGrainUrl);
  for (const texture of [coatGrain, leatherGrain]) {
    texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
    texture.flipY = false;
  }
  const tuned = new Set<THREE.MeshStandardMaterial>();
  scene.traverse(part => {
    if (!(part instanceof THREE.Mesh) || !(part.material instanceof THREE.MeshStandardMaterial)) return;
    const material = part.material;
    if (tuned.has(material)) return;
    tuned.add(material);
    if (part.geometry.hasAttribute('uv') && /pelt|leather/i.test(material.name)) {
      const isPelt = /pelt/i.test(material.name);
      material.bumpMap = isPelt ? coatGrain : leatherGrain;
      material.bumpScale = isPelt ? 0.018 : 0.012;
    }
    material.onBeforeCompile = shader => {
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <roughnessmap_fragment>', `
          #include <roughnessmap_fragment>
          #ifdef USE_BUMPMAP
            float coatGrain = texture2D(bumpMap, vBumpMapUv).r;
            roughnessFactor = clamp(roughnessFactor + (coatGrain - 0.28) * 0.32, 0.48, 0.98);
            diffuseColor.rgb *= mix(0.64, 1.38, smoothstep(0.04, 0.52, coatGrain));
          #endif
        `)
        .replace('#include <lights_fragment_begin>', closeupLights)
        .replace('#include <opaque_fragment>',
          'outgoingLight += diffuseColor.rgb * vec3(0.115, 0.121, 0.132);\n#include <opaque_fragment>');
    };
  });
  template = scene;
  return true;
}, error => {
  console.warn('Could not load the ledge werewolf.', error);
  return false;
}).finally(() => draco.dispose());

type Wolf = ReturnType<typeof createWolf>;

export function createLedgeAppearance(wolf: Wolf) {
  const forestMeshes: THREE.Mesh[] = [];
  wolf.root.traverse(part => {
    if (part instanceof THREE.Mesh && part.visible) forestMeshes.push(part);
  });
  const joints: [string, THREE.Object3D][] = [
    ['Chest', wolf.chest], ['Pelvis', wolf.pelvis], ['Head', wolf.head], ['Jaw', wolf.jaw], ['Tail', wolf.tail],
  ];
  for (const [index, suffix] of ['L', 'R'].entries()) {
    const arm = wolf.arms[index];
    const leg = wolf.legs[index];
    joints.push(
      ['Shoulder.' + suffix, arm.first], ['Elbow.' + suffix, arm.middle], ['Wrist.' + suffix, arm.end],
      ['Hip.' + suffix, leg.first], ['Knee.' + suffix, leg.middle], ['Hock.' + suffix, leg.end],
      ['Toes.' + suffix, leg.toes],
    );
  }
  const rest = joints.map(([, source]) => source.getWorldQuaternion(new THREE.Quaternion()).invert());
  const worldPosition = new THREE.Vector3();
  const worldRotation = new THREE.Quaternion();
  const parentRotation = new THREE.Quaternion();
  const rootRotation = new THREE.Quaternion();
  const jawCorrection = new THREE.Quaternion();
  const jawAxis = new THREE.Vector3(1, 0, 0);
  let model: THREE.Object3D | undefined;
  let drivers: { source: THREE.Object3D; bone: THREE.Bone; offset: THREE.Quaternion }[] = [];
  let showing = false;

  return (close: boolean) => {
    if (close && !model && template) {
      const instance = clone(template);
      const bones = joints.map(([name]) => instance.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name)));
      if (!bones.every(bone => bone instanceof THREE.Bone)) return;
      model = instance;
      model.name = 'Blender ledge werewolf';
      wolf.root.add(model);
      model.traverse(part => {
        if (!(part instanceof THREE.Mesh)) return;
        part.frustumCulled = false;
        part.receiveShadow = true;
        part.castShadow = !part.name.includes('guard_hair');
      });
      wolf.root.getWorldQuaternion(rootRotation).invert();
      drivers = bones.map((bone, index) => ({
        bone,
        source: joints[index][1],
        offset: rest[index].clone().multiply(rootRotation).multiply(bone.getWorldQuaternion(worldRotation)),
      }));
    }
    if (!model) return;
    if (close !== showing) {
      showing = close;
      model.visible = close;
      for (const part of forestMeshes) {
        if (close) part.layers.disable(0);
        else part.layers.enable(0);
      }
    }
    if (!close) return;
    wolf.root.updateWorldMatrix(true, true);
    // Keep the in-game hand contacts and jaw motion while the Blender skin deforms around the same joints.
    for (const { bone, source, offset } of drivers) {
      const parent = bone.parent!;
      bone.position.copy(parent.worldToLocal(source.getWorldPosition(worldPosition)));
      parent.getWorldQuaternion(parentRotation).invert();
      source.getWorldQuaternion(worldRotation);
      if (source === wolf.jaw) worldRotation.multiply(jawCorrection.setFromAxisAngle(jawAxis, -wolf.jaw.rotation.x * 0.34));
      bone.quaternion.copy(parentRotation).multiply(worldRotation).multiply(offset);
      bone.updateMatrixWorld(true);
    }
  };
}
