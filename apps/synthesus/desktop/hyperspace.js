/* Synthesus — Live "Solar System" background
 * A glowing sun with eight orbiting, sun-lit planets (Saturn's rings, Earth's
 * moon, Jupiter's bands), faint orbit paths, a calm twinkling starfield, slow
 * violet/gold nebula, and occasional comets. Pure canvas 2D, CPU-friendly.
 *
 * Exposes window.Hyperspace = { start(), stop() } so the Settings wallpaper
 * picker can turn it on/off.
 */
(function () {
    const canvas = document.getElementById('hyperspace-bg');
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true });

    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    let w, h, base, sunX, sunY;

    function resize() {
        w = canvas.width = Math.floor(window.innerWidth * DPR);
        h = canvas.height = Math.floor(window.innerHeight * DPR);
        canvas.style.width = window.innerWidth + 'px';
        canvas.style.height = window.innerHeight + 'px';
        base = Math.min(w, h);
        sunX = w * 0.28;   // sun off-centre so the centred login panel doesn't sit on it
        sunY = h * 0.34;
        seedStars();
    }

    // --- Twinkling starfield ----------------------------------------------
    let stars = [];
    function seedStars() {
        const n = Math.round((w * h) / (8000 * DPR));
        stars = [];
        for (let i = 0; i < n; i++) {
            stars.push({
                x: Math.random() * w,
                y: Math.random() * h,
                r: Math.random() * 1.1 * DPR + 0.25,
                phase: Math.random() * Math.PI * 2,
                speed: 0.008 + Math.random() * 0.03,
                tint: Math.random() < 0.12 ? (Math.random() < 0.5 ? '#c9b6ff' : '#ffe9a8') : '#e6efff'
            });
        }
    }

    // --- Drifting nebula (violet + gold forward) --------------------------
    const nebula = [
        { x: 0.26, y: 0.30, hue: '167, 139, 250', rad: 0.62, amp: 0.040 },
        { x: 0.74, y: 0.28, hue: '192, 132, 252', rad: 0.50, amp: 0.030 },
        { x: 0.52, y: 0.78, hue: '250, 204, 21', rad: 0.46, amp: 0.026 },
        { x: 0.80, y: 0.66, hue: '56, 189, 248', rad: 0.42, amp: 0.012 }
    ];

    // --- Planets ----------------------------------------------------------
    // dist = orbit radius as fraction of the smaller screen dimension.
    // r    = body radius in CSS px (scaled by DPR).  spd = radians/frame.
    const planets = [
        { name: 'Mercury', dist: 0.10, r: 3.5,  spd: 0.0090, light: '#bdbdbd', dark: '#3a3a3a' },
        { name: 'Venus',   dist: 0.145, r: 6,   spd: 0.0066, light: '#ecca84', dark: '#6b5226' },
        { name: 'Earth',   dist: 0.20, r: 6.6,  spd: 0.0052, light: '#5fa8e8', dark: '#123a5e', moon: true },
        { name: 'Mars',    dist: 0.255, r: 5,   spd: 0.0042, light: '#df6a42', dark: '#4a1d10' },
        { name: 'Jupiter', dist: 0.35, r: 15,   spd: 0.0023, light: '#dcb88e', dark: '#5a4326', bands: true },
        { name: 'Saturn',  dist: 0.44, r: 12.5, spd: 0.0017, light: '#e8d2a2', dark: '#6e5e3a', rings: true },
        { name: 'Uranus',  dist: 0.52, r: 9.5,  spd: 0.0012, light: '#aee9e2', dark: '#2f5a55' },
        { name: 'Neptune', dist: 0.585, r: 9,   spd: 0.0009, light: '#5f7ee8', dark: '#1a2552' }
    ];
    planets.forEach((p, i) => { p.angle = Math.random() * Math.PI * 2; p.moonAngle = i; });

    // --- Comets (rare) ----------------------------------------------------
    let comet = null;
    function maybeComet() {
        if (comet || Math.random() > 0.0035) return;
        const fromLeft = Math.random() < 0.5;
        comet = {
            x: fromLeft ? -40 : w + 40, y: Math.random() * h * 0.5,
            vx: (fromLeft ? 1 : -1) * (6 + Math.random() * 4) * DPR,
            vy: (2 + Math.random() * 2) * DPR, life: 1
        };
    }

    function drawSphere(px, py, r, light, dark) {
        const lr = Math.hypot(sunX - px, sunY - py) || 1;
        const ox = (sunX - px) / lr, oy = (sunY - py) / lr;
        const g = ctx.createRadialGradient(px + ox * r * 0.55, py + oy * r * 0.55, r * 0.12, px, py, r);
        g.addColorStop(0, light);
        g.addColorStop(0.62, light);
        g.addColorStop(1, dark);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawPlanet(p, t) {
        const orbit = p.dist * base;
        const px = sunX + Math.cos(p.angle) * orbit;
        const py = sunY + Math.sin(p.angle) * orbit * 0.92; // slight perspective flattening
        const r = p.r * DPR;

        // Saturn: ring behind the body, body, then ring in front.
        if (p.rings) {
            const rx = r * 2.2, ry = r * 0.7, tilt = -0.5;
            ctx.save();
            ctx.translate(px, py);
            ctx.rotate(tilt);
            ctx.lineWidth = r * 0.55;
            const rg = ctx.createLinearGradient(-rx, 0, rx, 0);
            rg.addColorStop(0, 'rgba(201,178,126,0.05)');
            rg.addColorStop(0.5, 'rgba(229,207,160,0.55)');
            rg.addColorStop(1, 'rgba(201,178,126,0.05)');
            ctx.strokeStyle = rg;
            ctx.beginPath(); ctx.ellipse(0, 0, rx, ry, 0, Math.PI, Math.PI * 2); ctx.stroke(); // back half
            ctx.restore();
        }

        if (p.bands) {
            drawSphere(px, py, r, p.light, p.dark);
            ctx.save();
            ctx.beginPath(); ctx.arc(px, py, r, 0, Math.PI * 2); ctx.clip();
            ctx.globalAlpha = 0.35;
            for (let b = -3; b <= 3; b++) {
                ctx.fillStyle = (b % 2 === 0) ? '#c79a6a' : '#efd3a6';
                ctx.fillRect(px - r, py + b * r * 0.28 - r * 0.09, r * 2, r * 0.18);
            }
            ctx.globalAlpha = 1;
            ctx.restore();
        } else {
            drawSphere(px, py, r, p.light, p.dark);
        }

        if (p.rings) {
            const rx = r * 2.2, ry = r * 0.7, tilt = -0.5;
            ctx.save();
            ctx.translate(px, py);
            ctx.rotate(tilt);
            ctx.lineWidth = r * 0.55;
            const rg = ctx.createLinearGradient(-rx, 0, rx, 0);
            rg.addColorStop(0, 'rgba(201,178,126,0.05)');
            rg.addColorStop(0.5, 'rgba(229,207,160,0.7)');
            rg.addColorStop(1, 'rgba(201,178,126,0.05)');
            ctx.strokeStyle = rg;
            ctx.beginPath(); ctx.ellipse(0, 0, rx, ry, 0, 0, Math.PI); ctx.stroke(); // front half
            ctx.restore();
        }

        if (p.moon) {
            p.moonAngle += 0.04;
            const mx = px + Math.cos(p.moonAngle) * r * 2.4;
            const my = py + Math.sin(p.moonAngle) * r * 2.4 * 0.9;
            drawSphere(mx, my, Math.max(1.4, r * 0.27), '#d7d7d7', '#444');
        }

        p.angle += p.spd;
    }

    function drawSun(t) {
        const r = base * 0.05;
        const pulse = 1 + 0.05 * Math.sin(t * 0.02);
        const glow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, r * 6 * pulse);
        glow.addColorStop(0, 'rgba(255,247,214,0.95)');
        glow.addColorStop(0.12, 'rgba(255,213,128,0.65)');
        glow.addColorStop(0.4, 'rgba(250,170,60,0.18)');
        glow.addColorStop(1, 'rgba(250,170,60,0)');
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(sunX, sunY, r * 6 * pulse, 0, Math.PI * 2); ctx.fill();

        const core = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, r);
        core.addColorStop(0, '#fffdf5');
        core.addColorStop(0.6, '#ffe9a8');
        core.addColorStop(1, '#ffb347');
        ctx.fillStyle = core;
        ctx.beginPath(); ctx.arc(sunX, sunY, r, 0, Math.PI * 2); ctx.fill();
    }

    let t = 0, running = false, looping = false;

    function frame() {
        if (!running) { looping = false; return; }
        looping = true;
        t++;

        ctx.clearRect(0, 0, w, h); // CSS gradient shows through as deep-space base

        // Nebula
        ctx.globalCompositeOperation = 'lighter';
        for (const n of nebula) {
            const a = n.amp * (0.7 + 0.3 * Math.sin(t * 0.004 + n.x * 6));
            const gx = (n.x + 0.03 * Math.sin(t * 0.0009 + n.y * 5)) * w;
            const gy = (n.y + 0.03 * Math.cos(t * 0.0011 + n.x * 5)) * h;
            const rr = n.rad * Math.max(w, h);
            const g = ctx.createRadialGradient(gx, gy, 0, gx, gy, rr);
            g.addColorStop(0, `rgba(${n.hue}, ${a})`);
            g.addColorStop(1, `rgba(${n.hue}, 0)`);
            ctx.fillStyle = g;
            ctx.fillRect(0, 0, w, h);
        }
        ctx.globalCompositeOperation = 'source-over';

        // Twinkling stars
        for (const s of stars) {
            ctx.globalAlpha = 0.45 + 0.5 * (0.5 + 0.5 * Math.sin(s.phase + t * s.speed));
            ctx.fillStyle = s.tint;
            ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;

        // Faint orbit paths
        ctx.strokeStyle = 'rgba(255,255,255,0.06)';
        ctx.lineWidth = 1;
        for (const p of planets) {
            const orbit = p.dist * base;
            ctx.beginPath(); ctx.ellipse(sunX, sunY, orbit, orbit * 0.92, 0, 0, Math.PI * 2); ctx.stroke();
        }

        drawSun(t);
        for (const p of planets) drawPlanet(p, t);

        // Comet
        maybeComet();
        if (comet) {
            comet.x += comet.vx; comet.y += comet.vy; comet.life -= 0.006;
            const tx = comet.x - comet.vx * 8, ty = comet.y - comet.vy * 8;
            const grad = ctx.createLinearGradient(comet.x, comet.y, tx, ty);
            grad.addColorStop(0, `rgba(255,255,255,${0.9 * comet.life})`);
            grad.addColorStop(0.4, `rgba(207,226,255,${0.5 * comet.life})`);
            grad.addColorStop(1, 'rgba(207,226,255,0)');
            ctx.strokeStyle = grad; ctx.lineWidth = 2.2 * DPR;
            ctx.beginPath(); ctx.moveTo(comet.x, comet.y); ctx.lineTo(tx, ty); ctx.stroke();
            if (comet.life <= 0 || comet.x < -80 || comet.x > w + 80 || comet.y > h + 80) comet = null;
        }

        requestAnimationFrame(frame);
    }

    function start() {
        canvas.style.display = 'block';
        running = true;
        if (!looping) requestAnimationFrame(frame);
    }
    function stop() {
        running = false;
        canvas.style.display = 'none';
    }

    window.addEventListener('resize', resize);
    resize();
    window.Hyperspace = { start, stop };

    // Auto-start only if the saved wallpaper is the live one (or none chosen yet).
    const saved = localStorage.getItem('synthesus_wallpaper');
    if (!saved || saved === 'solar') start();
})();
