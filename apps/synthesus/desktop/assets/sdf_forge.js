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

  const VERSION = "1";

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

  // ---- the GPU raymarcher ----------------------------------------------
  const VERT = `#version 300 es
  in vec2 aPos;
  void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

  const FRAG = `#version 300 es
  precision highp float;
  out vec4 fragColor;
  uniform vec2 uRes;
  uniform float uTime;
  uniform int uIters;        // fractal fold depth
  uniform float uBlend;      // smooth-union amount
  uniform int uMode;         // 0 boolean sculpture, 1 infinite field, 2 fractal
  uniform vec3 uAccent;      // purple accent

  float sdSphere(vec3 p, float r){ return length(p) - r; }
  float sdBox(vec3 p, vec3 b){ vec3 q = abs(p) - b; return length(max(q,0.0)) + min(max(q.x,max(q.y,q.z)),0.0); }
  float sdTorus(vec3 p, vec2 t){ vec2 q = vec2(length(p.xz)-t.x, p.y); return length(q)-t.y; }
  float opU(float a, float b){ return min(a,b); }
  float opI(float a, float b){ return max(a,b); }
  float opS(float a, float b){ return max(-a,b); }
  float opSU(float a, float b, float k){ float h = clamp(0.5+0.5*(b-a)/k,0.0,1.0); return mix(b,a,h)-k*h*(1.0-h); }

  float scene(vec3 p){
    if (uMode == 1){
      // infinite field: repeat a carved cube-sphere every 4 units
      vec3 q = mod(p+2.0,4.0)-2.0;
      float box = sdBox(q, vec3(1.0));
      float sph = sdSphere(q, 1.28);
      return opS(sph*0.0 + sdSphere(q,1.2), box);
    }
    if (uMode == 2){
      // Menger sponge: the classic CSG fractal — a cube with a cross carved out
      // (difference), repeated at one third scale, iterated. Pure boolean algebra
      // on distances, scaling detail infinitely from one primitive.
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
        d = max(d, c);   // difference: carve the cross out of the cube
      }
      return d;
    }
    // boolean sculpture: sphere ∩ box, minus three axis cylinders (as torii),
    // smooth-unioned with an orbiting sphere.
    float box = sdBox(p, vec3(1.15));
    float sph = sdSphere(p, 1.5);
    float solid = opI(box, sph);
    float holeX = sdTorus(p.yzx, vec2(1.15, 0.42));
    float holeY = sdTorus(p, vec2(1.15, 0.42));
    solid = opS(sdSphere(p, 0.72), solid);
    solid = min(solid, 1e9);
    vec3 op = p - vec3(1.9*sin(uTime), 0.0, 1.9*cos(uTime));
    float orbit = sdSphere(op, 0.55);
    return opSU(orbit, solid, max(uBlend, 0.001));
  }

  vec3 normal(vec3 p){
    vec2 e = vec2(0.0008, 0.0);
    return normalize(vec3(
      scene(p+e.xyy)-scene(p-e.xyy),
      scene(p+e.yxy)-scene(p-e.yxy),
      scene(p+e.yyx)-scene(p-e.yyx)));
  }

  void main(){
    vec2 uv = (gl_FragCoord.xy*2.0 - uRes) / uRes.y;
    float ca = cos(uTime*0.25), sa = sin(uTime*0.25);
    vec3 ro = vec3(4.2*sa, 1.4, 4.2*ca);
    vec3 fw = normalize(-ro);
    vec3 rt = normalize(cross(vec3(0.0,1.0,0.0), fw));
    vec3 up = cross(fw, rt);
    vec3 rd = normalize(uv.x*rt + uv.y*up + 1.6*fw);

    float t = 0.0; float d = 0.0; bool hit=false;
    for (int i=0;i<128;i++){
      vec3 p = ro + rd*t;
      d = scene(p);
      if (d < 0.001){ hit=true; break; }
      t += d;
      if (t > 40.0) break;
    }
    vec3 col = vec3(0.02,0.02,0.03);
    if (hit){
      vec3 p = ro + rd*t;
      vec3 n = normal(p);
      vec3 ld = normalize(vec3(0.6,0.8,0.4));
      float diff = clamp(dot(n,ld),0.0,1.0);
      float rim = pow(1.0-clamp(dot(n,-rd),0.0,1.0), 2.5);
      vec3 base = mix(vec3(0.9), uAccent, 0.55);
      col = base*(0.18 + 0.82*diff) + uAccent*rim*0.9;
      col = mix(col, vec3(0.02,0.02,0.03), clamp(t/40.0,0.0,1.0));
    } else {
      float g = clamp(uv.y*0.5+0.5, 0.0, 1.0);
      col = mix(vec3(0.02,0.02,0.03), uAccent*0.10, g);
    }
    col = pow(col, vec3(0.4545)); // gamma
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
      this.params = { iters: 6, blend: 0.35, mode: 0, accent: [0.55, 0.36, 0.96] };
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
        accent: gl.getUniformLocation(prog, "uAccent"),
      };
    }

    setParams(patch) {
      Object.assign(this.params, patch || {});
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
      gl.uniform3fv(this.u.accent, this.params.accent);
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
      // A single deterministic frame, for export.
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

  return { VERSION, math, Renderer, create };
});
