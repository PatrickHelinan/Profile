# water-engineering-cases

Two small, checkable engineering tools built around one scenario from my
PhD research: recovering fine CaF₂ precipitates from semiconductor wastewater
by magnetic nanocoagulation, compared with conventional chemical
clarification.

| Case | Question | Live page | Code |
|---|---|---|---|
| A — Hydraulic inventory | How much tank volume per unit flow, and how does it compare with design references? | [case-a](https://linan-he-portfolio.workspace-305642.chatgpt.site/tools/case-a/) | [`case-a-hydraulic-inventory/`](case-a-hydraulic-inventory/) |
| B — Carbon data audit | Per 1000 m³, where do the emissions sit, which factors are verified, and where is the break-even? | [case-b](https://linan-he-portfolio.workspace-305642.chatgpt.site/tools/case-b/) | [`case-b-carbon-audit/`](case-b-carbon-audit/) |

Each case has a Python reference implementation with tests, a single-file
web calculator with an on-load self-check, and a shared file of expected
values or factors that both must reproduce. No client or plant data are
used; manuscript figures come from the published source data of my
first-author papers (under review at JECE and JWPE).

```
pip install -r case-a-hydraulic-inventory/python/requirements.txt
python -m pytest -q case-a-hydraulic-inventory/python case-b-carbon-audit/python
```

Drafted with AI assistance; every formula is written out in the READMEs and
every reported figure is checked against independently recorded values.

MIT licence for the code.
