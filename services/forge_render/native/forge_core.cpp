// Native SDF core for the Synthesus forge.
//
// A direct transcription of services/forge_render/engine.py — same algorithm,
// same operation order, double precision throughout, so that output can be
// compared byte-for-byte against the Python engine rather than merely "looking
// the same".
//
// DETERMINISM IS THE LOAD-BEARING PROPERTY. Distributed tiles only composite
// without seams if every node produces identical pixels. Two hazards therefore
// govern how this file must be built:
//
//   * -march=native is FORBIDDEN for this target. It compiles for the build
//     machine's instruction set, so two nodes with different CPUs can produce
//     different results (vectorisation order, FMA contraction) and seam.
//   * -ffp-contract=off is REQUIRED. Fusing a*b+c into an FMA changes the
//     rounding of intermediate results, which is exactly the kind of last-ulp
//     difference that shows up as a visible tile boundary.
//
// Those flags are pinned in the accompanying Makefile and asserted by test.
// If the numbers ever stop matching Python, the correct response is to bump
// ENGINE_VERSION, not to relax the comparison.

#include <cmath>
#include <cstdint>
#include <cstring>
#include <algorithm>

extern "C" {

struct Recipe {
    int mode;
    int iters;
    int blend;
    int hue;
    int glow;
    int palette;
    int cam;
};

static inline double clampd(double v, double lo, double hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

// Python's % on floats is floor-modulo and differs from C's fmod for negative
// operands. The scene functions rely on it, so it is reproduced exactly.
static inline double pymod(double a, double b) {
    double r = std::fmod(a, b);
    if (r != 0.0 && ((r < 0.0) != (b < 0.0))) r += b;
    return r;
}

static inline double sd_sphere(double x, double y, double z, double r) {
    return std::sqrt(x * x + y * y + z * z) - r;
}

static inline double sd_box(double px, double py, double pz,
                            double bx, double by, double bz) {
    double qx = std::fabs(px) - bx;
    double qy = std::fabs(py) - by;
    double qz = std::fabs(pz) - bz;
    double ox = qx > 0.0 ? qx : 0.0;
    double oy = qy > 0.0 ? qy : 0.0;
    double oz = qz > 0.0 ? qz : 0.0;
    double outside = std::sqrt(ox * ox + oy * oy + oz * oz);
    double m = qy > qz ? qy : qz;
    if (qx > m) m = qx;
    double inside = m < 0.0 ? m : 0.0;
    return outside + inside;
}

static inline double op_smooth_union(double a, double b, double k) {
    double h = 0.5 + 0.5 * (b - a) / k;
    if (h < 0.0) h = 0.0;
    else if (h > 1.0) h = 1.0;
    return b * (1 - h) + a * h - k * h * (1.0 - h);
}

static double scene(double px, double py, double pz, const Recipe& rc) {
    if (rc.mode == 1) {
        double qx = pymod(px + 2.0, 4.0) - 2.0;
        double qy = pymod(py + 2.0, 4.0) - 2.0;
        double qz = pymod(pz + 2.0, 4.0) - 2.0;
        double box = sd_box(qx, qy, qz, 1.0, 1.0, 1.0);
        double neg = -sd_sphere(qx, qy, qz, 1.2);
        return neg > box ? neg : box;
    }
    if (rc.mode == 2) {
        double d = sd_box(px, py, pz, 1.0, 1.0, 1.0);
        double s = 1.0;
        int n = rc.iters < 10 ? rc.iters : 10;
        for (int m = 0; m < n; ++m) {
            double ax = pymod(px * s, 2.0) - 1.0;
            double ay = pymod(py * s, 2.0) - 1.0;
            double az = pymod(pz * s, 2.0) - 1.0;
            s *= 3.0;
            double rx = std::fabs(1.0 - 3.0 * std::fabs(ax));
            double ry = std::fabs(1.0 - 3.0 * std::fabs(ay));
            double rz = std::fabs(1.0 - 3.0 * std::fabs(az));
            double da = rx > ry ? rx : ry;
            double db = ry > rz ? ry : rz;
            double dc = rz > rx ? rz : rx;
            double mn = db < dc ? db : dc;
            if (da < mn) mn = da;
            double c = (mn - 1.0) / s;
            if (c > d) d = c;
        }
        return d;
    }
    if (rc.mode == 3) {
        double sc = 2.0 + rc.iters * 0.6;
        double g = std::fabs(std::sin(px * sc) * std::cos(py * sc)
                           + std::sin(py * sc) * std::cos(pz * sc)
                           + std::sin(pz * sc) * std::cos(px * sc)) / sc - 0.03;
        g *= 0.5;
        double sph = sd_sphere(px, py, pz, 1.7);
        return g > sph ? g : sph;
    }
    double box = sd_box(px, py, pz, 1.15, 1.15, 1.15);
    double sph = sd_sphere(px, py, pz, 1.5);
    double solid = box > sph ? box : sph;
    double neg = -sd_sphere(px, py, pz, 0.72);
    if (neg > solid) solid = neg;
    double orbit = sd_sphere(px - 0.0, py, pz - 1.9, 0.55);
    double k = rc.blend / 100.0;
    if (k < 0.001) k = 0.001;
    return op_smooth_union(orbit, solid, k);
}

static void normal_at(double px, double py, double pz, const Recipe& rc,
                      double* nx, double* ny, double* nz) {
    const double e = 0.0012;
    double dx = scene(px + e, py, pz, rc) - scene(px - e, py, pz, rc);
    double dy = scene(px, py + e, pz, rc) - scene(px, py - e, pz, rc);
    double dz = scene(px, py, pz + e, rc) - scene(px, py, pz - e, rc);
    double ln = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (ln == 0.0) ln = 1.0;  // matches Python's `or 1.0`
    *nx = dx / ln; *ny = dy / ln; *nz = dz / ln;
}

static double soft_shadow(double rox, double roy, double roz,
                          double rdx, double rdy, double rdz, const Recipe& rc) {
    double res = 1.0;
    double t = 0.03;
    for (int i = 0; i < 20; ++i) {
        double h = scene(rox + rdx * t, roy + rdy * t, roz + rdz * t, rc);
        if (h < 0.001) return 0.0;
        double c = 9.0 * h / t;
        if (c < res) res = c;
        t += clampd(h, 0.02, 0.3);
        if (t > 7.0) break;
    }
    return clampd(res, 0.0, 1.0);
}

static double hsl_f(double n, double h, double s, double l) {
    double k = pymod(n + h * 12.0, 12.0);
    double lo = l < (1 - l) ? l : (1 - l);
    double a = s * lo;
    double t1 = k - 3.0;
    double t2 = 9.0 - k;
    double inner = t2 < 1.0 ? t2 : 1.0;
    double mx = t1 < inner ? t1 : inner;
    if (mx < -1.0) mx = -1.0;
    return l - a * mx;
}

static void hsl_to_rgb(double h, double s, double l, double* r, double* g, double* b) {
    h = pymod(pymod(h, 360.0) + 360.0, 360.0) / 360.0;
    *r = hsl_f(0.0, h, s, l);
    *g = hsl_f(8.0, h, s, l);
    *b = hsl_f(4.0, h, s, l);
}

static inline uint8_t to_byte(double c) {
    if (!(c > 0.0)) c = 0.0;
    c = std::pow(c, 0.4545);
    return (uint8_t)(clampd(c, 0.0, 1.0) * 255.0 + 0.5);
}

static inline double hash21(int x, int y) {
    uint32_t v = (uint32_t)((int64_t)x * 374761393 + (int64_t)y * 668265263) & 0xFFFFFFFFu;
    v = (uint32_t)(((uint64_t)(v ^ (v >> 13)) * 1274126177ull) & 0xFFFFFFFFull);
    return (double)((v ^ (v >> 16)) & 0xFFFFFFFFu) / 4294967296.0;
}

// Render an absolute rect [x0,x1) x [y0,y1) of a full_w x full_h frame into a
// tight RGB buffer. Every pixel derives from ABSOLUTE coordinates, which is
// what lets a tile agree with the whole frame.
void forge_render_region(const Recipe* rcp, int full_w, int full_h,
                         int x0, int y0, int x1, int y1,
                         int quality, uint8_t* out) {
    const Recipe rc = *rcp;
    double car, cag, cab, cbr, cbg, cbb;
    static const double profiles[4][4] = {
        {0.62, 0.50, 0.50, 0.86},
        {0.78, 0.50, 0.60, 0.88},
        {0.72, 0.38, 0.62, 0.80},
        {0.50, 0.62, 0.35, 0.94},
    };
    int pi = ((rc.palette % 4) + 4) % 4;
    hsl_to_rgb((double)rc.hue, profiles[pi][0], profiles[pi][1], &car, &cag, &cab);
    hsl_to_rgb((double)rc.hue + 12.0, profiles[pi][2], profiles[pi][3], &cbr, &cbg, &cbb);

    const double glow = rc.glow / 100.0;
    const double dist = rc.cam * 0.1;
    const double rox = 0.0, roy = 1.4, roz = dist;

    // Camera basis is independent of the pixel — hoisted out of the loop.
    double flen = std::sqrt(rox * rox + roy * roy + roz * roz);
    double fwx = -rox / flen, fwy = -roy / flen, fwz = -roz / flen;
    double rtx = fwz * 1.0 - fwy * 0.0;
    double rty = fwx * 0.0 - fwz * 0.0;
    double rtz = fwy * 0.0 - fwx * 1.0;
    double rl = std::sqrt(rtx * rtx + rty * rty + rtz * rtz);
    if (rl == 0.0) rl = 1.0;
    rtx /= rl; rty /= rl; rtz /= rl;
    double upx = fwy * rtz - fwz * rty;
    double upy = fwz * rtx - fwx * rtz;
    double upz = fwx * rty - fwy * rtx;

    const int w = x1 - x0;
    for (int py = y0; py < y1; ++py) {
        double v = ((double)full_h - ((double)py * 2.0 + 1.0)) / (double)full_h;
        for (int px = x0; px < x1; ++px) {
            double u = ((double)px * 2.0 + 1.0 - (double)full_w) / (double)full_h;

            double rdx = u * rtx + v * upx + 1.6 * fwx;
            double rdy = u * rty + v * upy + 1.6 * fwy;
            double rdz = u * rtz + v * upz + 1.6 * fwz;
            double dl = std::sqrt(rdx * rdx + rdy * rdy + rdz * rdz);
            if (dl == 0.0) dl = 1.0;
            rdx /= dl; rdy /= dl; rdz /= dl;

            double t = 0.0;
            bool hit = false;
            for (int i = 0; i < quality; ++i) {
                double d = scene(rox + rdx * t, roy + rdy * t, roz + rdz * t, rc);
                if (d < 0.001) { hit = true; break; }
                t += d;
                if (t > 40.0) break;
            }

            double gy = clampd(v * 0.5 + 0.5, 0.0, 1.0);
            double skyr = 0.015 * (1 - gy) + car * 0.10 * gy;
            double skyg = 0.012 * (1 - gy) + cag * 0.10 * gy;
            double skyb = 0.020 * (1 - gy) + cab * 0.10 * gy;
            double halo = glow * 0.06 * std::exp(-2.5 * std::sqrt(u * u + v * v));
            double r = skyr + cbr * halo;
            double g = skyg + cbg * halo;
            double b = skyb + cbb * halo;

            if (hit) {
                double hx = rox + rdx * t, hy = roy + rdy * t, hz = roz + rdz * t;
                double nx, ny, nz;
                normal_at(hx, hy, hz, rc, &nx, &ny, &nz);
                const double ldx = 0.5698, ldy = 0.8288, ldz = 0.3625;
                double dif = clampd(nx * ldx + ny * ldy + nz * ldz, 0.0, 1.0);
                double sh = soft_shadow(hx + nx * 0.01, hy + ny * 0.01, hz + nz * 0.01,
                                        ldx, ldy, ldz, rc);
                double ndv = clampd(-(nx * rdx + ny * rdy + nz * rdz), 0.0, 1.0);
                double fres = (1.0 - ndv) * (1.0 - ndv) * (1.0 - ndv);
                double mixf = 0.35 + 0.5 * dif;
                double baser = car * (1 - mixf) + cbr * mixf;
                double baseg = cag * (1 - mixf) + cbg * mixf;
                double baseb = cab * (1 - mixf) + cbb * mixf;
                double lit = 0.14 + 0.9 * dif * sh;
                r = baser * lit + cbr * fres * (0.6 + glow);
                g = baseg * lit + cbg * fres * (0.6 + glow);
                b = baseb * lit + cbb * fres * (0.6 + glow);
                double haze = clampd(t / 40.0, 0.0, 1.0);
                r = r * (1 - haze) + skyr * haze;
                g = g * (1 - haze) + skyg * haze;
                b = b * (1 - haze) + skyb * haze;
            }

            double vig = 1.0 - 0.30 * (u * u + v * v) * 0.25;
            r *= vig; g *= vig; b *= vig;
            double grain = (hash21(px, py) - 0.5) * 0.035;
            r += grain; g += grain; b += grain;

            size_t idx = ((size_t)(py - y0) * (size_t)w + (size_t)(px - x0)) * 3;
            out[idx] = to_byte(r);
            out[idx + 1] = to_byte(g);
            out[idx + 2] = to_byte(b);
        }
    }
}

// ===========================================================================
// RECIPE v2 — composable scene graph
// ===========================================================================
//
// v1 above selects one of four hardcoded scenes. That ceiling is the reason a
// prompt can only pick a shape and turn knobs. v2 replaces the selection with a
// composition: a flat array of nodes, each a primitive, a transform wrapping one
// child, or a combinator joining two.
//
// v2 IS NATIVE-ONLY BY DESIGN. v1 is mirrored in engine.py and must stay
// byte-identical to it forever; duplicating every new primitive in two
// languages is what made expansion expensive. Nothing above this line changes,
// so existing SF1 codes keep rendering exactly as before. A machine without the
// compiled core refuses a v2 recipe outright rather than serving a different
// picture — the determinism rule that governs v1 tiles governs these too.
//
// The graph is flat and indices only ever point BACKWARD (a child index is
// always < its parent's). That makes cycles unrepresentable rather than merely
// discouraged, so evaluation cannot run away, and a malformed graph from the
// wire is a bounds check rather than a hang.

enum : int {
    // primitives (no children)
    OP_SPHERE = 0, OP_BOX = 1, OP_TORUS = 2, OP_CAPSULE = 3,
    OP_CYLINDER = 4, OP_CONE = 5, OP_OCTAHEDRON = 6, OP_HEXPRISM = 7,
    OP_PLANE = 8,
    // combinators (children a, b)
    OP_UNION = 20, OP_SUBTRACT = 21, OP_INTERSECT = 22,
    OP_SMOOTH_UNION = 23, OP_SMOOTH_SUBTRACT = 24, OP_SMOOTH_INTERSECT = 25,
    // transforms (child a)
    OP_TRANSLATE = 40, OP_SCALE = 41, OP_ROTATE_X = 42, OP_ROTATE_Y = 43,
    OP_ROTATE_Z = 44, OP_TWIST = 45, OP_BEND = 46, OP_MIRROR = 47,
    OP_REPEAT = 48, OP_ROUND = 49, OP_SHELL = 50,
    // fractal fields (no children)
    OP_MENGER = 60, OP_GYROID = 61, OP_MANDELBULB = 62, OP_APOLLONIAN = 63,
};

struct NodeV2 {
    int op;
    int a;        // child index, or -1
    int b;        // second child index, or -1
    double p[6];  // parameters, meaning depends on op
};

struct RecipeV2 {
    int hue;
    int glow;
    int palette;
    int cam;
    int root;     // index of the root node
    int count;    // number of nodes
};

static inline double fractd(double v) { return pymod(v, 1.0); }

static inline double sd_torus(double px, double py, double pz, double R, double r) {
    double q = std::sqrt(px * px + pz * pz) - R;
    return std::sqrt(q * q + py * py) - r;
}

static inline double sd_capsule(double px, double py, double pz, double h, double r) {
    double y = py - clampd(py, -h, h);
    return std::sqrt(px * px + y * y + pz * pz) - r;
}

static inline double sd_cylinder(double px, double py, double pz, double h, double r) {
    double dx = std::sqrt(px * px + pz * pz) - r;
    double dy = std::fabs(py) - h;
    double ox = dx > 0.0 ? dx : 0.0;
    double oy = dy > 0.0 ? dy : 0.0;
    double m = dx > dy ? dx : dy;
    return (m < 0.0 ? m : 0.0) + std::sqrt(ox * ox + oy * oy);
}

static inline double sd_cone(double px, double py, double pz, double h, double r) {
    // Cone from apex at +h to base radius r at -h, capped.
    double q = std::sqrt(px * px + pz * pz);
    double slope = r / (2.0 * h);
    double d1 = q * (2.0 * h) - (h - py) * r;
    d1 /= std::sqrt((2.0 * h) * (2.0 * h) + r * r);
    double d2 = -py - h;
    double mx = d1 > d2 ? d1 : d2;
    (void)slope;
    return mx;
}

static inline double sd_octahedron(double px, double py, double pz, double s) {
    double d = std::fabs(px) + std::fabs(py) + std::fabs(pz) - s;
    return d * 0.57735026918962584;  // 1/sqrt(3)
}

static inline double sd_hexprism(double px, double py, double pz, double h, double r) {
    const double kx = 0.8660254037844386, ky = 0.5;
    double qx = std::fabs(px), qy = std::fabs(py), qz = std::fabs(pz);
    double dot = kx * qx + ky * qz;
    double sub = 2.0 * (dot < 0.0 ? dot : 0.0);
    qx -= sub * kx;
    qz -= sub * ky;
    double lx = qx - clampd(qx, -r * 0.5773502691896258, r * 0.5773502691896258);
    double lz = qz - r;
    double dxy = std::sqrt(lx * lx + lz * lz);
    double sgn = (qz - r) > 0.0 ? 1.0 : -1.0;
    double d1 = dxy * sgn;
    double d2 = qy - h;
    double o1 = d1 > 0.0 ? d1 : 0.0;
    double o2 = d2 > 0.0 ? d2 : 0.0;
    double m = d1 > d2 ? d1 : d2;
    return (m < 0.0 ? m : 0.0) + std::sqrt(o1 * o1 + o2 * o2);
}

static double sd_menger_field(double px, double py, double pz, int iters) {
    double d = sd_box(px, py, pz, 1.0, 1.0, 1.0);
    double s = 1.0;
    int n = iters < 1 ? 1 : (iters > 10 ? 10 : iters);
    for (int m = 0; m < n; ++m) {
        double ax = pymod(px * s, 2.0) - 1.0;
        double ay = pymod(py * s, 2.0) - 1.0;
        double az = pymod(pz * s, 2.0) - 1.0;
        s *= 3.0;
        double rx = std::fabs(1.0 - 3.0 * std::fabs(ax));
        double ry = std::fabs(1.0 - 3.0 * std::fabs(ay));
        double rz = std::fabs(1.0 - 3.0 * std::fabs(az));
        double da = rx > ry ? rx : ry;
        double db = ry > rz ? ry : rz;
        double dc = rz > rx ? rz : rx;
        double mn = db < dc ? db : dc;
        if (da < mn) mn = da;
        double c = (mn - 1.0) / s;
        if (c > d) d = c;
    }
    return d;
}

static double sd_gyroid_field(double px, double py, double pz, double sc, double thick) {
    if (sc < 0.05) sc = 0.05;
    double g = std::fabs(
        std::sin(px * sc) * std::cos(py * sc)
        + std::sin(py * sc) * std::cos(pz * sc)
        + std::sin(pz * sc) * std::cos(px * sc)
    ) / sc - thick;
    return g * 0.5;
}

static double sd_mandelbulb(double px, double py, double pz, int iters, double power) {
    double zx = px, zy = py, zz = pz;
    double dr = 1.0, r = 0.0;
    int n = iters < 1 ? 1 : (iters > 12 ? 12 : iters);
    for (int i = 0; i < n; ++i) {
        r = std::sqrt(zx * zx + zy * zy + zz * zz);
        if (r > 2.0) break;
        if (r < 1e-9) break;
        double theta = std::acos(clampd(zz / r, -1.0, 1.0));
        double phi = std::atan2(zy, zx);
        dr = std::pow(r, power - 1.0) * power * dr + 1.0;
        double zr = std::pow(r, power);
        theta *= power;
        phi *= power;
        double st = std::sin(theta);
        zx = zr * st * std::cos(phi) + px;
        zy = zr * st * std::sin(phi) + py;
        zz = zr * std::cos(theta) + pz;
    }
    if (r < 1e-9) r = 1e-9;
    if (dr < 1e-9) dr = 1e-9;
    return 0.5 * std::log(r) * r / dr;
}

static double sd_apollonian(double px, double py, double pz, int iters, double s) {
    double x = px, y = py, z = pz;
    double scale = 1.0;
    int n = iters < 1 ? 1 : (iters > 12 ? 12 : iters);
    for (int i = 0; i < n; ++i) {
        x = -1.0 + 2.0 * fractd(0.5 * x + 0.5);
        y = -1.0 + 2.0 * fractd(0.5 * y + 0.5);
        z = -1.0 + 2.0 * fractd(0.5 * z + 0.5);
        double r2 = x * x + y * y + z * z;
        if (r2 < 1e-9) r2 = 1e-9;
        double k = s / r2;
        x *= k; y *= k; z *= k;
        scale *= k;
    }
    if (std::fabs(scale) < 1e-9) scale = scale < 0.0 ? -1e-9 : 1e-9;
    return 0.25 * std::fabs(y) / scale;
}

// Evaluate node `idx` at point (px,py,pz). Child indices are strictly less than
// the parent's, so this terminates without a depth counter; the bounds check is
// what makes a hostile or truncated graph safe rather than undefined.
static double sdf_v2(const NodeV2* g, int count, int idx,
                     double px, double py, double pz) {
    if (idx < 0 || idx >= count) return 1e9;
    const NodeV2& nd = g[idx];
    const double* p = nd.p;
    switch (nd.op) {
        case OP_SPHERE:      return sd_sphere(px, py, pz, p[0]);
        case OP_BOX:         return sd_box(px, py, pz, p[0], p[1], p[2]);
        case OP_TORUS:       return sd_torus(px, py, pz, p[0], p[1]);
        case OP_CAPSULE:     return sd_capsule(px, py, pz, p[0], p[1]);
        case OP_CYLINDER:    return sd_cylinder(px, py, pz, p[0], p[1]);
        case OP_CONE:        return sd_cone(px, py, pz, p[0], p[1]);
        case OP_OCTAHEDRON:  return sd_octahedron(px, py, pz, p[0]);
        case OP_HEXPRISM:    return sd_hexprism(px, py, pz, p[0], p[1]);
        case OP_PLANE:       return py - p[0];
        case OP_MENGER:      return sd_menger_field(px, py, pz, (int)p[0]);
        case OP_GYROID:      return sd_gyroid_field(px, py, pz, p[0], p[1]);
        case OP_MANDELBULB:  return sd_mandelbulb(px, py, pz, (int)p[0], p[1]);
        case OP_APOLLONIAN:  return sd_apollonian(px, py, pz, (int)p[0], p[1]);

        case OP_UNION: {
            double a = sdf_v2(g, count, nd.a, px, py, pz);
            double b = sdf_v2(g, count, nd.b, px, py, pz);
            return a < b ? a : b;
        }
        case OP_SUBTRACT: {
            double a = sdf_v2(g, count, nd.a, px, py, pz);
            double b = -sdf_v2(g, count, nd.b, px, py, pz);
            return a > b ? a : b;
        }
        case OP_INTERSECT: {
            double a = sdf_v2(g, count, nd.a, px, py, pz);
            double b = sdf_v2(g, count, nd.b, px, py, pz);
            return a > b ? a : b;
        }
        case OP_SMOOTH_UNION: {
            double a = sdf_v2(g, count, nd.a, px, py, pz);
            double b = sdf_v2(g, count, nd.b, px, py, pz);
            double k = p[0] > 0.001 ? p[0] : 0.001;
            return op_smooth_union(a, b, k);
        }
        case OP_SMOOTH_SUBTRACT: {
            double a = sdf_v2(g, count, nd.a, px, py, pz);
            double b = sdf_v2(g, count, nd.b, px, py, pz);
            double k = p[0] > 0.001 ? p[0] : 0.001;
            return -op_smooth_union(-a, b, k);
        }
        case OP_SMOOTH_INTERSECT: {
            double a = sdf_v2(g, count, nd.a, px, py, pz);
            double b = sdf_v2(g, count, nd.b, px, py, pz);
            double k = p[0] > 0.001 ? p[0] : 0.001;
            return -op_smooth_union(-a, -b, k);
        }

        case OP_TRANSLATE:
            return sdf_v2(g, count, nd.a, px - p[0], py - p[1], pz - p[2]);
        case OP_SCALE: {
            double s = std::fabs(p[0]) < 1e-6 ? 1e-6 : p[0];
            return sdf_v2(g, count, nd.a, px / s, py / s, pz / s) * s;
        }
        case OP_ROTATE_X: {
            double c = std::cos(p[0]), sn = std::sin(p[0]);
            return sdf_v2(g, count, nd.a, px, c * py + sn * pz, -sn * py + c * pz);
        }
        case OP_ROTATE_Y: {
            double c = std::cos(p[0]), sn = std::sin(p[0]);
            return sdf_v2(g, count, nd.a, c * px - sn * pz, py, sn * px + c * pz);
        }
        case OP_ROTATE_Z: {
            double c = std::cos(p[0]), sn = std::sin(p[0]);
            return sdf_v2(g, count, nd.a, c * px + sn * py, -sn * px + c * py, pz);
        }
        case OP_TWIST: {
            double ang = p[0] * py;
            double c = std::cos(ang), sn = std::sin(ang);
            return sdf_v2(g, count, nd.a, c * px - sn * pz, py, sn * px + c * pz);
        }
        case OP_BEND: {
            double ang = p[0] * px;
            double c = std::cos(ang), sn = std::sin(ang);
            return sdf_v2(g, count, nd.a, c * px - sn * py, sn * px + c * py, pz);
        }
        case OP_MIRROR: {
            double mx = p[0] != 0.0 ? std::fabs(px) : px;
            double my = p[1] != 0.0 ? std::fabs(py) : py;
            double mz = p[2] != 0.0 ? std::fabs(pz) : pz;
            return sdf_v2(g, count, nd.a, mx, my, mz);
        }
        case OP_REPEAT: {
            // A zero period on an axis leaves that axis untouched, so a graph can
            // tile in one or two dimensions without a separate operator.
            double qx = px, qy = py, qz = pz;
            if (p[0] > 1e-6) qx = pymod(px + 0.5 * p[0], p[0]) - 0.5 * p[0];
            if (p[1] > 1e-6) qy = pymod(py + 0.5 * p[1], p[1]) - 0.5 * p[1];
            if (p[2] > 1e-6) qz = pymod(pz + 0.5 * p[2], p[2]) - 0.5 * p[2];
            return sdf_v2(g, count, nd.a, qx, qy, qz);
        }
        case OP_ROUND:
            return sdf_v2(g, count, nd.a, px, py, pz) - p[0];
        case OP_SHELL:
            return std::fabs(sdf_v2(g, count, nd.a, px, py, pz)) - p[0];
    }
    return 1e9;
}

static void normal_at_v2(const NodeV2* g, int count, int root,
                         double px, double py, double pz,
                         double* nx, double* ny, double* nz) {
    const double e = 0.0012;
    double dx = sdf_v2(g, count, root, px + e, py, pz) - sdf_v2(g, count, root, px - e, py, pz);
    double dy = sdf_v2(g, count, root, px, py + e, pz) - sdf_v2(g, count, root, px, py - e, pz);
    double dz = sdf_v2(g, count, root, px, py, pz + e) - sdf_v2(g, count, root, px, py, pz - e);
    double ln = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (ln == 0.0) ln = 1.0;
    *nx = dx / ln; *ny = dy / ln; *nz = dz / ln;
}

static double soft_shadow_v2(const NodeV2* g, int count, int root,
                             double rox, double roy, double roz,
                             double rdx, double rdy, double rdz) {
    double res = 1.0;
    double t = 0.03;
    for (int i = 0; i < 20; ++i) {
        double h = sdf_v2(g, count, root, rox + rdx * t, roy + rdy * t, roz + rdz * t);
        if (h < 0.001) return 0.0;
        double c = 9.0 * h / t;
        if (c < res) res = c;
        t += clampd(h, 0.02, 0.3);
        if (t > 7.0) break;
    }
    return clampd(res, 0.0, 1.0);
}

// Same camera, shading, haze, vignette and grain as v1 — only the distance
// field changes. Keeping the look identical is what lets a v2 graph that
// happens to reproduce a v1 shape also reproduce its image.
void forge_render_region_v2(const NodeV2* graph, const RecipeV2* rcp,
                            int full_w, int full_h,
                            int x0, int y0, int x1, int y1,
                            int quality, uint8_t* out) {
    const RecipeV2 rc = *rcp;
    const int count = rc.count;
    const int root = rc.root;

    double car, cag, cab, cbr, cbg, cbb;
    static const double profiles[4][4] = {
        {0.62, 0.50, 0.50, 0.86},
        {0.78, 0.50, 0.60, 0.88},
        {0.72, 0.38, 0.62, 0.80},
        {0.50, 0.62, 0.35, 0.94},
    };
    int pi = ((rc.palette % 4) + 4) % 4;
    hsl_to_rgb((double)rc.hue, profiles[pi][0], profiles[pi][1], &car, &cag, &cab);
    hsl_to_rgb((double)rc.hue + 12.0, profiles[pi][2], profiles[pi][3], &cbr, &cbg, &cbb);

    const double glow = rc.glow / 100.0;
    const double dist = rc.cam * 0.1;
    const double rox = 0.0, roy = 1.4, roz = dist;

    double flen = std::sqrt(rox * rox + roy * roy + roz * roz);
    double fwx = -rox / flen, fwy = -roy / flen, fwz = -roz / flen;
    double rtx = fwz * 1.0 - fwy * 0.0;
    double rty = fwx * 0.0 - fwz * 0.0;
    double rtz = fwy * 0.0 - fwx * 1.0;
    double rl = std::sqrt(rtx * rtx + rty * rty + rtz * rtz);
    if (rl == 0.0) rl = 1.0;
    rtx /= rl; rty /= rl; rtz /= rl;
    double upx = fwy * rtz - fwz * rty;
    double upy = fwz * rtx - fwx * rtz;
    double upz = fwx * rty - fwy * rtx;

    const int w = x1 - x0;
    for (int py = y0; py < y1; ++py) {
        double v = ((double)full_h - ((double)py * 2.0 + 1.0)) / (double)full_h;
        for (int px = x0; px < x1; ++px) {
            double u = ((double)px * 2.0 + 1.0 - (double)full_w) / (double)full_h;

            double rdx = u * rtx + v * upx + 1.6 * fwx;
            double rdy = u * rty + v * upy + 1.6 * fwy;
            double rdz = u * rtz + v * upz + 1.6 * fwz;
            double dl = std::sqrt(rdx * rdx + rdy * rdy + rdz * rdz);
            if (dl == 0.0) dl = 1.0;
            rdx /= dl; rdy /= dl; rdz /= dl;

            double t = 0.0;
            bool hit = false;
            for (int i = 0; i < quality; ++i) {
                double d = sdf_v2(graph, count, root,
                                  rox + rdx * t, roy + rdy * t, roz + rdz * t);
                if (d < 0.001) { hit = true; break; }
                t += d;
                if (t > 40.0) break;
            }

            double gy = clampd(v * 0.5 + 0.5, 0.0, 1.0);
            double skyr = 0.015 * (1 - gy) + car * 0.10 * gy;
            double skyg = 0.012 * (1 - gy) + cag * 0.10 * gy;
            double skyb = 0.020 * (1 - gy) + cab * 0.10 * gy;
            double halo = glow * 0.06 * std::exp(-2.5 * std::sqrt(u * u + v * v));
            double r = skyr + cbr * halo;
            double g = skyg + cbg * halo;
            double b = skyb + cbb * halo;

            if (hit) {
                double hx = rox + rdx * t, hy = roy + rdy * t, hz = roz + rdz * t;
                double nx, ny, nz;
                normal_at_v2(graph, count, root, hx, hy, hz, &nx, &ny, &nz);
                const double ldx = 0.5698, ldy = 0.8288, ldz = 0.3625;
                double dif = clampd(nx * ldx + ny * ldy + nz * ldz, 0.0, 1.0);
                double sh = soft_shadow_v2(graph, count, root,
                                           hx + nx * 0.01, hy + ny * 0.01, hz + nz * 0.01,
                                           ldx, ldy, ldz);
                double ndv = clampd(-(nx * rdx + ny * rdy + nz * rdz), 0.0, 1.0);
                double fres = (1.0 - ndv) * (1.0 - ndv) * (1.0 - ndv);
                double mixf = 0.35 + 0.5 * dif;
                double baser = car * (1 - mixf) + cbr * mixf;
                double baseg = cag * (1 - mixf) + cbg * mixf;
                double baseb = cab * (1 - mixf) + cbb * mixf;
                double lit = 0.14 + 0.9 * dif * sh;
                r = baser * lit + cbr * fres * (0.6 + glow);
                g = baseg * lit + cbg * fres * (0.6 + glow);
                b = baseb * lit + cbb * fres * (0.6 + glow);
                double haze = clampd(t / 40.0, 0.0, 1.0);
                r = r * (1 - haze) + skyr * haze;
                g = g * (1 - haze) + skyg * haze;
                b = b * (1 - haze) + skyb * haze;
            }

            double vig = 1.0 - 0.30 * (u * u + v * v) * 0.25;
            r *= vig; g *= vig; b *= vig;
            double grain = (hash21(px, py) - 0.5) * 0.035;
            r += grain; g += grain; b += grain;

            size_t idx = ((size_t)(py - y0) * (size_t)w + (size_t)(px - x0)) * 3;
            out[idx] = to_byte(r);
            out[idx + 1] = to_byte(g);
            out[idx + 2] = to_byte(b);
        }
    }
}

}  // extern "C"
