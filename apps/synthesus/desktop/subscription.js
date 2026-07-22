/* =====================================================================
   Subscription / plans surface.

   Self-contained so it can land alongside concurrent edits to script.js.
   Reads /api/plans; renders nothing it has not been told.

   Honesty rules that apply here as everywhere: a number that cannot be read
   renders "unknown", never a plausible guess. Usage is shown BEFORE a limit
   is reached, because a limit discovered by something breaking is a bug, not
   a business model.
   ===================================================================== */

function plansEscape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

function plansAuthHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    try {
        const token = localStorage.getItem('synthesus_token');
        if (token) headers['Authorization'] = 'Bearer ' + token;
    } catch (e) { /* storage unavailable — proceed unauthenticated */ }
    return headers;
}

function plansPrice(cents) {
    if (cents === null || cents === undefined) return { amount: 'Talk to us', period: '' };
    if (cents === 0) return { amount: 'Free', period: 'forever' };
    return { amount: '$' + (cents / 100).toFixed(0), period: '/month' };
}

function plansLimitText(value, unit) {
    if (value === -1) return 'Unlimited';
    if (value === null || value === undefined) return 'unknown';
    return value + (unit ? ' ' + unit : '');
}

function plansRenderCard(plan, currentPlanId) {
    const price = plansPrice(plan.price_monthly_cents);
    const isCurrent = plan.plan_id === currentPlanId;
    const isRecommended = plan.plan_id === 'personal' && !isCurrent;

    let badge = '';
    if (isCurrent) badge = '<span class="plan-badge is-plain">Your plan</span>';
    else if (isRecommended) badge = '<span class="plan-badge">Most popular</span>';

    const highlights = (plan.highlights || []).map(function (h) {
        return '<li>' + plansEscape(h) + '</li>';
    }).join('');

    let cta;
    if (isCurrent) {
        cta = '<button class="ds-btn" disabled>Current plan</button>';
    } else if (plan.price_monthly_cents === null) {
        cta = '<button class="ds-btn" onclick="plansContact()">Contact sales</button>';
    } else if (plan.price_monthly_cents === 0) {
        cta = '<button class="ds-btn" onclick="plansChoose(\'free\')">Switch to Free</button>';
    } else {
        cta = '<button class="ds-btn ds-btn-primary" onclick="plansChoose(\'' +
              plansEscape(plan.plan_id) + '\')">Upgrade</button>';
    }

    return '' +
        '<div class="plan' + (isCurrent ? ' is-current' : '') +
             (isRecommended ? ' is-recommended' : '') + '">' +
            badge +
            '<div class="plan-name">' + plansEscape(plan.name) + '</div>' +
            '<div class="plan-tagline">' + plansEscape(plan.tagline) + '</div>' +
            '<div class="plan-price">' +
                '<span class="plan-price-amount">' + plansEscape(price.amount) + '</span>' +
                '<span class="plan-price-period">' + plansEscape(price.period) + '</span>' +
            '</div>' +
            '<ul class="plan-highlights">' + highlights + '</ul>' +
            '<div class="plan-cta">' + cta + '</div>' +
        '</div>';
}

function plansUsageRow(label, used, limit, unit) {
    const unlimited = limit === -1;
    const known = typeof used === 'number';
    const atLimit = !unlimited && known && used >= limit;
    const pct = (unlimited || !known || !limit) ? 0 : Math.min(100, (used / limit) * 100);
    const value = known
        ? (unlimited ? used + ' — unlimited' : used + ' of ' + plansLimitText(limit, unit))
        : 'unknown';
    return '' +
        '<div>' +
            '<div class="plan-usage-row">' +
                '<span class="plan-usage-label">' + plansEscape(label) + '</span>' +
                '<span class="plan-usage-value' + (atLimit ? ' is-at-limit' : '') + '">' +
                    plansEscape(value) + '</span>' +
            '</div>' +
            (unlimited || !known ? '' :
                '<div class="plan-meter' + (atLimit ? ' is-at-limit' : '') + '">' +
                '<span style="width:' + pct.toFixed(0) + '%"></span></div>') +
        '</div>';
}

async function plansRefresh() {
    const host = document.getElementById('plans-list');
    const usageHost = document.getElementById('plans-usage');
    if (!host) return;
    host.innerHTML = '<div class="ds-skel" style="height:220px"></div>';

    let payload = null;
    try {
        const resp = await fetch('/api/plans', { headers: plansAuthHeaders() });
        if (resp.ok) payload = await resp.json();
    } catch (e) { /* handled below */ }

    if (!payload) {
        host.innerHTML = '<div class="ds-empty">' +
            '<div class="ds-empty-title">Plans unavailable</div>' +
            '<div class="ds-empty-body">The controller could not be reached, so ' +
            'your plan could not be read. Nothing has changed.</div></div>';
        if (usageHost) usageHost.innerHTML = '';
        return;
    }

    const current = payload.current_plan_id || 'free';
    host.innerHTML = (payload.plans || [])
        .map(function (p) { return plansRenderCard(p, current); }).join('');

    if (usageHost) {
        const plan = (payload.plans || []).find(function (p) { return p.plan_id === current; });
        const usage = payload.usage || {};
        if (plan) {
            usageHost.innerHTML =
                '<div class="plan-usage">' +
                    plansUsageRow('Devices', usage.devices, plan.limits.max_devices, 'device') +
                    plansUsageRow('Renders today', usage.renders_today,
                                  plan.limits.max_renders_per_day, 'a day') +
                    plansUsageRow('Characters', usage.characters,
                                  plan.limits.max_characters, '') +
                '</div>' +
                '<div class="plan-note">Limits are shown before you reach them. ' +
                'Your data is never deleted or locked when a plan changes — ' +
                'a subscription buys the right to run, never the right to ' +
                'withhold what your machine recorded.</div>';
        }
    }
}

// Checkout is not wired. Say so rather than pretending.
function plansChoose(planId) {
    if (typeof dsToast === 'function') {
        dsToast('Checkout not connected',
                'Plan "' + planId + '" selected. Billing is not wired up in this build, ' +
                'so nothing has been charged or changed.', 'warn', 7000);
    } else {
        console.log('[plans] selected', planId, '- checkout not wired');
    }
}

function plansContact() {
    if (typeof dsToast === 'function') {
        dsToast('Enterprise', 'Contact routing is not wired up in this build.', 'warn', 6000);
    }
}

function openPlans() {
    if (typeof toggleWindow === 'function') toggleWindow('win-plans');
    const win = document.getElementById('win-plans');
    if (win && win.style.display !== 'none') plansRefresh();
}
