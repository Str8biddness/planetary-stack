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

}  // extern "C"
