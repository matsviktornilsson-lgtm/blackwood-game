import type { Material } from 'three';

const fogged = new WeakSet<Material>();

export function applyValleyFog(material: Material, time: { value: number }) {
  if (!('fog' in material) || !material.fog || fogged.has(material)) return;
  fogged.add(material);
  const compile = material.onBeforeCompile;
  const cacheKey = material.customProgramCacheKey();
  material.customProgramCacheKey = () => cacheKey + ':valley';
  material.onBeforeCompile = (shader, renderer) => {
    compile.call(material, shader, renderer);
    shader.uniforms.valleyTime = time;
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 valleyPoint;')
      .replace('#include <fog_vertex>', `
        #include <fog_vertex>
        vec4 valleyPosition = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          valleyPosition = instanceMatrix * valleyPosition;
        #endif
        valleyPoint = (modelMatrix * valleyPosition).xyz;
      `);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `
        #include <common>
        varying vec3 valleyPoint;
        uniform float valleyTime;

        float valleyNoise(vec2 p) {
          vec2 i = floor(p);
          vec2 f = smoothstep(0.0, 1.0, fract(p));
          vec4 h = fract(sin(vec4(dot(i, vec2(127.1, 311.7))) + vec4(0.0, 127.1, 311.7, 438.8)) * 43758.5453);
          return mix(mix(h.x, h.y, f.x), mix(h.z, h.w, f.x), f.y);
        }
      `)
      .replace('#include <fog_fragment>', `
        #include <fog_fragment>
        vec3 lineOfSight = valleyPoint - cameraPosition;
        float distanceToSurface = length(lineOfSight);
        // Integrate an exponential density profile along the line of sight.
        float eyeHeight = max(cameraPosition.y, 0.0) * 0.18;
        float surfaceHeight = max(valleyPoint.y, 0.0) * 0.18;
        float span = eyeHeight - surfaceHeight;
        float density = abs(span) > 0.01
          ? (exp(-surfaceHeight) - exp(-eyeHeight)) / span
          : exp(-0.5 * (eyeHeight + surfaceHeight));
        vec2 p = valleyPoint.xz * vec2(0.05, 0.11) - vec2(valleyTime * 0.025, valleyTime * 0.009);
        float banks = valleyNoise(p * 0.54 + 3.0) * 0.74 + valleyNoise(p * 1.41) * 0.26;
        float valley = smoothstep(15.0, 39.0, distanceToSurface)
          * (1.0 - exp(-distanceToSurface * density * mix(0.010, 0.040, banks)));
        gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.32, 0.38, 0.42), valley * 0.81);
      `);
  };
}
