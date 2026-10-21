# Alma normalization rule syntax reference

Condensed from the Ex Libris Knowledge Center page "Working with Normalization Rules >
Normalization Rule Syntax" and the "Alma Normalization Rule Examples" blog. The formal
grammar is `alma_normalization_rules.ebnf` in this folder.

## Rule structure

```
rule "<name>"
[priority <n> | salience <n>]
when
<condition>
then
<action> [if (<condition>)]
<action> ...
end
```

- A file may hold several rules. `priority` and `salience` are synonyms; a higher number
  runs first (2 before 1, 10 before 9). Priority only matters when rules work on the same
  fields; otherwise rules run top to bottom.
- Actions inside a rule run in the order written. Each action works on one field.
- `when` must be the only word on its line; the condition goes on the next line.
- Comments: `#` at the start of a line, or `//` to the end of the line.
- Rule names: unique within the file, at most 255 characters, no backslash (breaks filter
  sets), no `$$`. Do not capitalize the word "rule" in the rule file name.

## Record elements (inside the quotes)

| Form | Example | Meaning |
|---|---|---|
| `<tag>` | `245`, `LDR`, `TMP`, `9*`, `6**` | a field; `*` after the first character is a wildcard; letters make temporary fields |
| `<tag>.{<i1>,<i2>}` | `650.{*,0}` | field with indicators; `*` any, `-` or space empty |
| `<tag>.<code>` | `245.a`, `245.*` | subfield; `*` any subfield |
| `<tag>.{<i1>,<i2>}.<code>` | `245.{1,0}.a` | |
| `<tag>.<code>.<value>` | `035.a.(OCoLC)*` | subfield with value (pattern) |
| `<tag>.{<i1>,<i2>}.<code>.<value>` | `650.{*,7}.2.afset` | |
| `<tag>.{<pos>,<len>}` | `LDR.{17,3}` | control field positions |
| `<tag>.{<pos>,<len>}.<value>` | `008.{35,3}.eng` | |
| UNIMARC/CNMARC 1XX | `100.{*,*}.a.{17,3}.*` | fixed position fields |

Values: `*` matches any string including empty and is greedy (`b*b` on `a b c b d b e`
matches `b c b d b`). `|` separates alternatives: `"900.a.Design|Architecture"`.
A wildcard cannot be the first character of the element. Limited regular expressions work
in `replaceContents` (`"035.a.^0+(.*)"` with `"$1"`) but are not officially supported.

## Conditions

`when` conditions test the whole record; combine with `AND` / `OR` and parentheses.

| Condition | True when |
|---|---|
| `TRUE` | always |
| `exists "<element>"` | at least one data field matches |
| `not exists "<element>"` | no data field matches |
| `existsControl "<element>"` / `not existsControl` | control field (LDR, 001-009) matches / does not |
| `existsMoreThanOnce "<element>"` | more than one match |
| `existsFixedField "<element>"` / `not existsFixedField` | UNIMARC/CNMARC 1XX fixed field |
| `containsScript "<script>" "<tag>"` | the field contains that script (Arabic, Cyrillic, Han, Hebrew, Latin, ... fixed list) |
| `recordHasDuplicateSubfields "<tags>" "<codes>" "<charsToIgnore>"` | indication rules |
| `recordHasDuplicateFields "<tags>"` | indication rules |

`if (...)` after an action is evaluated per field: only fields for which the test is true
are changed, and the tested field must be the field the action works on. Forms:
`action if (exists "...")`, `action if (not exists "...")`, `action if (existsControl "...")`.
`if (exists ...)` cannot select one subfield by value for copy/remove; use XSL for that.

Watch out:
- A `when` with several OR branches that are true together can fire the rule once per true
  branch. Prefer a pipe value (`exists "900.a.A|B"`) or separate rules, or make the actions
  idempotent.
- Keep a `when` under 200 boolean operators.
- Double quotes inside a condition value: enclose the element in single quotes and escape the
  double quote: `(exists '245.{*, }.c.\"')`. Only in conditions.

## Actions

Every action takes an optional `if (...)` unless noted.

### Replace fields and subfields

| Action | Example | Effect |
|---|---|---|
| `changeControlField "<tag>" to "<new tag>"` | `changeControlField "007" to "008"` | retag a control field |
| `changeField "<tag>" to "<new tag>"` | `changeField "245" to "246"` | retag; indicators and subfields unchanged (the field moves to the end of its tag group) |
| `changeSubField "<tag>.<code>" to "<new code>"` | `changeSubField "035.b" to "a"` | all matching subfields |
| `changeSubFieldOnlyFirst` / `changeSubFieldExceptFirst` | `changeSubFieldExceptFirst "050.a" to "b"` | first only / all but first |
| `changeFirstIndicator "<tag>" to "<v>"` / `changeSecondIndicator` | `changeSecondIndicator "856" to "0" if (exists "856.{*,1}")` | set an indicator (`" "` for blank) |
| `combineFields "<tag>" excluding "<codes,csv>"` | `combineFields "852" excluding "a,b"` | merge all `<tag>` fields into the first |

### Add

