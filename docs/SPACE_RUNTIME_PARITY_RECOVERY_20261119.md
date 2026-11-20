# Second Brain Space runtime parity and recovery — 2026-11-19

Status: DEPLOYMENT DRIFT / RELEASE HOLD.
No automatic Hub writes or production deploys from this repository change.

## Source authority and observed cause

Canonical source: szl-holdings/szl-second-brain commit
73e8e4388268d092c50eac849d2a6f22a18418f2.
Live HF Space: SZLHOLDINGS/szl-second-brain revision
8baec29ec65260a0438ca4f57c140e4209ad73e4, provider RUNNING.

The deployed Space Dockerfile Git blob c7f746117b146e875047c05d0bdc3940f1c0ea82
runs uvicorn app:app. Its app.py Git blob 34471bca490d37765f0e743ecd87d9c8fe690549
is a limited static server exposing /healthz, /api/status, /api/corpus/stats,
then a static-files root mount.

Canonical GitHub Dockerfile blob 3e5df3feee2aac733ef7457e1f80005301eaf828
runs uvicorn app_refinement:app; that module aliases second_brain.web:app.
GitHub app.py is itself a compatibility alias (blob
4b7304dc9d2533b33c6580dd34d276680fbe5835).

Changing only the Docker command is NOT a correct fix because the live Space
also lacks the required current application modules and data contract.

## Exact observed deployment parity

Of the 51 required files from the canonical explicit publish manifest:

- 34 source blobs match the live Hub tree.
- 9 differ: Dockerfile, README.md, app.py, second_brain/console.py,
  second_brain/frontier.py, second_brain/hybrid.py,
  second_brain/routes_operational.py, second_brain/web.py, static/index.html.
- 8 required files are absent: data/lutar-locked-claims.source.v1.json,
  second_brain/admission.py, second_brain/evidence_adapters.py,
  second_brain/evidence_console.py, second_brain/evidence_graph.py,
  second_brain/lineage_console.py, second_brain/lutar_lineage.py,
  second_brain/lutar_reference.py.
- 4 remote paths are additional to the manifest: .gitattributes,
  assets/szl-holo3d.css, assets/szl-holo3d.js,
  receipts/holo3d-v1-20261115.json.
  Do not delete retained receipts or assets without source-owner review.

The read-only verifier:

    python tools/check_live_space_parity.py \
      --source-root /exact/clean/szl-second-brain \
      --expected-commit 73e8e4388268d092c50eac849d2a6f22a18418f2 \
      --out /private/new-unique-source-parity.json

This performs a bounded public Hub API metadata/tree read at one immutable
Space SHA, independently reads its SHA again, validates the local Git tracked
index and COPY-closure, and compares committed Git object identities.
It rejects moving source/Space and reports missing, changed and extra paths.
SHA-1 Git blob identity is content identity; it is not a digital signature.
No credentials, model weights, private graph or provider writes are used.

## Source-staging evidence

BETTERWITHAGE exact clean source clone staged 51 files using the existing
check_space_payload.py --stage command. A dedicated Python 3.12.10 venv
installed the existing requirements and tested app_refinement.app, identical
to second_brain.web.app. Seven local ASGI TestClient GETs returned HTTP 200:
/, /health, /readyz, /api/v1/index, /api/v1/query?q=khipu,
/api/v1/retrieval-capabilities, /api/v1/lutar-invariants.
The local public index reported 575 chunks and handles-only retrieval with
execution_authority NONE. These results are from LOCAL STAGED SOURCE,
not the deployed provider.

Docker Desktop's Linux daemon was unavailable on this workstation, so
there is no fresh local image-level execution proof. The live Hub Space
still returned 404 on its documented API routes.

## Authorized release sequence

1. Verify protected main and current Hub SHA again; coordinate exclusive
   deploy ownership with other operators and preserve old receipts.
2. Obtain separately recorded source-owner approval for a provider release.
   The current publishing/space-payload.manifest.json explicitly has
   publish: false. Do not flip it silently or create an unreviewed uploader.
3. Stage the source-owned full 51-file payload, never only the Dockerfile,
   and run existing CI container/wheel checks and signed source admission.
   No automatic installer may hydrate private training data.
4. An admitted publisher may upload only after verifying exact Hub parent
   revision, source hash, release identity, rights, signature, and rollback
   readiness. Treat additional remote assets and receipts as separately
   owned; do not delete them as a side effect.
5. Independently verify the new Hub SHA and all required Git blobs, the
   actual GET /health, /readyz, /api/v1/index and /api/v1/query endpoints,
   plus genuine public corpus and review-state readiness.
6. Retain the 575 public handles and the private 9,464-node graph boundary.
   No private graph text may enter model gradients or public status APIs.
7. Verify Hatun at the separately admitted authenticated /mcp/ endpoint,
   not the /wires product page. Require tool listing, Yuyay, valid DSSE
   signer, tenant isolation and Khipu receipt readback before wiring model
   inference routes or bounded learning loops.
8. Admit actual model/base/adapter identity, heldout accuracy, checkpoint,
   budget, energy, GPU capacity, exclusive lease and restore path before
   any paid Salad job or production model promotion.

Nonclaims: no HF deployment, model inference, private graph hydration,
paid compute, signed proof, production repair, automatic model training,
secrets handling, merge, DNS change, or branch protection bypass.
