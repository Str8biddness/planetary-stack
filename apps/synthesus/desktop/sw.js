/* Synthesus Web Desktop — service worker.
 *
 * Purpose: let the desktop launch when it is installed to a phone home screen
 * and the shell has not started yet, or has stopped. It caches the APP SHELL
 * ONLY — markup, styles, scripts, icons.
 *
 * It deliberately does NOT cache anything under /api/. A cached API response
 * is a number that was true at some point in the past and is presented as if
 * it were true now, which is exactly the kind of fabricated state this product
 * refuses to render. When the controller is unreachable the UI must say so;
 * that is the job of the page, not of this file.
 *
 * Secure context: this runs over plain HTTP from loopback on the device
 * itself, which browsers treat as a secure context. Nothing here assumes TLS
 * and nothing here contacts an external origin.
 */

/* Bump CACHE_VERSION whenever a shell asset changes. Old caches are deleted on
   activate, so a stale shell cannot survive an update. */
const CACHE_VERSION = 'synthesus-shell-v1-20260721';

/* The shell. Query strings are the existing cache-busting markers in
   index.html; requests are matched with ignoreSearch so a version bump in the
   markup still finds the cached body until the new one is fetched. */
const SHELL = [
    './',
    'index.html',
    'styles.css',
    'script.js',
    'hyperspace.js',
    'xterm.css',
    'xterm.js',
    'xterm-addon-fit.js',
    'manifest.webmanifest',
    'assets/synthesus-icon.png',
    'assets/synthesus-icon-128.png',
    'assets/synthesus-icon-192.png',
    'assets/synthesus-icon-256.png',
    'assets/synthesus-icon-384.png',
    'assets/synthesus-icon-512.png',
    'assets/synthesus-maskable-192.png',
    'assets/synthesus-maskable-512.png',
];

/* Prefixes that must never be served from, or written to, the cache. */
const NEVER_CACHE = ['/api/', '/ws', '/terminal', '/socket.io'];

function isNeverCached(url) {
    return NEVER_CACHE.some(function (prefix) {
        return url.pathname === prefix || url.pathname.indexOf(prefix) === 0;
    });
}

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE_VERSION).then(function (cache) {
            /* One failing asset must not abort the whole install, or the app
               becomes uninstallable because of a single missing file. */
            return Promise.all(SHELL.map(function (path) {
                return cache.add(new Request(path, { cache: 'reload' })).catch(function () {
                    return undefined;
                });
            }));
        }).then(function () {
            return self.skipWaiting();
        })
    );
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(keys.map(function (key) {
                return key === CACHE_VERSION ? undefined : caches.delete(key);
            }));
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener('fetch', function (event) {
    const request = event.request;
    if (request.method !== 'GET') return;

    let url;
    try {
        url = new URL(request.url);
    } catch (e) {
        return;
    }

    /* Same-origin only. There is no external origin in this product, and if one
       ever appears it must not be silently cached here. */
    if (url.origin !== self.location.origin) return;

    /* Live controller data is never cached and never served from cache. */
    if (isNeverCached(url)) return;

    /* Navigations: try the network so a running shell always wins, and fall
       back to the cached document so the installed app still opens offline. */
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(function () {
                return caches.match('index.html', { ignoreSearch: true }).then(function (hit) {
                    return hit || caches.match('./', { ignoreSearch: true });
                });
            })
        );
        return;
    }

    /* Shell assets: cache first for instant launch, then refresh the entry. */
    event.respondWith(
        caches.match(request, { ignoreSearch: true }).then(function (hit) {
            const network = fetch(request).then(function (response) {
                if (response && response.ok && response.type === 'basic') {
                    const copy = response.clone();
                    caches.open(CACHE_VERSION).then(function (cache) {
                        cache.put(request, copy);
                    });
                }
                return response;
            });
            return hit || network;
        })
    );
});
