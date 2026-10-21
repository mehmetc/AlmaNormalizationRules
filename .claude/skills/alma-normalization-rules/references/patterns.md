# Patterns for tasks without a single action

Each pattern passes `scripts/validate_rules.py`. Adapt tags, codes and values.

## Field-level selection: `when (TRUE)` + `if`

To act on only some occurrences of a repeatable field, test the field itself in `if`.

```
rule "remove 650 with 2nd indicator 7 and $2 fast"
when
(TRUE)
then
removeField "650" if (exists "650.{*,7}.2.fast")
end
```

`when (exists "650.{*,7}.2.fast")` with an unconditional `removeField "650"` would remove
**every** 650 in matching records.

## Move text after a delimiter into another subfield

No action moves part of a subfield. Mark the split point with a placeholder, split, then
recode the second part.

```
rule "move text after the colon in 245 a to 245 b"
when
(exists "245.a.*:*") AND (not exists "245.b")
then
replaceContents "245.a.:" with " :_separator_"
splitSubField "245.a._separator_"
changeSubFieldExceptFirst "245.a" to "b"
end
```

## Several rules on the same field: priorities in order

```
rule "step 1 copy 650 with 2nd indicator 0 to TMP"
priority 30
when
(TRUE)
then
copyField "650" to "TMP" if (exists "650.{*,0}")
end

rule "step 2 set TMP 2nd indicator to 4"
priority 20
when
(exists "TMP")
then
changeSecondIndicator "TMP" to "4"
end

rule "step 3 turn TMP into 690"
priority 10
when
(exists "TMP")
then
changeField "TMP" to "690"
end
```

Temporary fields use letter tags (`TMP`, `YLK`, `ABC`) so they never clash with real data.
Always remove or rename them in the last step.

## Mark, then act (complex field selection)

`if` takes one test. To combine tests on the same field, mark fields with a temporary
subfield, unmark the ones that fail the second test, then act on the mark.

```
rule "remove 6XX with 2nd indicator 7 unless $2 is lcgft or fast"
when
(TRUE)
then
addSubField "6**.Z.mark" if (not exists "6**.2.lcgft|fast")
removeSubField "6**.Z" if (not exists "6**.{*,7}")
removeField "6**" if (exists "6**.Z")
end
```

## Add a field only once

Make the `when` test for the field you are about to add, so re-running the rule (or
normalize-on-save) does not add it again.

```
rule "add 336 text if missing"
when
(not exists "336")
then
addField "336.a.text"
addSubField "336.b.txt"
addSubField "336.2.rdacontent"
end
```

## Add a field with several subfields

`addField` creates one subfield; add the rest with `addSubField` guarded by the new value
so other occurrences of the tag are not touched.

```
rule "add 650 7 Feministin GND"
when
(not exists "650.{-,7}.a.Feministin")
then
addField "650.{-,7}.a.Feministin"
addSubField "650.2.gnd" if (exists "650.{-,7}.a.Feministin")
end
```

## Punctuation only when missing

```
rule "end 500 a with a period"
when
(exists "500.a")
then
suffix "500.a" with "\\\\." if (not exists "500.a.*\\\\.")
end
```

## Work with control field positions

Copy the control field to a temporary control field, blank what you do not need, copy
the rest into a data field, then remove the temporary field.

```
rule "copy 008 language code to 041 a"
when
(not existsControl "009") AND (not exists "041.a")
then
copyControlField "008" to "009"
replaceControlContents "009.{0,35}" with " "
replaceControlContents "009.{4,2}" with " "
copyField "009" to "041.a"
removeControlField "009"
end
```

## Change a control field position

```
rule "set LDR 07 to m when it is s"
when
(existsControl "LDR.{7,1}.s")
then
replaceControlContents "LDR.{7,1}.s" with "m"
end
```

## Insert a field before existing ones of the same tag

New fields go to the end of their tag group. Rename the existing ones away, add, rename
back (renamed fields move to the end).

```
rule "590 out of the way"
priority 3
when
(not exists "590.a.Gift of the Friends")
then
changeField "590" to "ABC"
end

rule "add the new 590"
priority 2
when
(not exists "590.a.Gift of the Friends")
then
addField "590.a.Gift of the Friends"
end

rule "restore the old 590"
priority 1
when
(exists "ABC")
then
changeField "ABC" to "590"
end
```

## Remove the last occurrence of a character only

Append a sentinel, remove "character + sentinel", then remove any leftover sentinel.

```
rule "trailing comma 1 add sentinel"
priority 3
when
(TRUE)
then
suffix "500.a" with "_end_"
end

rule "trailing comma 2 remove comma and sentinel"
priority 2
when
(TRUE)
then
replaceContents "500.a.,_end_" with ""
end

rule "trailing comma 3 remove leftover sentinel"
priority 1
when
(TRUE)
then
replaceContents "500.a._end_" with ""
end
```
