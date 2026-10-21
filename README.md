# Alma Normalization Rules

A formal grammar (EBNF) for [Ex Libris Alma normalization rules](https://knowledge.ag-software.clarivate.com/alma/en-us/Product_Documentation/Metadata_Management/Working_with_Normalization_Rules.html#Normalization_Rule_Syntax), plus tools to create, validate and fix rules with an LLM.

- [Grammar documentation](https://html-preview.github.io/?url=https://github.com/mehmetc/AlmaNormalizationRules/blob/main/alma_normalization_rules.html) (railroad diagrams, created with [ebnf2railroad](https://matthijsgroen.github.io/ebnf2railroad/try-yourself.html))

## Background

After seeing Jill Strykowski's presentation [Training AI To Write ExLibris Norm Rules](https://exlkdelunaddam2024.dryfta.com/program-schedule/program/368/training-ai-to-write-exlibris-norm-rules) at #ELUNA2024, I thought: why not use an LLM to reverse engineer Alma normalization rules into an EBNF?

An EBNF is a notation that describes a syntax. An LLM can use it to write new rules from a description of what the rule needs to do, and a parser or language server can use it to check a rule's syntax.

## What's in this repository

| Path | Contents |
|---|---|
| `alma_normalization_rules.ebnf` | The grammar (ISO 14977 EBNF), checked against the Ex Libris documentation and examples |
| `alma_normalization_rules.html` | Railroad diagrams generated from the grammar |
| `prompts/` | Prompts for using the grammar in any LLM chat |
| `.claude/skills/alma-normalization-rules/` | A Claude Code skill that creates, validates and fixes rules |

## Using the Claude Code skill

Open this folder in Claude Code and ask, for example:

- "Write a normalization rule that removes all 650 fields with 2nd indicator 7"
- "Validate this rule: ..."
- "Fix this rule: ..."

The skill contains:

- `references/alma_normalization_rules.ebnf`: a copy of the grammar. Keep it identical to the one in the root; a test checks this.
- `references/syntax.md` and `references/patterns.md`: the syntax reference and common idioms
- `scripts/validate_rules.py`: a validator and fixer with no dependencies

You can also run the validator yourself:

```bash
python3 .claude/skills/alma-normalization-rules/scripts/validate_rules.py my.rules
```

```bash
python3 .claude/skills/alma-normalization-rules/scripts/validate_rules.py my.rules --fix
```

```bash
python3 .claude/skills/alma-normalization-rules/tests/test_validate_rules.py
```

## Using the prompts in another LLM

Copy `prompts/create_rule_from_ebnf.prompt` into the chat window.
Most free LLMs cannot follow links to external resources. In that case, paste the EBNF into the prompt and remove the URL.

<details>
<summary>Results from 2024-05-16 for the prompt "Remove all 650 fields which have 2nd indicator 0"</summary>

##### Expected
```
rule "remove 650 if 2nd indicator 0"
when
    (TRUE)
then
    removeField "650" if (exists "650.{*,0}")
end
```

##### ChatGPT 3.5
```
rule "Remove 650 fields with 2nd indicator 0"
priority 1
when
    (TRUE)
then
    removeField "650" if (exists "650.1", "0")
end
```

##### Copilot
```
rule "Remove 650 fields with 2nd indicator 0"
when
    (TRUE)
then
    removeField "650" if (exists "650.2, '0'")
end
```

##### Llama 3
```
remove_650_with_2nd_indicator_0
priority 1
when
    existsField("650") && secondIndicator("650") == "0"
then
    removeField("650")
end
```

##### Llama 2
```
rule "Remove 650 fields with 2nd indicator 0"
priority 1
when
    conditions = (TRUE)
then
actions = DELETE
end
```

##### Code Llama
```
rule "Remove 650 with 2nd indicator 0"
priority 1
when
    exists "650" if (exists "ind1" and "ind1" = '0')
then
    removeField "650" if (exists "ind1" and "ind1" = '0')
end
```

##### Mixtral
```
rule "Remove 650 fields with second indicator 0"
priority 1
when
    (
        field_tag = '650' and
        subfield_tag = '2' and
        subfield_value = '0'
    )
then
    removeField "650"
end
```

</details>

## Contributing

Fork the project and start editing; you do not need to install anything. You can help if you:

- are a native English speaker or prompt engineer who can refine the prompts
- can extend the grammar with syntax Alma accepts that is still missing
- can use the grammar to build a parser, language server, ...
- can organize a meeting and motivate people
- have ideas

## Sources

- Ex Libris Knowledge Center: [Working with Normalization Rules, Normalization Rule Syntax](https://knowledge.ag-software.clarivate.com/alma/en-us/Product_Documentation/Metadata_Management/Working_with_Normalization_Rules.html#Normalization_Rule_Syntax)
- Ex Libris Developer Network: [Alma Normalization Rule Examples](https://developers.exlibrisgroup.com/blog/alma-normalization-rule-examples/)

## Contributors

- Mehmet Celik (@mehmetc)
