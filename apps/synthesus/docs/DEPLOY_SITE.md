# Deploying the Synthesus Landing Page

Plain-English guide to getting `site/` live on the internet. Read it once, top to
bottom; the whole thing takes about 10 minutes of clicking plus waiting on DNS.

**Repo:** `Str8biddness/synthesus` (verified via `git remote -v`)

---

## How it works

`.github/workflows/pages.yml` runs on every push to `main` that touches `site/`.
It takes the `site/` directory exactly as-is and publishes it to GitHub Pages.
There is no build step, no Node, no Jekyll — what is in `site/` is what goes live.

You can also trigger a deploy by hand: **Actions → "Deploy site to GitHub Pages"
→ Run workflow**. Useful for re-deploying without making a commit.

---

## 1. One-time GitHub setup (do this first)

The workflow **cannot** deploy until you flip this switch. It is not optional.

1. Go to **https://github.com/Str8biddness/synthesus/settings/pages**
2. Under **Build and deployment**, set **Source** to **GitHub Actions**
   (not "Deploy from a branch").
3. That's it. Save is automatic.

If you skip this, the workflow fails on the "Deploy to GitHub Pages" step with an
error about the Pages site not existing.

---

## 2. Your default URL

Once the workflow has run green, the site is live at:

**https://str8biddness.github.io/synthesus/**

That URL is derived from the owner (`Str8biddness`) and the repo name
(`synthesus`). Note the trailing path — because this is a *project* site rather
than a user site, the page lives under `/synthesus/`, not at the root of
`str8biddness.github.io`.

This URL works forever and is free. You only need the rest of this document if
you want a real domain.

---

## 3. Custom domain

Say you buy `synthesus.ai` (GoDaddy, Namecheap, whoever — the records are the
same everywhere; only the UI differs).

### 3a. DNS records to create at your registrar

These IP addresses are GitHub's official, current Pages IPs, taken from
https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site

**Apex domain** (`synthesus.ai`, no `www`) — four **A** records. Same name, four
different values. Every registrar lets you add four A records with the same host.

| Type | Name / Host | Value            |
|------|-------------|------------------|
| A    | `@`         | `185.199.108.153` |
| A    | `@`         | `185.199.109.153` |
| A    | `@`         | `185.199.110.153` |
| A    | `@`         | `185.199.111.153` |

**Apex domain, IPv6** — four **AAAA** records. Strongly recommended; some mobile
networks are IPv6-only and will not reach you without these.

| Type | Name / Host | Value                 |
|------|-------------|-----------------------|
| AAAA | `@`         | `2606:50c0:8000::153` |
| AAAA | `@`         | `2606:50c0:8001::153` |
| AAAA | `@`         | `2606:50c0:8002::153` |
| AAAA | `@`         | `2606:50c0:8003::153` |

**www subdomain** — one **CNAME** record pointing at your GitHub user, *not* at
your apex domain and *not* at the repo.

| Type  | Name / Host | Value                    |
|-------|-------------|--------------------------|
| CNAME | `www`       | `str8biddness.github.io` |

Notes:
- The trailing dot (`str8biddness.github.io.`) is added automatically by most
  registrars. Either form is fine.
- The value is `str8biddness.github.io` — the **user** domain. Do **not** append
  `/synthesus`. CNAMEs point at hostnames, not paths. GitHub figures out which
  repo to serve from the custom-domain setting in step 3b.
- On GoDaddy, `@` is how you write "the domain itself". Leave TTL at default (1 hour).
- Delete any pre-existing "parked page" / forwarding A records the registrar
  created for you, or they will fight with these.

### 3b. Tell GitHub about the domain

1. **Settings → Pages → Custom domain**
2. Type `synthesus.ai` (or `www.synthesus.ai` — pick one as primary; GitHub
   redirects the other automatically once both DNS records above exist).
3. Click **Save**.

GitHub will then run a DNS check and, when it passes, **automatically commit a
file called `CNAME` into your `site/` directory** containing your domain. That is
correct and expected. Let it do this.

> **Do NOT create or commit a `CNAME` file yourself with a placeholder or
> guessed domain.** A `CNAME` file containing a domain whose DNS does not point
> at GitHub will break the deploy: GitHub will try to serve the site at a domain
> that does not resolve, and your `github.io` URL will start 404ing too. If a bad
> `CNAME` file ever lands in `site/`, delete it, commit, and re-add the domain
> through the Settings UI.

### 3c. Enforce HTTPS

After the DNS check passes, GitHub provisions a free Let's Encrypt certificate.
This can take **up to ~1 hour** — the **Enforce HTTPS** checkbox on the Pages
settings page stays greyed out until the cert is ready.

Once it is clickable: **tick Enforce HTTPS.** This is what makes `http://` visitors
get redirected to `https://`. Do not skip it.

### 3d. How long does DNS take?

- Typically **10 minutes to 1 hour**.
- Officially, up to **48 hours** for full worldwide propagation.
- Check progress from your machine:

  ```bash
  dig +short synthesus.ai            # should list the four 185.199.x.153 IPs
  dig +short AAAA synthesus.ai       # should list the four 2606:50c0:… addresses
  dig +short www.synthesus.ai        # should show str8biddness.github.io
  ```

  Nothing to do but wait until those come back correct. GitHub's Pages settings
  page will show a green check when it agrees.

---

## Troubleshooting

**The workflow is green but I get a 404.**
- Did you set **Source = GitHub Actions** (step 1)? This is the #1 cause.
- Remember the path: a project site lives at `…github.io/synthesus/`, *with* the
  trailing slash. `…github.io/synthesus` (no slash) may 404 on some paths.
- Make sure the file is literally `site/index.html`. GitHub serves `index.html`
  as the directory root; `home.html` or `Index.html` will not work.
- A stale bad `CNAME` file in `site/` will 404 the `github.io` URL. Check for one.

**The workflow didn't run at all.**
It only triggers on pushes to `main` that touch `site/**` or the workflow file
itself. If you changed something else, run it by hand from the Actions tab.

**Workflow fails with a permissions error** (`Resource not accessible by
integration`, or an OIDC/token error on the deploy step):
- Check **Settings → Actions → General → Workflow permissions**. It must not be
  locked down in a way that strips the workflow's declared permissions.
- The workflow already declares what it needs (`pages: write`, `id-token: write`,
  `contents: read`). Do not remove these; `id-token: write` in particular is what
  `deploy-pages` uses to authenticate, and its absence produces a confusing
  "not accessible" error rather than an obvious one.
- If the repo is in an organization with restricted Actions, the `actions/*`
  actions must be allowed.

**DNS is not propagating / GitHub says the domain check failed.**
- Re-run the `dig` commands above. If they return the registrar's parking-page IP,
  you left an old A record in place — delete it.
- If `dig` returns nothing, the records were saved on the wrong host (e.g. `@` vs
  the full domain name). Check your registrar's convention.
- After fixing DNS, go back to Settings → Pages and click **Save** on the custom
  domain again to force a re-check.

**Certificate error / "Not secure" in the browser.**
The cert has not been issued yet. Wait (up to an hour), then tick **Enforce
HTTPS**. If it has been much longer, remove the custom domain, save, re-add it,
and save again — this forces GitHub to re-request the certificate.
