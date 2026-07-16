# Emulation Corpus

Public-source corpus of emulation, virtualization, and hypervisor technology.

## Composition

| Plane | File pattern | License | Source |
| --- | --- | --- | --- |
| Wikipedia extracts | `entries/<category>.jsonl` | CC-BY-SA-4.0 | en.wikipedia.org via MediaWiki API |
| Research papers | `entries/research_paper.jsonl` | OpenAlex CC0 metadata; reconstructed abstracts | api.openalex.org |
| Foundational pointers | `entries/foundational_pointers.jsonl` | URL + metadata only; upstream docs unchanged | QEMU, Linux KVM, Xen, Firecracker, gVisor, Kata, crosvm, Cloud Hypervisor, Bochs, libvirt, MAME, Dolphin, USENIX |

## Categories

`hypervisor_type1`, `hypervisor_type2`, `container_runtime`, `emulator_pc`, `emulator_console`, `emulator_handheld`, `emulator_arcade`, `emulator_mobile`, `emulator_mainframe_retro`, `concept_virtualization`, `concept_translation`, `concept_isolation`, `concept_io_virtualization`, `research_paper`.

## Rebuild

```bash
python -m pipelines.ingest_corpus.wikipedia_fetcher \
  --seeds corpus/emulation/seeds/wikipedia_seeds.yaml \
  --out corpus/emulation/entries

python -m pipelines.ingest_corpus.papers_fetcher \
  --queries corpus/emulation/seeds/arxiv_queries.yaml \
  --out corpus/emulation/entries/research_paper.jsonl
```

## Linking to the Synthesus EmulEngineering subsystem

`synthesus3.0/kernel/emul_engineering/` consumes this corpus through the standard Knowledge Cloud query interface. The expected access pattern is semantic retrieval: queries like "Intel VT-x EPT extended page tables" or "QEMU TCG basic-block cache" should return high-quality grounded entries from both the Wikipedia and research planes.

## Boundaries

We do not vendor proprietary ROMs, BIOS images, or copyrighted firmware blobs. Pointers reference public upstream documentation only. Research-paper entries store abstracts; full PDFs remain at the publisher's URL.