| Action | Example | Effect |
|---|---|---|
| `addField "<tag>[.{i1,i2}].<code>.<value>"` | `addField "650.{-,0}.a.Feminist theory"` | new field with one subfield |
| `addControlField "<tag>.<value>"` | `addControlField "008.######s2013####xx######r#####000#0#eng#d"` | new control field |
| `addSubField "<tag>[.{i1,i2}].<code>.<value>"` | `addSubField "650.2.GND" if (exists "650.{-,7}.a.Feministin")` | adds to existing field(s); nothing if the field is missing |
| `addSystemNumber "<tag>.<code>" from "<tag>" prefixed by "<tag>"` | `addSystemNumber "035.a" from "001" prefixed by "003"` | `(DAV)9945110100121` |

### Copy

| Action | Example | Effect |
|---|---|---|
| `copyField "<tag>" to "<new tag>"` | `copyField "650" to "TMP" if (exists "650.{ ,0}")` | full copy as a new field |
| `copyField "<tag>.<code>" to "<tag>.<code>"` | `copyField "020.z" to "776.z"` | one subfield into a new field |
| `copyField "<tag>" to "<tag>.{i1,i2}"` | `copyField "300" to "901.{1,2}"` | copy with new indicators |
| `copyControlField "<tag>" to "<tag>"` | `copyControlField "008" to "009"` | used in the Ex Libris examples, not in the syntax table |

copyField always creates a separate field; use `combineFields` to merge.

### Remove

| Action | Example |
|---|---|
| `removeControlField "<tag>"` | `removeControlField "009"` (Alma recreates 008: add it back) |
| `removeField "<tag>"` | `removeField "9*" if (not exists "913.a.*")` |
| `removeSubField "<tag>.<code>"` | `removeSubField "245.h"` |

### Replace text

| Action | Example | Effect |
|---|---|---|
| `replaceControlContents "<tag>.{pos,len}[.<value>]" with "<new>"` | `replaceControlContents "LDR.{7,1}.s" with "m"` | `#` is not a wildcard here |
| `replaceContents "<tag>.<code>.<value>" with "<new>"` | `replaceContents "245.h.[Journal]" with "[Book]"` | only the matching part changes; `*` code = all subfields |
| `replaceContentsOnlyFirst` / `replaceContentsExceptFirst` | | first matching subfield / all but first |
| `replaceSubFieldContents "<tag>.<code>" with "<tag>.<code>"` | `replaceSubFieldContents "245.b" with "100.a"` | |
| `replaceFixedContents "<tag>.{i1,i2}.<code>.{pos,len}.<value>" with "<new>"` | `replaceFixedContents "100.{1,2}.a.{0,8}.20150226" with "20220724"` | UNIMARC/CNMARC 1XX |

### Add text

| Action | Example | New value |
|---|---|---|
| `prefix "<tag>.<code>" with "<text>"` | `prefix "035.b" with "(OCoLC)"` | text + old |
| `suffix "<tag>.<code>" with "<text>"` | `suffix "245.a" with " :" if (not exists "245.a.*:")` | old + text |
| `prefixSubField "<tag>.<code>" with "<tag>.<code>"` | `prefixSubField "910.a" with "906.a"` | other subfield + old |
| `suffixSubField "<tag>.<code>" with "<tag>.<code>"` | `suffixSubField "910.a" with "907.c"` | old + other subfield |

### Agencies (must be enabled by Ex Libris Support)

`addCreatingAgency "040.a"`, `addModifyingAgency "040.d"`, `replaceModifyingAgency "040.d"`.

### Split

`splitSubField "<tag>[.{i1,i2}].<code>.<delimiter>" [to "<tag>[.{i1,i2}].<code>" [addSeq "<code>"]]`

- `splitSubField "866.a.;" to "555.{0,0}.a" addSeq "8"`: one 555 per part, numbered in $8.
- `splitSubField "245.a._separator_"`: without `to`, splits into repeated $a in the same field.

### Duplicates and order

| Action | Example | Note |
|---|---|---|
| `correctDuplicateSubfields "<tags>" "<codes>"` | `correctDuplicateSubfields "610,630" "xyz"` | same code and value, keeps first |
| `correctDuplicateFields "<tags>"` | `correctDuplicateFields "610,630,650"` | |
| `moveSubfieldsToEndOfField "<tag>" "<codes>"` | `moveSubfieldsToEndOfField "650" "92"` | **no `if` clause** |
| `set indication."true"` | | indication rules only |

## Escaping and special characters

Valid escapes: `\b \t \n \f \r \" \' \\` (and `\uXXXX`). Anything else, such as `\z`, `\.`,
`\(` or a lone `\`, fails with "Invalid escape sequence". Fixes: `\.` -> `.` (or `\\\\.`),
`\(` -> `(`, `\\\` -> `\\`, `\\\|` -> `\\|`.

- Literal backslash: `\\`.
- Period as the last character of a value: `\\\\.` (best practice: before every literal
  period): `replaceContents "300.a.1 v \\\\." with "Leaves"`, `addField "907.a.F\\\\.L\\\\.T\\\\."`.
- Pipe as a literal character in a condition: `\\\\|` (`if (exists "866.8.0\\\\|99")`).
- `$$` may not appear anywhere in the rule, not even in the name or a comment-like value.
- Empty indicators are `-` (`650.{-,0}`); a space also works.
- Typographic quotes (“ ” ‘ ’) from copy/paste are not quotes; use straight quotes.

## Scope notes

- Normalization on an Institution Zone record linked to the Network Zone only changes local
  fields; run it from the Network institution to change shared fields.
- Dublin Core / MODS normalization and complex logic use XSL rules, not this syntax.
