#!/usr/bin/env python3
"""Regression tests for validate_rules.py and check_ebnf.py.

run: python3 tests/test_validate_rules.py
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import validate_rules as v  # noqa: E402


def codes(text, severity=None):
    _, _, issues = v.validate("<test>", text)
    return [i.code for i in issues if severity is None or i.severity == severity]


VALID = {
    "remove 650 2nd indicator 0": '''
rule "remove 650 if 2nd indicator 0"
when
(TRUE)
then
removeField "650" if (exists "650.{*,0}")
end
''',
    "priority, comments and control fields": '''
# copy the 008 language code to 041
rule "copy 008 language code to 041"
priority 10
when
(not existsControl "009") AND (not exists "041.a")
then
copyControlField "008" to "009"   // undocumented but used by Ex Libris
replaceControlContents "009.{0,35}" with " "
copyField "009" to "041.a"
removeControlField "009"
end
''',
    "salience and multiple rules on same field": '''
rule "change field 519 to 919"
salience 10
when
TRUE
then
changeField "519" to "919"
end

rule "remove duplicate 919 fields"
salience 9
when
TRUE
then
correctDuplicateFields "919"
end
''',
    "split with to and addSeq": '''
rule "split 866"
when
(exists "866.a.*;*")
then
splitSubField "866.a.;" to "555.{0,0}.a" addSeq "8"
end
''',
    "single quoted condition with escaped double quote": '''
rule "populate 008 7-10 2016"
when
(exists '245.{*, }.c.\\"')
then
replaceControlContents "008.{7,4}" with "2016"
end
''',
    "every action form": '''
rule "all actions"
when
(TRUE)
then
changeControlField "007" to "008"
changeSubFieldOnlyFirst "040.d" to "a"
changeSecondIndicator "856" to "0" if (exists "856.{*,1}")
combineFields "852" excluding "a,b"
addField "999.{-,-}.a.RESTRICTED"
addControlField "008.820305s1991####nyu###########001#0#eng##"
addSubField "245.h.[Journal]"
addSystemNumber "035.a" from "001" prefixed by "003"
copyField "300" to "901.{1,2}"
removeSubField "245.h"
replaceControlContents "LDR.{7,1}.s" with "m"
replaceContentsExceptFirst "938.a.Baker and Taylor" with "B and T"
replaceSubFieldContents "245.b" with "100.a"
replaceFixedContents "100.{1,2}.a.{0,8}.20150226" with "20220724"
prefix "035.b" with "(OCoLC)"
prefixSubField "910.a" with "906.a"
suffix "500.a" with "\\\\\\\\." if (not exists "500.a.*\\\\\\\\.")
suffixSubField "910.a" with "907.c"
addCreatingAgency "040.a"
correctDuplicateSubfields "610,630" "xyz"
moveSubfieldsToEndOfField "650" "92"
removeField "9*" if (not exists "913.a.*")
end
''',
    "containsScript and indication": '''
rule "Is CJK in Authority"
when
containsScript "Han" "1**"
then
set indication."true"
end
''',
}


class ValidRules(unittest.TestCase):
    def test_valid(self):
        for name, text in VALID.items():
            with self.subTest(name):
                self.assertEqual(codes(text, "error"), [], name)
                self.assertEqual(codes(text, "warning"), [], name)


class InvalidRules(unittest.TestCase):
    def expect(self, text, code, severity="error"):
        self.assertIn(code, codes(text, severity), codes(text))

    def test_missing_end(self):
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nremoveField "650"\n', "expected-end")

    def test_missing_then(self):
        self.expect('rule "a"\nwhen\n(TRUE)\nremoveField "650"\nend\n', "expected-keyword")

    def test_unknown_action_suggests(self):
        _, _, issues = v.validate("t", 'rule "a"\nwhen\n(TRUE)\nthen\nremoveFeld "650"\nend\n')
        issue = [i for i in issues if i.code == "unknown-action"][0]
        self.assertIn("removeField", issue.hint)

    def test_bad_tag(self):
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nremoveField "65"\nend\n', "bad-element")

    def test_subfield_with_dollar(self):
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nremoveSubField "245$h"\nend\n', "bad-element")

    def test_dollar_dollar(self):
        self.expect('rule "add $$a"\nwhen\n(TRUE)\nthen\nremoveField "650"\nend\n', "subfield-separator")

    def test_invalid_escape(self):
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nreplaceContents "245.a.\\(x\\)" with ""\nend\n',
                    "invalid-escape")

    def test_smart_quotes(self):
        self.expect('rule “a”\nwhen\n(TRUE)\nthen\nremoveField "650"\nend\n', "smart-quote")

    def test_move_subfields_no_if(self):
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nmoveSubfieldsToEndOfField "650" "92" '
                    'if (exists "650.9")\nend\n', "if-not-supported")

    def test_duplicate_names(self):
        rule = 'rule "a"\nwhen\n(TRUE)\nthen\nremoveField "650"\nend\n'
        self.expect(rule + rule, "duplicate-name")

    def test_c_style_operators(self):
        self.expect('rule "a"\nwhen\n(exists "650") && (exists "651")\nthen\nremoveField "650"\nend\n',
                    "operator")

    def test_unknown_script(self):
        self.expect('rule "a"\nwhen\ncontainsScript "Chinese" "245"\nthen\nremoveField "650"\nend\n',
                    "unknown-script")

    def test_leading_wildcard(self):
        self.expect('rule "a"\nwhen\n(exists "*.a")\nthen\nremoveField "650"\nend\n', "leading-wildcard")

    def test_empty_condition(self):
        self.expect('rule "a"\nwhen\nthen\nremoveField "650"\nend\n', "empty-condition")

    def test_warnings(self):
        self.expect('rule "a"\nwhen (TRUE)\nthen\nremoveField "650"\nend\n', "when-line", "warning")
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nremoveField "863" if (not exists "866.8.9")\nend\n',
                    "if-other-field", "warning")
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nremoveControlField "008"\nend\n', "removed-008", "warning")
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\naddField "907.a.F.L.T."\nend\n', "trailing-period", "warning")
        self.expect('rule "a"\nwhen\n(TRUE)\nthen\nReplaceContents "245.a.x" with "y"\nend\n',
                    "casing", "warning")
        two = ('rule "a"\nwhen\n(TRUE)\nthen\nremoveField "650"\nend\n'
               'rule "b"\nwhen\n(TRUE)\nthen\naddField "650.a.x"\nend\n')
        self.expect(two, "same-priority", "warning")


class Fixer(unittest.TestCase):
    def test_fix_round_trip(self):
        broken = ('rule “fix me”\nWhen (true)\nthen\nReplaceContents "245.a.\\." with ""\n'
                  'addField "907.a.F.L.T."\nEnd\n')
        fixed, applied = v.fix("t", broken)
        self.assertGreater(applied, 0)
        self.assertEqual(codes(fixed, "error"), [], fixed)
        self.assertEqual(codes(fixed, "warning"), [], fixed)
        self.assertIn('rule "fix me"', fixed)
        self.assertIn("when\n    (true)", fixed)
        self.assertIn('replaceContents "245.a.\\\\\\\\." with ""', fixed)
        self.assertIn('addField "907.a.F.L.T\\\\\\\\."', fixed)
        self.assertTrue(fixed.rstrip().endswith("end"))


class Docs(unittest.TestCase):
    def test_patterns_are_clean(self):
        import re
        with open(os.path.join(SKILL, "references", "patterns.md"), encoding="utf-8") as fh:
            blocks = re.findall(r"```\n(.*?)```", fh.read(), re.S)
        self.assertGreater(len(blocks), 5)
        for block in blocks:
            with self.subTest(block.splitlines()[0]):
                self.assertEqual(codes(block, "error") + codes(block, "warning"), [], block)


class Grammar(unittest.TestCase):
    def test_ebnf_well_formed(self):
        for path in (os.path.join(SKILL, "references", "alma_normalization_rules.ebnf"),
                     os.path.join(SKILL, "..", "..", "..", "alma_normalization_rules.ebnf")):
            if not os.path.exists(path):
                continue
            with self.subTest(path):
                out = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "check_ebnf.py"), path],
                                     capture_output=True, text=True)
                self.assertEqual(out.returncode, 0, out.stdout)

    def test_ebnf_copies_in_sync(self):
        skill_copy = os.path.join(SKILL, "references", "alma_normalization_rules.ebnf")
        repo_copy = os.path.join(SKILL, "..", "..", "..", "alma_normalization_rules.ebnf")
        if os.path.exists(repo_copy):
            with open(skill_copy, encoding="utf-8") as a, open(repo_copy, encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read(), "copy the repo EBNF into references/")

    def test_grammar_actions_match_validator(self):
        with open(os.path.join(SKILL, "references", "alma_normalization_rules.ebnf"), encoding="utf-8") as fh:
            ebnf = fh.read()
        for action in v.ACTIONS:
            with self.subTest(action):
                self.assertIn("'%s'" % action, ebnf)


if __name__ == "__main__":
    unittest.main(verbosity=1)
