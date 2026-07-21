/* SDF Forge — offline procedural image generation for Synthesus.
 *
 * Constructive Solid Geometry over signed distance fields, rendered by a
 * WebGL2 raymarcher. Every pixel is computed from geometry equations — there
 * is no bitmap, no network, no dependency. This is the honest kind of image
 * generation: the picture is a real evaluation of the scene, not a plausible
 * fabrication. When WebGL2 is not available the module reports "unknown" and
 * renders nothing; it never substitutes a fake frame.
 *
 * CSG is boolean algebra on distances:
 *     union      A ∪ B   = min(a, b)
 *     intersect  A ∩ B   = max(a, b)
 *     subtract   A \ B   = max(-a, b)
 * Scaling to a whole world is domain repetition/folding of those primitives,
 * which is how the same handful of shapes builds anything from a bolt to a
 * planet.
 *
 * The pure-distance math lives in `math` and runs headlessly (node), so the
 * CSG algebra is unit-tested without a GPU. The GPU only ever renders what the
 * math already defines.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.SDFForge = api;
  }
})(typeof self !== "undefined" ? self : typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const VERSION = "2";

  // ---- pure distance math (GPU-independent, unit-tested in node) --------
  const math = {
    length3(x, y, z) {
      return Math.sqrt(x * x + y * y + z * z);
    },
    sdSphere(p, r) {
      return math.length3(p[0], p[1], p[2]) - r;
    },
    sdBox(p, b) {
      const qx = Math.abs(p[0]) - b[0];
      const qy = Math.abs(p[1]) - b[1];
      const qz = Math.abs(p[2]) - b[2];
      const outside = math.length3(Math.max(qx, 0), Math.max(qy, 0), Math.max(qz, 0));
      const inside = Math.min(Math.max(qx, Math.max(qy, qz)), 0);
      return outside + inside;
    },
    sdTorus(p, majorR, minorR) {
      const qx = math.length3(p[0], p[2], 0) - majorR;
      return math.length3(qx, p[1], 0) - minorR;
    },
    opUnion(a, b) {
      return Math.min(a, b);
    },
    opIntersect(a, b) {
      return Math.max(a, b);
    },
    opSubtract(a, b) {
      // b minus a: keep b, carve out a.
      return Math.max(-a, b);
    },
    opSmoothUnion(a, b, k) {
      const h = Math.max(k - Math.abs(a - b), 0.0) / (k || 1e-6);
      return Math.min(a, b) - h * h * k * 0.25;
    },
    // One fold of an infinite lattice: repeat space every `cell` units so a
    // finite primitive tiles a whole world.
    foldRepeat(coord, cell) {
      if (cell <= 0) return coord;
      const half = cell * 0.5;
      return ((((coord + half) % cell) + cell) % cell) - half;
    },
  };

  // ---- deterministic seeding: a short recipe string -> a scene ----------
  // A recipe is human-legible and shareable: "SF1.m.i.b.h.g.p.c".
  const SCENES = ["Boolean sculpture", "Infinite carved field", "Menger sponge", "Gyroid lattice"];
  const PALETTES = ["Amethyst", "Magenta bloom", "Ultraviolet", "Orchid mist"];

  const PRESETS = {
    "Amethyst engine": "SF1.0.6.42.285.60.0.42",
    "Void lattice": "SF1.1.6.20.300.75.2.40",
    "Cathedral sponge": "SF1.2.7.20.278.55.3.44",
    "Nebula gyroid": "SF1.3.5.30.312.90.1.38",
    "Orchid bloom": "SF1.0.6.70.320.100.3.46",
    "Ultraviolet core": "SF1.2.6.15.268.45.2.42",
  };

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashString(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function clampInt(v, lo, hi) {
    v = Math.round(v);
    return v < lo ? lo : v > hi ? hi : v;
  }

  // A free-text seed -> a full recipe (deterministic).
  function recipeFromSeed(seedText) {
    const rng = mulberry32(hashString(String(seedText || "synthesus")));
    const mode = Math.floor(rng() * SCENES.length);
    const iters = clampInt(2 + rng() * 8, 1, 10);
    const blend = clampInt(rng() * 100, 0, 100);
    const hue = clampInt(260 + rng() * 60, 260, 320);
    const glow = clampInt(30 + rng() * 70, 0, 100);
    const palette = Math.floor(rng() * PALETTES.length);
    const cam = clampInt(36 + rng() * 12, 30, 52);
    return { mode, iters, blend, hue, glow, palette, cam };
  }

  function encodeRecipe(r) {
    return ["SF1", r.mode, r.iters, r.blend, r.hue, r.glow, r.palette, r.cam].join(".");
  }

  function decodeRecipe(text) {
    const parts = String(text || "").trim().split(".");
    if (parts[0] !== "SF1" || parts.length < 8) return null;
    const n = parts.slice(1).map((x) => parseInt(x, 10));
    if (n.some((x) => Number.isNaN(x))) return null;
    return {
      mode: clampInt(n[0], 0, SCENES.length - 1),
      iters: clampInt(n[1], 1, 10),
      blend: clampInt(n[2], 0, 100),
      hue: clampInt(n[3], 260, 320),
      glow: clampInt(n[4], 0, 100),
      palette: clampInt(n[5], 0, PALETTES.length - 1),
      cam: clampInt(n[6], 30, 52),
    };
  }

  // Two purple-family colours per palette. Purple is the only accent hue —
  // richness comes from value/saturation and white highlights, never blue.
  function hslToRgb(h, s, l) {
    h = (((h % 360) + 360) % 360) / 360;
    const f = (n) => {
      const k = (n + h * 12) % 12;
      const a = s * Math.min(l, 1 - l);
      return l - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)));
    };
    return [f(0), f(8), f(4)];
  }

  function paletteColours(hue, palette) {
    const profiles = [
      { sA: 0.62, lA: 0.5, sB: 0.5, lB: 0.86 }, // Amethyst
      { sA: 0.78, lA: 0.5, sB: 0.6, lB: 0.88 }, // Magenta bloom
      { sA: 0.72, lA: 0.38, sB: 0.62, lB: 0.8 }, // Ultraviolet
      { sA: 0.5, lA: 0.62, sB: 0.35, lB: 0.94 }, // Orchid mist
    ];
    const p = profiles[palette % profiles.length];
    const colA = hslToRgb(hue, p.sA, p.lA);
    const colB = hslToRgb(hue + 12, p.sB, p.lB);
    return { colA, colB };
  }

  // ---- the GPU raymarcher ----------------------------------------------
  const VERT = `#version 300 es
  in vec2 aPos;
  void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

  const FRAG = `#version 300 es
  precision highp float;
  out vec4 fragColor;
  uniform vec2 uRes;
  uniform float uTime;
  uniform int uIters;
  uniform float uBlend;
  uniform int uMode;
  uniform float uGlow;
  uniform float uCam;
  uniform vec3 uColA;
  uniform vec3 uColB;

  float sdSphere(vec3 p, float r){ return length(p) - r; }
  float sdBox(vec3 p, vec3 b){ vec3 q = abs(p) - b; return length(max(q,0.0)) + min(max(q.x,max(q.y,q.z)),0.0); }
  float sdTorus(vec3 p, vec2 t){ vec2 q = vec2(length(p.xz)-t.x, p.y); return length(q)-t.y; }
  float opU(float a, float b){ return min(a,b); }
  float opI(float a, float b){ return max(a,b); }
  float opS(float a, float b){ return max(-a,b); }
  float opSU(float a, float b, float k){ float h = clamp(0.5+0.5*(b-a)/k,0.0,1.0); return mix(b,a,h)-k*h*(1.0-h); }

  float hash21(vec2 p){ p = fract(p*vec2(123.34, 456.21)); p += dot(p, p+45.32); return fract(p.x*p.y); }

  float scene(vec3 p){
    if (uMode == 1){
      // infinite field: a carved cube-sphere repeated every 4 units
      vec3 q = mod(p+2.0,4.0)-2.0;
      float box = sdBox(q, vec3(1.0));
      return opS(sdSphere(q,1.2), box);
    }
    if (uMode == 2){
      // Menger sponge: cube minus a cross, repeated at 1/3 scale (iterated
      // difference). Pure boolean algebra scaling detail infinitely.
      float d = sdBox(p, vec3(1.0));
      float s = 1.0;
      for (int m=0;m<10;m++){
        if (m>=uIters) break;
        vec3 a = mod(p*s, 2.0) - 1.0;
        s *= 3.0;
        vec3 r = abs(1.0 - 3.0*abs(a));
        float da = max(r.x, r.y);
        float db = max(r.y, r.z);
        float dc = max(r.z, r.x);
        float c = (min(da, min(db, dc)) - 1.0) / s;
        d = max(d, c);
      }
      return d;
    }
    if (uMode == 3){
      // Gyroid: an infinite minimal surface, intersected with a sphere so it
      // reads as a woven orb. Scale rises gently with fractal depth.
      float sc = 2.0 + float(uIters)*0.6;
      vec3 q = p + vec3(0.0, uTime*0.15, 0.0);
      float g = abs(dot(sin(q*sc), cos(q.yzx*sc))) / sc - 0.03;
      g *= 0.5;
      return opI(g, sdSphere(p, 1.7));
    }
    // boolean sculpture: box ∩ sphere, carved by an inner sphere, smooth-unioned
    // with an orbiting sphere.
    float box = sdBox(p, vec3(1.15));
    float sph = sdSphere(p, 1.5);
    float solid = opI(box, sph);
    solid = opS(sdSphere(p, 0.72), solid);
    vec3 op = p - vec3(1.9*sin(uTime), 0.0, 1.9*cos(uTime));
    float orbit = sdSphere(op, 0.55);
    return opSU(orbit, solid, max(uBlend, 0.001));
  }

  vec3 calcNormal(vec3 p){
    vec2 e = vec2(0.0009, 0.0);
    return normalize(vec3(
      scene(p+e.xyy)-scene(p-e.xyy),
      scene(p+e.yxy)-scene(p-e.yxy),
      scene(p+e.yyx)-scene(p-e.yyx)));
  }

  float softShadow(vec3 ro, vec3 rd){
    float res = 1.0; float t = 0.03;
    for (int i=0;i<28;i++){
      float h = scene(ro + rd*t);
      if (h < 0.001) return 0.0;
      res = min(res, 9.0*h/t);
      t += clamp(h, 0.02, 0.28);
      if (t > 7.0) break;
    }
    return clamp(res, 0.0, 1.0);
  }

  float calcAO(vec3 p, vec3 n){
    float occ = 0.0; float sca = 1.0;
    for (int i=0;i<5;i++){
      float hr = 0.012 + 0.12*float(i)/4.0;
      float d = scene(p + n*hr);
      occ += (hr - d)*sca;
      sca *= 0.86;
    }
    return clamp(1.0 - 1.6*occ, 0.0, 1.0);
  }

  void main(){
    vec2 uv = (gl_FragCoord.xy*2.0 - uRes) / uRes.y;
    float ca = cos(uTime*0.25), sa = sin(uTime*0.25);
    float dist = uCam*0.1;
    vec3 ro = vec3(dist*sa, 1.4, dist*ca);
    vec3 fw = normalize(-ro);
    vec3 rt = normalize(cross(vec3(0.0,1.0,0.0), fw));
    vec3 up = cross(fw, rt);
    vec3 rd = normalize(uv.x*rt + uv.y*up + 1.6*fw);

    float t = 0.0; float d = 0.0; bool hit=false; int steps=0;
    for (int i=0;i<160;i++){
      vec3 p = ro + rd*t;
      d = scene(p);
      steps = i;
      if (d < 0.0009){ hit=true; break; }
      t += d;
      if (t > 40.0) break;
    }

    vec3 sky = mix(vec3(0.015,0.012,0.02), uColA*0.10, clamp(uv.y*0.5+0.5,0.0,1.0));
    // a soft central glow so empty space still feels lit, never flat black
    sky += uColB * uGlow * 0.06 * exp(-2.5*length(uv));
    vec3 col = sky;

    if (hit){
      vec3 p = ro + rd*t;
      vec3 n = calcNormal(p);
      vec3 ld = normalize(vec3(0.55, 0.8, 0.35));
      float dif = clamp(dot(n, ld), 0.0, 1.0);
      float sh = softShadow(p + n*0.01, ld);
      float ao = calcAO(p, n);
      float fres = pow(1.0 - clamp(dot(n, -rd), 0.0, 1.0), 3.0);
      vec3 h = normalize(ld - rd);
      float spec = pow(clamp(dot(n, h), 0.0, 1.0), 40.0);

      vec3 base = mix(uColA, uColB, 0.35 + 0.5*dif);
      col = base * (0.14 + 0.9*dif*sh) * ao;
      col += uColB * fres * (0.6 + uGlow);      // fresnel glow, the flavour
      col += vec3(1.0) * spec * 0.5 * sh;       // white highlight
      col = mix(col, sky, clamp(t/40.0, 0.0, 1.0)); // distance haze
    }

    // vignette + subtle film grain for depth (design-guide: grain/noise)
    col *= 1.0 - 0.30*dot(uv, uv)*0.25;
    col += (hash21(gl_FragCoord.xy + fract(uTime)) - 0.5) * 0.035;
    col = pow(max(col, 0.0), vec3(0.4545)); // gamma
    fragColor = vec4(col, 1.0);
  }`;

  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(sh);
      gl.deleteShader(sh);
      throw new Error("shader compile failed: " + log);
    }
    return sh;
  }

  class Renderer {
    constructor(canvas) {
      this.canvas = canvas;
      this.gl = canvas.getContext("webgl2", { preserveDrawingBuffer: true, antialias: false });
      this.available = !!this.gl;
      this.raf = 0;
      this.startedAt = 0;
      this.frames = 0;
      this.fps = null; // null means "unknown", never a fabricated number
      this.params = {
        iters: 6,
        blend: 0.35,
        mode: 0,
        glow: 0.6,
        cam: 42,
        colA: [0.5, 0.34, 0.85],
        colB: [0.86, 0.74, 1.0],
      };
      if (this.available) this._build();
    }

    _build() {
      const gl = this.gl;
      const prog = gl.createProgram();
      gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
      gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        throw new Error("program link failed: " + gl.getProgramInfoLog(prog));
      }
      this.prog = prog;
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, "aPos");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      this.u = {
        res: gl.getUniformLocation(prog, "uRes"),
        time: gl.getUniformLocation(prog, "uTime"),
        iters: gl.getUniformLocation(prog, "uIters"),
        blend: gl.getUniformLocation(prog, "uBlend"),
        mode: gl.getUniformLocation(prog, "uMode"),
        glow: gl.getUniformLocation(prog, "uGlow"),
        cam: gl.getUniformLocation(prog, "uCam"),
        colA: gl.getUniformLocation(prog, "uColA"),
        colB: gl.getUniformLocation(prog, "uColB"),
      };
    }

    setParams(patch) {
      Object.assign(this.params, patch || {});
    }

    // Apply a decoded recipe (numbers) to GPU params, deriving the colours.
    applyRecipe(r) {
      const { colA, colB } = paletteColours(r.hue, r.palette);
      this.setParams({
        mode: r.mode,
        iters: r.iters,
        blend: r.blend / 100,
        glow: r.glow / 100,
        cam: r.cam,
        colA,
        colB,
      });
    }

    drawFrame(timeSeconds) {
      if (!this.available) return false;
      const gl = this.gl;
      gl.viewport(0, 0, this.canvas.width, this.canvas.height);
      gl.useProgram(this.prog);
      gl.uniform2f(this.u.res, this.canvas.width, this.canvas.height);
      gl.uniform1f(this.u.time, timeSeconds);
      gl.uniform1i(this.u.iters, this.params.iters | 0);
      gl.uniform1f(this.u.blend, this.params.blend);
      gl.uniform1i(this.u.mode, this.params.mode | 0);
      gl.uniform1f(this.u.glow, this.params.glow);
      gl.uniform1f(this.u.cam, this.params.cam);
      gl.uniform3fv(this.u.colA, this.params.colA);
      gl.uniform3fv(this.u.colB, this.params.colB);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      return true;
    }

    start() {
      if (!this.available) return false;
      cancelAnimationFrame(this.raf);
      this.startedAt = performance.now();
      this.frames = 0;
      const loop = (now) => {
        const t = (now - this.startedAt) / 1000;
        this.drawFrame(t);
        this.frames += 1;
        if (t > 0.5) this.fps = Math.round(this.frames / t);
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
      return true;
    }

    stop() {
      cancelAnimationFrame(this.raf);
      this.raf = 0;
    }

    renderStill(timeSeconds) {
      return this.drawFrame(timeSeconds || 0);
    }

    toPNG() {
      if (!this.available) return null;
      return this.canvas.toDataURL("image/png");
    }
  }

  function create(canvas) {
    return new Renderer(canvas);
  }

  return {
    VERSION,
    math,
    Renderer,
    create,
    SCENES,
    PALETTES,
    PRESETS,
    recipeFromSeed,
    encodeRecipe,
    decodeRecipe,
    paletteColours,
  };
});
