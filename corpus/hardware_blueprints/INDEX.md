# Hardware Blueprints Corpus

Public-source corpus of computational hardware: CPUs, GPUs, NPUs, TPUs, QPUs, FPGAs, memory, storage, motherboards, firmware, and interconnects.

## Composition

| Plane | File pattern | License | Source |
| --- | --- | --- | --- |
| Wikipedia extracts | `entries/<category>.jsonl` | CC-BY-SA-4.0 | en.wikipedia.org via MediaWiki API |
| OpenAlex research papers | `entries/research_paper.jsonl` | OpenAlex metadata CC0; abstracts via inverted-index reconstruction | api.openalex.org |
| Vendor / standards pointers | `entries/datasheet_pointers.jsonl` | URL + metadata only; vendor docs remain on their sites | Intel, AMD, Arm, NVIDIA, JEDEC, PCI-SIG, CXL, NVMe, RISC-V International, OpenTitan, lowRISC |

## Categories

`cpu_x86`, `cpu_arm`, `cpu_riscv`, `cpu_other`, `gpu_discrete`, `gpu_integrated`, `gpu_mobile`, `npu`, `tpu`, `qpu`, `fpga`, `accelerator_other`, `memory_dram`, `memory_hbm`, `memory_cache`, `storage_ssd`, `storage_hdd`, `storage_optical_tape`, `motherboard_form_factor`, `motherboard_chipset`, `firmware_bios_uefi`, `interconnect_pcie`, `interconnect_usb_thunderbolt`, `interconnect_storage_bus`, `interconnect_fabric`, `soc_mobile_tv_embedded`.

## Rebuild

```bash
python -m pipelines.ingest_corpus.wikipedia_fetcher \
  --seeds corpus/hardware_blueprints/seeds/wikipedia_seeds.yaml \
  --out corpus/hardware_blueprints/entries

python -m pipelines.ingest_corpus.papers_fetcher \
  --queries corpus/hardware_blueprints/seeds/openalex_queries.yaml \
  --out corpus/hardware_blueprints/entries/research_paper.jsonl
```

Both fetchers are idempotent: existing entries with the same id are preserved unless `--refresh` is passed.

## Expansion path

- Extend seed YAMLs (`seeds/wikipedia_seeds.yaml`, `seeds/openalex_queries.yaml`)
- Add new datasheet pointer entries to `entries/datasheet_pointers.jsonl` (URL + license metadata; do not vendor PDFs into this repo)
- Add new entry-type fetchers under `pipelines/ingest_corpus/` for additional sources (e.g. WikiChip via their public sitemap, Linux kernel device-tree exports)

## Boundaries

This corpus is intentionally **descriptive, not reproductive**. Vendor microarchitecture, RTL, full datasheets, and proprietary schematics are **not** redistributable and are not vendored here; we only point to their public locations. Open-hardware projects (RISC-V cores, OpenTitan) keep their source upstream — we link, we don't fork.
