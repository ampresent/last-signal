/**
 * lighting-engine.js — WebGL Real-time Lighting Engine for LAST SIGNAL
 *
 * Replaces pre-generated frame sequences with GPU-accelerated per-pixel lighting.
 * Reads depth maps + base scene images, applies configurable light sources at 60fps.
 *
 * Usage:
 *   const engine = new LightingEngine(canvas);
 *   await engine.loadScene('apartment', config);
 *   engine.setLights(config.scenes.apartment.lights);
 *   engine.start();
 */

class LightingEngine {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl2', { premultipliedAlpha: false, preserveDrawingBuffer: true }) ||
              canvas.getContext('webgl', { premultipliedAlpha: false, preserveDrawingBuffer: true });
    if (!this.gl) throw new Error('WebGL not supported');

    this.width = canvas.width;
    this.height = canvas.height;
    this.program = null;
    this.baseTexture = null;
    this.depthTexture = null;
    this.maskTextures = {};
    this.lights = [];
    this.time = 0;
    this.running = false;
    this.animFrame = null;
    this.sceneId = null;
    this.ambient = 0.02; // default, overridden by config
    this.onUpdate = null; // callback for editor

    this._initShaders();
    this._initQuad();
  }

  // ── Shader Setup ──────────────────────────────────────────────

  _initShaders() {
    const gl = this.gl;

    const vsSource = `
      attribute vec2 aPosition;
      attribute vec2 aTexCoord;
      varying vec2 vTexCoord;
      void main() {
        vTexCoord = aTexCoord;
        gl_Position = vec4(aPosition, 0.0, 1.0);
      }
    `;

    // Fragment shader: per-pixel depth-based lighting with shadow ray march
    const fsSource = `
      precision mediump float;
      varying vec2 vTexCoord;

      uniform sampler2D uBaseTex;
      uniform sampler2D uDepthTex;
      uniform float uTime;
      uniform float uAmbient;
      uniform vec2 uResolution;

      // Light uniforms (max 16)
      uniform int uLightCount;
      uniform vec3 uLightPos[16];      // x, y, z (z = depth plane)
      uniform vec3 uLightColor[16];
      uniform float uLightRadius[16];
      uniform float uLightIntensity[16];
      uniform int uLightType[16];       // 0=point, 1=directional, 2=global
      uniform vec2 uLightDir[16];       // direction for directional lights
      uniform float uLightPhaseVal[16]; // pre-computed phase value (0-1)

      // Phase animation uniforms
      uniform float uPhaseTime;

      float depthAt(vec2 uv) {
        // Clamp UV to edge to avoid wrapping artifacts
        uv = clamp(uv, vec2(0.0), vec2(1.0));
        return texture2D(uDepthTex, uv).r;
      }

      // ── Shadow Ray March ──
      // Traces from pixel toward light, detecting occluders along the way.
      // Returns 0.0 = fully shadowed, 1.0 = fully lit.
      float shadowRayMarch(vec2 pixelUV, vec2 lightUV, float pixelDepth, float lightDepth) {
        vec2 dir = lightUV - pixelUV;
        float totalDist = length(dir);
        if (totalDist < 0.001) return 1.0;

        vec2 stepUV = dir / 12.0;  // 12 steps
        float stepDepth = (lightDepth - pixelDepth) / 12.0;

        float shadow = 1.0;
        float blockerThreshold = 0.04;  // minimum depth difference to count as blocker

        for (int s = 1; s <= 12; s++) {
          vec2 sampleUV = pixelUV + stepUV * float(s);
          float sampleDepth = depthAt(sampleUV);

          // Expected depth at this point along the ray (linear interpolation)
          float expectedDepth = pixelDepth + stepDepth * float(s);

          // If the sampled surface is significantly shallower than expected,
          // something is blocking the light path
          float diff = expectedDepth - sampleDepth;
          if (diff > blockerThreshold) {
            // Occluder found — compute blocking strength based on how much it protrudes
            float blockStrength = smoothstep(blockerThreshold, blockerThreshold + 0.08, diff);
            shadow *= (1.0 - blockStrength);
          }
        }

        return shadow;
      }

      void main() {
        vec2 uv = vTexCoord;
        vec4 base = texture2D(uBaseTex, uv);
        float depth = depthAt(uv);

        // Convert depth to linear scale (0=near, 1=far)
        float linearDepth = depth;

        vec3 totalLight = vec3(uAmbient);

        for (int i = 0; i < 16; i++) {
          if (i >= uLightCount) break;

          float phaseVal = uLightPhaseVal[i];
          if (phaseVal <= 0.001) continue;

          vec3 lightColor = uLightColor[i] * uLightIntensity[i] * phaseVal;
          int ltype = uLightType[i];

          if (ltype == 2) {
            // Global light (e.g. lightning)
            totalLight += lightColor;
          } else if (ltype == 1) {
            // Directional light — simulates light coming from a direction
            // with depth-based falloff (farther objects receive less light)
            vec2 dir = normalize(uLightDir[i]);
            // Project pixel position along light direction
            float proj = dot(uv - vec2(0.5), dir);
            // Depth attenuation: closer surfaces get more light
            float depthAtten = 1.0 - linearDepth * 0.7;
            depthAtten = max(depthAtten, 0.1);
            // Spatial falloff from center
            float spatialFalloff = 1.0 - abs(proj) * 0.5;
            spatialFalloff = max(spatialFalloff, 0.0);
            totalLight += lightColor * depthAtten * spatialFalloff;
          } else {
            // Point light with shadow ray march
            vec2 lightUV = uLightPos[i].xy;
            float lightZ = uLightPos[i].z;
            float radius = uLightRadius[i] / max(uResolution.x, uResolution.y);

            // Distance from pixel to light in UV space
            float dist = distance(uv, lightUV);

            // ── Shadow ray march: detect occluders between pixel and light ──
            float shadow = shadowRayMarch(uv, lightUV, linearDepth, lightZ);

            // ── Geometry-based depth attenuation ──
            // Light at depth lightZ, pixel at depth linearDepth.
            // Compute the angle from light to pixel: if steep enough, light can reach.
            // The "height" of light above the pixel's depth plane:
            //   positive = light is farther (can shine down onto foreground)
            //   negative = light is closer (pixel is behind light, hard to reach)
            float depthDiff = linearDepth - lightZ;
            float horizDist = dist * max(uResolution.x, uResolution.y) / radius;
            float depthAtten = 1.0;

            if (depthDiff > 0.0) {
              // Pixel is behind the light plane.
              // Compute the elevation angle from pixel to light:
              //   angle = atan(height_above, horizontal_distance)
              // The deeper the pixel, the steeper the angle needed.
              float heightAbove = depthDiff;
              float horizPx = dist * max(uResolution.x, uResolution.y);
              // Normalize: use radius as the reference distance scale
              float r = max(uLightRadius[i], 1.0);
              float angle = atan(heightAbove * r, horizPx + 1.0);
              // Effective cone: light illuminates pixels within its cone angle.
              // Cone angle depends on light radius — larger radius = wider cone.
              // Base cone angle ~ 35 degrees (0.61 rad), scaled by radius
              float coneAngle = 0.4 + 0.3 * clamp(r / 400.0, 0.0, 1.0);
              // If angle is within cone → full light; outside → fade out
              float angleDiff = angle - coneAngle;
              if (angleDiff > 0.0) {
                // Outside cone — fade over 0.3 rad (~17°)
                depthAtten = 1.0 - smoothstep(0.0, 0.3, angleDiff);
                depthAtten = max(depthAtten, 0.03);
              }
              // Also apply distance-based depth falloff
              float distFade = 1.0 / (1.0 + heightAbove * heightAbove * 8.0);
              depthAtten *= max(distFade, 0.1);
            }

            // Combine: depth attenuation + ray march shadow
            float occlusion = depthAtten * shadow;

            // Inverse-square distance attenuation
            float atten = 1.0 / (1.0 + (dist / radius) * (dist / radius) * 10.0);
            // Soft edge falloff
            atten *= 1.0 - smoothstep(radius * 0.7, radius, dist);

            totalLight += lightColor * atten * max(occlusion, 0.0);
          }
        }

        // Apply lighting to base color (additive blend)
        vec3 result = base.rgb * (vec3(1.0) + totalLight);
        result = clamp(result, 0.0, 1.0);

        gl_FragColor = vec4(result, base.a);
      }
    `;

    const vs = this._compileShader(gl.VERTEX_SHADER, vsSource);
    const fs = this._compileShader(gl.FRAGMENT_SHADER, fsSource);

    this.program = gl.createProgram();
    gl.attachShader(this.program, vs);
    gl.attachShader(this.program, fs);
    gl.linkProgram(this.program);

    if (!gl.getProgramParameter(this.program, gl.LINK_STATUS)) {
      throw new Error('Shader link error: ' + gl.getProgramInfoLog(this.program));
    }

    gl.useProgram(this.program);

    // Cache uniform locations
    this.uniforms = {};
    const uniformNames = [
      'uBaseTex', 'uDepthTex', 'uTime', 'uAmbient', 'uResolution',
      'uLightCount', 'uPhaseTime'
    ];
    for (const name of uniformNames) {
      this.uniforms[name] = gl.getUniformLocation(this.program, name);
    }
    // Array uniforms
    for (let i = 0; i < 16; i++) {
      this.uniforms[`uLightPos[${i}]`] = gl.getUniformLocation(this.program, `uLightPos[${i}]`);
      this.uniforms[`uLightColor[${i}]`] = gl.getUniformLocation(this.program, `uLightColor[${i}]`);
      this.uniforms[`uLightRadius[${i}]`] = gl.getUniformLocation(this.program, `uLightRadius[${i}]`);
      this.uniforms[`uLightIntensity[${i}]`] = gl.getUniformLocation(this.program, `uLightIntensity[${i}]`);
      this.uniforms[`uLightType[${i}]`] = gl.getUniformLocation(this.program, `uLightType[${i}]`);
      this.uniforms[`uLightDir[${i}]`] = gl.getUniformLocation(this.program, `uLightDir[${i}]`);
      this.uniforms[`uLightPhaseVal[${i}]`] = gl.getUniformLocation(this.program, `uLightPhaseVal[${i}]`);
    }

    // Attribute locations
    this.attribs = {
      aPosition: gl.getAttribLocation(this.program, 'aPosition'),
      aTexCoord: gl.getAttribLocation(this.program, 'aTexCoord'),
    };
  }

  _compileShader(type, source) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error('Shader compile error: ' + gl.getShaderInfoLog(shader));
    }
    return shader;
  }

  _initQuad() {
    const gl = this.gl;

    // Full-screen quad
    const vertices = new Float32Array([
      -1, -1,  0, 1,   // bottom-left  (flipped Y for texture)
       1, -1,  1, 1,   // bottom-right
      -1,  1,  0, 0,   // top-left
       1,  1,  1, 0,   // top-right
    ]);

    this.vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
  }

  // ── Texture Loading ───────────────────────────────────────────

  async _loadTexture(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        const gl = this.gl;
        const tex = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        resolve(tex);
      };
      img.onerror = () => reject(new Error(`Failed to load: ${url}`));
      img.src = url;
    });
  }

  // ── Scene Loading ─────────────────────────────────────────────

  async loadScene(sceneId, config) {
    this.sceneId = sceneId;
    const scene = config.scenes[sceneId];
    if (!scene) throw new Error(`Scene "${sceneId}" not found in config`);

    // Read ambient from scene or global config
    this.ambient = scene.ambient || config.ambient || 0.02;

    // Load base image and depth map
    this.baseTexture = await this._loadTexture(`assets/${scene.base}`);
    this.depthTexture = await this._loadTexture(`assets/${scene.depth}`);

    // Set initial lights
    this.setLights(scene.lights);

    console.log(`💡 Lighting engine loaded scene: ${sceneId}`);
  }

  // ── Light Management ──────────────────────────────────────────

  setLights(lights) {
    this.lights = lights.map(l => ({ ...l }));
  }

  addLight(light) {
    if (this.lights.length >= 16) {
      console.warn('Maximum 16 lights reached');
      return false;
    }
    this.lights.push(light);
    return true;
  }

  removeLight(id) {
    this.lights = this.lights.filter(l => l.id !== id);
  }

  updateLight(id, updates) {
    const light = this.lights.find(l => l.id === id);
    if (light) Object.assign(light, updates);
  }

  getLight(id) {
    return this.lights.find(l => l.id === id);
  }

  // ── Phase Computation ─────────────────────────────────────────

  _computePhase(light, t) {
    const phase = light.phase;
    if (!phase) return 1.0;

    const speed = phase.speed || 1.0;
    const min = phase.min || 0.0;
    const max = phase.max || 1.0;
    const offset = phase.offset || 0.0;
    const range = max - min;

    let val = 0;

    switch (phase.type) {
      case 'steady':
        val = (min + max) / 2;
        break;

      case 'sine': {
        const angle = t * speed + offset;
        val = min + range * (0.5 + 0.5 * Math.sin(angle * Math.PI * 2));
        break;
      }

      case 'pulse': {
        const angle = t * speed + offset;
        val = min + range * Math.max(0, Math.sin(angle * Math.PI * 2));
        break;
      }

      case 'flicker': {
        // Multi-frequency irregular flicker
        const a1 = t * speed * 1.0 + offset;
        const a2 = t * speed * 2.3 + 1.7;
        const a3 = t * speed * 4.7 + 0.3;
        let v = (Math.sin(a1 * Math.PI * 2) +
                 0.7 * Math.sin(a2 * Math.PI * 2) +
                 0.4 * Math.sin(a3 * Math.PI * 2)) / 2.1;
        v = 0.5 + 0.5 * v;
        val = min + range * Math.max(0, Math.min(1, v));
        break;
      }

      case 'car_sweep': {
        // Car headlights: sweep pattern with dark/light zones
        const cycle = (t * speed + offset) % 1.0;
        const half = cycle < 0.5 ? cycle * 2 : 2 - cycle * 2;
        let v = half;
        // Contrast boost
        if (v < 0.4) v *= 0.1;
        else if (v < 0.6) {
          const alpha = (v - 0.4) / 0.2;
          const smooth = alpha * alpha * (3 - 2 * alpha);
          v = 0.04 * (1 - smooth) + v * smooth;
        } else {
          v = 0.6 + (v - 0.6) * 1.5;
        }
        val = min + range * Math.max(0, Math.min(1, v));
        break;
      }

      case 'lightning': {
        const angle = t * speed + offset;
        const v = 0.5 + 0.5 * Math.sin(angle * Math.PI * 2);
        if (v > 0.85) val = max;
        else if (v > 0.7) val = min + range * ((v - 0.7) / 0.15);
        else val = min;
        break;
      }

      case 'drift': {
        // Non-periodic smooth random using noise-like function
        const t_scaled = t * speed + offset;
        // Multi-octave pseudo-Perlin noise via sine sums
        let v = 0;
        v += Math.sin(t_scaled * 0.7 + 1.3) * 0.4;
        v += Math.sin(t_scaled * 1.3 + 2.7) * 0.3;
        v += Math.sin(t_scaled * 2.1 + 0.5) * 0.2;
        v += Math.sin(t_scaled * 3.7 + 4.1) * 0.1;
        v = 0.5 + v * 0.5; // normalize to ~0-1
        val = min + range * Math.max(0, Math.min(1, v));
        break;
      }

      case 'burst': {
        const t_scaled = t * speed + offset;
        // Slow baseline drift
        let base = 0.5 + 0.3 * Math.sin(t_scaled * 0.3 + 1.0);
        // Random burst trigger (using deterministic noise)
        const burstPhase = (t_scaled * 2.3) % 7.0;
        const burstStrength = Math.max(0, 1.0 - burstPhase * burstPhase);
        const burst = burstStrength * Math.max(0, Math.sin(t_scaled * 13.7));
        let v = base * 0.3 + burst * 0.7;
        val = min + range * Math.max(0, Math.min(1, v));
        break;
      }

      default:
        val = (min + max) / 2;
    }

    // ── Noise perturbation ──
    // Adds organic randomness so lights don't feel mechanical
    const noise = light.noise;
    if (noise) {
      const ni = noise.intensity || 0;
      const ns = noise.speed || 0;
      const np = noise.phase || 0;

      if (ni > 0 || ns > 0 || np > 0) {
        // Use a deterministic noise seed based on light id hash
        const seed = (light.id || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0);
        const t_noise = t * 1.7 + seed;

        // Intensity noise: random brightness wobble
        if (ni > 0) {
          const n1 = Math.sin(t_noise * 3.1 + seed * 0.1) * 0.5
                   + Math.sin(t_noise * 7.3 + seed * 0.3) * 0.3
                   + Math.sin(t_noise * 13.7 + seed * 0.7) * 0.2;
          val += n1 * ni * range * 0.5;
        }

        // Speed noise: random speed variation
        if (ns > 0) {
          const n2 = Math.sin(t_noise * 2.3 + seed * 0.2);
          val += n2 * ns * range * 0.15;
        }

        // Phase noise: random phase offset
        if (np > 0) {
          const n3 = Math.sin(t_noise * 5.1 + seed * 0.5) * 0.5
                   + Math.sin(t_noise * 11.3 + seed * 0.9) * 0.5;
          val += n3 * np * range * 0.2;
        }

        val = Math.max(min, Math.min(max, val));
      }
    }

    return val;
  }

  // ── Render ────────────────────────────────────────────────────

  _render() {
    const gl = this.gl;

    gl.viewport(0, 0, this.width, this.height);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);

    if (!this.baseTexture || !this.depthTexture) return;

    gl.useProgram(this.program);

    // Bind textures
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.baseTexture);
    gl.uniform1i(this.uniforms.uBaseTex, 0);

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.depthTexture);
    gl.uniform1i(this.uniforms.uDepthTex, 1);

    // Set global uniforms
    gl.uniform1f(this.uniforms.uTime, this.time);
    gl.uniform1f(this.uniforms.uAmbient, this.ambient);
    gl.uniform2f(this.uniforms.uResolution, this.width, this.height);

    // Compute phase values and set light uniforms
    const count = Math.min(this.lights.length, 16);
    gl.uniform1i(this.uniforms.uLightCount, count);

    for (let i = 0; i < count; i++) {
      const light = this.lights[i];
      const phaseVal = this._computePhase(light, this.time);

      // Position (point lights: x, y, depth)
      const x = light.x || 0.5;
      const y = light.y || 0.5;
      const z = light.depth || 0.3; // default depth
      gl.uniform3f(this.uniforms[`uLightPos[${i}]`], x, y, z);

      // Color
      const c = light.color || [1, 1, 1];
      gl.uniform3f(this.uniforms[`uLightColor[${i}]`], c[0], c[1], c[2]);

      // Radius (in pixels)
      gl.uniform1f(this.uniforms[`uLightRadius[${i}]`], light.radius || 150);

      // Intensity
      gl.uniform1f(this.uniforms[`uLightIntensity[${i}]`], light.intensity || 0.3);

      // Type: 0=point, 1=directional, 2=global
      const typeMap = { point: 0, directional: 1, global: 2 };
      gl.uniform1i(this.uniforms[`uLightType[${i}]`], typeMap[light.type] || 0);

      // Direction
      const dir = light.dir || [0, 0];
      gl.uniform2f(this.uniforms[`uLightDir[${i}]`], dir[0], dir[1]);

      // Phase value
      gl.uniform1f(this.uniforms[`uLightPhaseVal[${i}]`], phaseVal);
    }

    // Bind vertex buffer
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
    gl.enableVertexAttribArray(this.attribs.aPosition);
    gl.vertexAttribPointer(this.attribs.aPosition, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(this.attribs.aTexCoord);
    gl.vertexAttribPointer(this.attribs.aTexCoord, 2, gl.FLOAT, false, 16, 8);

    // Draw
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  // ── Animation Loop ────────────────────────────────────────────

  start() {
    if (this.running) return;
    this.running = true;
    this.time = 0;
    this._lastTime = performance.now();

    const loop = (now) => {
      if (!this.running) return;
      const dt = (now - this._lastTime) / 1000;
      this._lastTime = now;
      this.time += dt;

      this._render();
      if (this.onUpdate) this.onUpdate(this.time);

      this.animFrame = requestAnimationFrame(loop);
    };
    this.animFrame = requestAnimationFrame(loop);
  }

  stop() {
    this.running = false;
    if (this.animFrame) {
      cancelAnimationFrame(this.animFrame);
      this.animFrame = null;
    }
  }

  // ── Export ────────────────────────────────────────────────────

  /** Capture current frame as data URL */
  captureFrame() {
    this._render();
    return this.canvas.toDataURL('image/png');
  }

  /** Get current light configs as JSON-serializable array */
  exportLights() {
    return this.lights.map(l => {
      const exported = { ...l };
      // Strip internal fields if any
      delete exported._dirty;
      return exported;
    });
  }

  destroy() {
    this.stop();
    const gl = this.gl;
    if (this.baseTexture) gl.deleteTexture(this.baseTexture);
    if (this.depthTexture) gl.deleteTexture(this.depthTexture);
    if (this.program) gl.deleteProgram(this.program);
    if (this.vbo) gl.deleteBuffer(this.vbo);
  }
}

// Export for use in editor and game
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LightingEngine };
}
