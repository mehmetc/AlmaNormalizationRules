# Alma Normalization Rules

After seeing a presentation from 'Jill Strykowski' [Training AI To Write ExLibris Norm Rules](https://exlkdelunaddam2024.dryfta.com/program-schedule/program/368/training-ai-to-write-exlibris-norm-rules) at #ELUNA2024.
I thought why not use an LLM to reverse engineer 'Alma Normalization Rules' into an EBNF.

An EBNF is a notation that describes a syntax. We could use this EBNF file with an LLM to generate new rules by describing what the rule needs to do. Or a language server to validate the syntax.

Fork the project and start editing you do not need to install anything. You can help if you are a:
- native English speaker or prompt engineer to refine the prompts
- extend the EBNF with all possible actions
- can use the EBNF to write a parser, language server, ...
- can organize a meeting and motivate people
- an ideas person

Test by copying prompts/create_rule_from_ebnf.prompt into the chat window.
Caution most free to use LLMs do not support links to external resources. Paste the EBNF into the prompt and remove the referenced url. 



Results on 2024-05-16 for the prompt 'Remove all 650 fields which have 2nd indicator 0':

##### Expected 
```
rule "remove 650 if 2nd indicator 0"
when
    (TRUE)
then
    removeField "650" if (exists "650.{*,0}")
end
```

##### ChatGPT3.5
```
rule "Remove 650 fields with 2nd indicator 0"
priority 1
when
    (TRUE)
then
    removeField "650" if (exists "650.1", "0")
end
```

##### copilot
```
rule "Remove 650 fields with 2nd indicator 0"
when
    (TRUE)
then
    removeField "650" if (exists "650.2, '0'")
end
```

##### Llama3
```
remove_650_with_2nd_indicator_0
priority 1
when
    existsField("650") && secondIndicator("650") == "0"
then
    removeField("650")
end
```

##### Llama2
```
rule "Remove 650 fields with 2nd indicator 0"
priority 1
when
    conditions = (TRUE)
then
actions = DELETE
end
```

##### codellama
```
rule "Remove 650 with 2nd indicator 0"
priority 1
when
    exists "650" if (exists "ind1" and "ind1" = '0')
then
    removeField "650" if (exists "ind1" and "ind1" = '0')
end
```

##### mixtral
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



Contributors:
- Mehmet Celik (@mehmetc)