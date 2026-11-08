import * as THREE from 'three';
import slateUrl from './assets/lookout/slate.webp';
import floorUrl from './assets/lookout/floor.webp';
import timberUrl from './assets/lookout/timber.webp';
import groundUrl from './assets/lookout/ground.webp';
import horizonUrl from './assets/lookout/horizon.webp';
import spruceAUrl from './assets/lookout/spruce-a.webp';
import spruceBUrl from './assets/lookout/spruce-b.webp';
import spruceCUrl from './assets/lookout/spruce-c.webp';

const loader = new THREE.TextureLoader();

function materialTexture(url: string) {
  const texture = loader.load(url);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
}

const slate = materialTexture(slateUrl);
const floor = materialTexture(floorUrl);
const timber = materialTexture(timberUrl);
export const groundTexture = materialTexture(groundUrl);
export const horizonTexture = loader.load(horizonUrl);
horizonTexture.colorSpace = THREE.SRGBColorSpace;

export const spruceSprites = ([[spruceAUrl, 0.56], [spruceBUrl, 0.59], [spruceCUrl, 0.47]] as const).map(([url, width]) => {
  const map = loader.load(url);
  map.colorSpace = THREE.SRGBColorSpace;
  return { map, width };
});

const timberRelief = timber.clone();
timberRelief.colorSpace = THREE.NoColorSpace;

export function weatheredWood(color = '#c7ae92') {
  return new THREE.MeshStandardMaterial({
    color, map: timber, bumpMap: timberRelief, bumpScale: 0.009, roughness: 0.81,
  });
}

export function slateSurface(options: { tint?: string; floor?: boolean; wall?: boolean } = {}) {
  const material = new THREE.MeshStandardMaterial({
    color: options.tint ?? '#c1c6cb',
    roughness: options.floor ? 0.63 : 0.84,
    vertexColors: !!options.wall,
    side: options.wall ? THREE.DoubleSide : THREE.FrontSide,
  });
  const texture = options.floor ? floor : slate;
  const scale = options.floor ? 0.48 : 0.63;

  material.onBeforeCompile = shader => {
    shader.uniforms.slateMap = { value: texture };
    shader.uniforms.slateScale = { value: scale };
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 slatePoint;')
      .replace('#include <worldpos_vertex>', `
        #include <worldpos_vertex>
        slatePoint = (modelMatrix * vec4(transformed, 1.0)).xyz;
      `);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `
        #include <common>
        varying vec3 slatePoint;
        uniform sampler2D slateMap;
        uniform float slateScale;
      `)
      .replace('#include <map_fragment>', `
        vec3 slateAxis = abs(normalize(cross(dFdx(slatePoint), dFdy(slatePoint))));
        slateAxis = pow(slateAxis, vec3(4.0));
        slateAxis /= max(dot(slateAxis, vec3(1.0)), 0.001);
        vec3 slateUv = slatePoint * slateScale;
        vec3 slateColor =
          texture2D(slateMap, slateUv.zy).rgb * slateAxis.x +
          texture2D(slateMap, slateUv.xz).rgb * slateAxis.y +
          texture2D(slateMap, slateUv.xy).rgb * slateAxis.z;
        diffuseColor.rgb *= slateColor;
      `)
      .replace('#include <normal_fragment_maps>', `
        #include <normal_fragment_maps>
        float relief = dot(slateColor, vec3(0.21, 0.72, 0.07));
        vec3 surfaceDx = dFdx(-vViewPosition);
        vec3 surfaceDy = dFdy(-vViewPosition);
        vec3 reliefX = cross(surfaceDy, normal);
        vec3 reliefY = cross(normal, surfaceDx);
        float determinant = dot(surfaceDx, reliefX) * faceDirection;
        float fadeDetail = 1.0 - smoothstep(12.0, 30.0, length(vViewPosition));
        vec3 gradient = sign(determinant) * (dFdx(relief) * reliefX + dFdy(relief) * reliefY);
        normal = normalize(max(abs(determinant), 0.0000001) * normal - 0.016 * fadeDetail * gradient);
      `);
  };
  return material;
}
