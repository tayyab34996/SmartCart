# Benchmark lock (Phase 4)

Locked on 2026-11-25 by `scripts/build_benchmarks.py --lock`, after the annotation review in
[annotation_review.md](annotation_review.md). `build_benchmarks.py --check` and
`tests/unit/test_benchmarks.py` fail if a locked file changes. Test files are evaluated once,
with frozen configurations (Phases 6–11). Changing a locked file requires a new lock and a
note in `docs/progress.md` explaining why.

SHA-256 of the UTF-8 file contents:

| File | SHA-256 | Status |
| --- | --- | --- |
| `data/annotations/nlu.jsonl` | `dc755469f463812a703ecc9e3ec01a6f514a734f541097c8714fa9806f9f2b5c` | locked |
| `data/splits/nlu_split.json` | `e722e2a9c27d30a53bb3ecd8b4f3dc127b7535e98ca0bab5c53fe1afb14afd75` | locked |
| `data/splits/benchmark_groups.json` | `3dd8d89ec28cae438d5cd781956dd043b68b68d171864db90726f20aaa084243` | locked |
| `data/benchmarks/basket_test.json` | `d85e50be4df87d8d9d22ae2f56a1f20a3e13b55918aa811339ec4f68af8efe64` | locked |
| `data/benchmarks/retrieval_test.json` | `ed8c38b9adc0cb3dea02aedbe17a094617e7ac6d7c2dfc9585784bc48c34e50d` | locked |
| `data/benchmarks/basket_dev.json` | `01d792f69b26e3f41164821f15967788a6d0701e16b1b76554443a36d3b7443d` | development (not locked) |
| `data/benchmarks/retrieval_dev.json` | `da2030ed9b4b807378db85ac88ee724de733441ad6a27ab162a838ea1d0a24cd` | development (not locked) |
| `data/annotations/review_sample.jsonl` | `8ae3905af8db1656ecac516af9958a68e7476debb6b39cb641e6ff2134de6562` | development (not locked) |
