---
name: alma-normalization-rules
description: Create, validate, explain and fix Ex Libris Alma MARC normalization rules (the Drools-style `rule "..." when ... then ... end` syntax used in the Alma Metadata Editor for MARC 21, UNIMARC and CNMARC records). Use when someone asks to write an Alma normalization rule, norm rule or Drools rule for bibliographic, holdings or authority records; to check or debug a rule that fails to save, gives an "Invalid escape sequence" error or does not change the record as expected; or to translate a cataloging task ("remove 650 with 2nd indicator 7", "move text after the slash in 245 a to b") into a rule. Not for XSL normalization rules or Dublin Core / MODS records.
---

# Alma Normalization Rules

Alma normalization rules change MARC records (Metadata Editor > Rules > Normalization,
or via MarcDroolNormalization jobs). This skill has three modes: **create**, **validate**
and **fix**. All three end with the validator below, so never hand back a rule that has
not passed it.

Files in this skill:

- `references/alma_normalization_rules.ebnf`: the formal grammar (source of truth for syntax).
- `references/syntax.md`: every action and condition with its exact format, semantics and the
  documented gotchas (escaping, periods, priority, if clauses). Read it before writing a rule.
- `references/patterns.md`: idioms for tasks that have no single action (move text between
  subfields, temporary fields, marking fields, multi-step rules with priority).
- `scripts/validate_rules.py`: validator and mechanical fixer (Python 3, no dependencies).

## Validator

```bash
python3 <skill>/scripts/validate_rules.py rules.txt            # report
python3 <skill>/scripts/validate_rules.py - < rules.txt        # from stdin
python3 <skill>/scripts/validate_rules.py rules.txt --json     # machine readable
python3 <skill>/scripts/validate_rules.py rules.txt --fix      # print mechanically fixed rules
python3 <skill>/scripts/validate_rules.py rules.txt --fix --in-place
```

Exit status 0 means no errors (warnings may remain), 1 means errors. Each issue has a
severity, a code, line:column, an optional hint and whether `--fix` can repair it.

- **error**: Alma will reject the rule or the syntax is wrong. Must be fixed.
- **warning**: valid syntax but likely wrong behaviour (period not escaped, if clause on a
  different field, two rules on the same field without distinct priorities, removed 008...).
  Fix it or explain to the user why it is intended.
- **info**: worth knowing (OR in `when` may fire the rule more than once, undocumented action).

The validator checks syntax and documented rules. It cannot know the user's records,
so it cannot prove the rule does what they want. Say so when it matters.

## Mode 1: create a rule

1. Pin down the task: which fields/subfields/indicators, which records (the `when`), what
   should happen when the target is missing or occurs more than once. Ask only when the
   answer changes the rule; otherwise state the assumption.
2. Read `references/syntax.md`. If no single action does the job, read `references/patterns.md`.
3. Decide **where each condition goes**:
   - `when` tests the whole record and decides whether the rule runs at all.
   - `if (...)` after an action is tested per field and must test the **same field** the
     action changes. Use `when (TRUE)` plus per-action `if` for "remove every 650 that has X".
4. Write the rule using the template, one action per line:

   ```
   rule "short description of what it does"
   priority 10
   when
   (exists "245.a")
   then
   suffix "245.a" with " :" if (not exists "245.a.*:")
   end
   ```

   - `when` alone on its line, condition on the next line.
   - Omit `priority` for a single rule; when several rules touch the same field, give each a
     distinct priority (higher runs first) and name them in execution order.
   - Unique rule names, no `$$`, no backslash in names.
   - Escape a literal period at the end of a value as `\\\\.` (best practice: every literal period).
5. Save the rule to a file and run the validator. Fix every error and every warning you
   cannot justify, then re-run until clean.
6. Answer with: the rule in a fenced code block, a two or three line explanation of what it
   does in record terms, any assumptions, and a short before/after example of a field when
   that helps. Suggest testing it in the Metadata Editor with Preview on a sample record
   (F6 split editor > Rules > right-click > Edit > Preview) before running it as a job.

## Mode 2: validate a rule

1. Write the user's rule to a temporary file exactly as given (keep their quotes, they may be
   typographic quotes from a copy/paste, which is itself a finding).
2. Run the validator. Then review what it cannot see, using `references/syntax.md`:
   - Does the `when`/`if` split match the intent (record level vs field level)?
   - Does the order of actions/priorities produce the intended result (actions run top to
     bottom inside a rule, rules by priority)?
   - Wildcards: `*` is greedy and cannot start a value; `|` in a value means OR.
   - Would the rule touch fields it should not (e.g. `removeField "650"` without `if`)?
3. Report: a verdict line (valid / valid with warnings / invalid), then each finding with its
   line, what is wrong, why it matters and the corrected line. Do not rewrite the rule unless
   asked; offer the fixed version.

## Mode 3: fix a rule

1. Run `validate_rules.py --fix` to repair the mechanical issues: typographic quotes,
   keyword/action casing (`ReplaceContents` -> `replaceContents`), `&&`/`||`, condition on
   the `when` line, invalid escapes (`\.` `\(` `\\\|`), unescaped trailing periods.
2. Fix the rest by hand: missing `then`/`end`, unknown actions (the hint suggests the closest
   name), wrong element formats (`245$a` -> `245.a`, `20` -> `020`), `if` on another field
   (move the test to `when` or change the tested field), duplicate names, missing priorities,
   `moveSubfieldsToEndOfField` with an `if` (not supported; move the test to `when`).
   If the user said what the rule should do and the rule cannot do it, rewrite it with Mode 1.
3. Re-run the validator until it reports no errors.
4. Answer with the fixed rule and a short list of what changed and why (one line each).

## When the grammar may be out of date

The grammar and validator follow the Ex Libris documentation "Working with Normalization
Rules > Normalization Rule Syntax" and the "Alma Normalization Rule Examples" blog. If a
user shows syntax that Alma accepts but the validator rejects, trust Alma: tell the user,
and update `references/alma_normalization_rules.ebnf`, `references/syntax.md` and the
`ACTIONS` / `CONDITIONS` tables in `scripts/validate_rules.py` together, then run
`python3 tests/test_validate_rules.py`.
