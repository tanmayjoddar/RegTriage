# RegTriage eval results

> NOT YET RUN BY A HUMAN. No eval has been executed: no baseline sims, no
> mutants, no LLM arms. There are no numbers below by design — the table is
> generated from `eval/results.json` by `regtriage eval-report`, and that
> file does not exist yet. Do not fill this in by hand.

When run, this file will contain: upstream pin, baseline green counts,
generated/killed/used mutant counts, the three-arm table (hit@file,
hit@module, hit@line±5, fabricated-citation rates before/after), spend,
and manual-timing comparison.

Known limitations (apply to any future numbers here): mutants are small
syntactic changes, simpler than real protocol-level PCIe bugs, so hit rates
overstate real-world accuracy; real UVM and commercial-simulator logs are
not covered beyond the sample parsers; numbers come from the harness run
only.
