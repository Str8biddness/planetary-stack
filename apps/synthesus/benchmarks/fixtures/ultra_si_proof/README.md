# Ultra SI proof fixtures

Provenance: private archive `synthesus-ultra-` @ `db72d05` (2026-06-28).

These are **committed run artifacts** from the ancestral SI monorepo — not mocks:

| File | What it shows |
|------|----------------|
| `pipeline_scene.png` | Coarse-to-fine VSA pipeline (pattern graph → HD raster) |
| `grounded_*.png` | Data-grounded colour + shape illustrations |
| `hd_mountain_grass_sky_sun_256.png` | Multi-entity geometric scene |
| `imagined_mountain_grass_sky.png` | Hopfield imagination fill path |
| `larynx_vocal.wav` | Early SI larynx sample (pre-formant multipass stack) |

## Honesty

- These prove **SI construction existed and ran** in Ultra.
- The **live** launch engine is the public `image_service` / formant stack (far beyond these early renders).
- Use as **visual regression baselines** or docs/marketing, not as the production renderer.

## Regenerate (public stack)

```bash
# Modern SI image path (runtime)
curl -s -X POST http://127.0.0.1:5010/api/v1/image \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a mountain and grass under a sky with a sun","resolution":256}' \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin); open('/tmp/si_scene.png','wb').write(base64.b64decode(d['image_base64']))"
```
