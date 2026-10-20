# Data-audit verification

Test date: 20 October 2026. Scope: the implemented data-audit stage.

| Check | Outcome |
| --- | --- |
| Existing unit suite | All 6 tests passed. |
| CLI help | Completed successfully. |
| End-to-end CLI with small synthetic ZIP fixtures | Produced the expected JSON summary, CSV shortlist, and Markdown report; known order and recipe counts matched. |
| Missing source file | Exited with an error and did not create success artifacts. |
| Current source ZIPs versus saved manifest | Both SHA-256 hashes, byte sizes, and member inventories matched. |
| Saved transaction checks and aggregates | Primary-ID checks, order references, basket histograms, and evaluation-set totals agreed. |
| Recipe shortlist | 50 distinct recipe IDs; every candidate remains unverified and excluded from optimization. |

No defects were found in these checks. The existing full CSV audit was validated
against unchanged source archives rather than repeating its complete scan.
The synthetic CLI fixtures tested the application boundary independently of the
real-data results. The temporary fixture files were removed after the checks.

These checks do not resolve Food.com's missing units or inconsistent ingredient
lists. They also do not test basket generation, request parsing, or a user
interface, which have not been implemented.

Repeat the unit suite from the repository root:

```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

Next task: verify five meal recipes and create their ingredient mappings and a
covering 20-option product catalog before building the first basket baseline.

## Pilot contract verification

Subsequently added the first three source-checked recipe examples, eleven canonical
ingredients, and twenty simulated product options. Ran the combined suite:
**18 tests passed**, comprising the existing six audit tests and twelve contract tests.

The added checks cover duplicate IDs, unexpected fields, invalid prices and
currencies, simulation provenance, nonpositive/nonfinite quantities, fractional
piece packs, incompatible units, ingredient-specific conversion restrictions,
broken references, invalid dietary states, source-based scaling without accumulated
rounding, source package quantities, invalid serving counts, and CLI rejection of
invalid input. All twelve recipe lines have matching available product options.

The real-seed CLI produced the expected requirements for two pasta servings:
120 g flour, one egg, 7.394 ml oil, and 29.574 ml water. This validates ingredient
normalization; basket selection and budget compliance remain unimplemented.

Independent review of the three recipe examples remains pending. The flour
conversion is a documented reference estimate, and all product attributes are
simulated. Next: implement and check the structured-request basket baseline.

## Student quantity helpers — 21 October 2026

Reviewed the student's `missing_amount()` and `packs_needed()` without modifying
their implementations. Added seven regression tests. The combined suite has
**25 passing tests**.

Verified partial, exact, and excess pantry stock; zero demand; negative input
rejection; nonpositive pack-size rejection; decimal arithmetic; whole-pack
rounding; and the composed example: 600 g required, 200 g in stock, and 250 g
packs results in two packs.

The pack function's error message still says both amounts must be greater than
zero, although zero demand is valid. This is a wording issue; the tested boundary
behavior is correct. Callers must supply finite Decimal quantities in compatible
units, consistent with the validated data contracts.

Next student exercise: calculate line cost in integer currency minor units,
then connect quantities and costs to eligible product options.
