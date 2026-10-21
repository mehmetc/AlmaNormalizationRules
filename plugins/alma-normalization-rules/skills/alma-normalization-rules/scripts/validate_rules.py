#!/usr/bin/env python3
"""Validate (and mechanically fix) Alma MARC normalization rules (Drools syntax).

The checks follow alma_normalization_rules.ebnf plus the documented gotchas from
the Ex Libris "Normalization Rule Syntax" page.

usage:
  validate_rules.py FILE [FILE ...]        validate, human readable report
  validate_rules.py -                      read the rules from stdin
  validate_rules.py FILE --json            machine readable report
  validate_rules.py FILE --fix             print the mechanically fixed rules
  validate_rules.py FILE --fix --in-place  rewrite FILE with the fixes

exit status: 0 no errors (warnings allowed), 1 errors found, 2 usage error
"""
import argparse
import bisect
import difflib
import json
import re
import sys

# --------------------------------------------------------------------------
# Element patterns (contents of the quoted strings)
# --------------------------------------------------------------------------

TAG = r"(?:[0-9A-Z]{3}|[0-9A-Z]{2}\*|[0-9A-Z]\*\*?)"
IND = r"\{[0-9A-Za-z*\- #],[0-9A-Za-z*\- #]\}"
CODE = r"[0-9A-Za-z*]"
POS = r"\{\d+,\d+\}"

ELEMENTS = {
    # name: (regex, human readable form)
    "tag": (rf"{TAG}", "<tag>  e.g. 245, LDR, TMP, 9*"),
    "tag_list": (rf"{TAG}(?:,{TAG})*", "<tag>,<tag>,...  e.g. 610,630,650"),
    "code": (r"[0-9A-Za-z]", "<code>  e.g. a"),
    "code_list": (r"[0-9A-Za-z]+", "<codes>  e.g. xyz"),
    "code_csv": (r"(?:[0-9A-Za-z](?:,[0-9A-Za-z])*)?", "<code>,<code>  e.g. a,b"),
    "indicator_value": (r"[0-9a-z #]", "a single indicator value, e.g. 1 or a space"),
    "tag_code": (rf"{TAG}\.{CODE}", "<tag>.<code>  e.g. 245.a"),
    "tag_ind_code": (rf"{TAG}(?:\.{IND})?\.{CODE}", "<tag>[.{{ind1,ind2}}].<code>"),
    "tag_code_opt": (rf"{TAG}(?:\.{CODE})?", "<tag>[.<code>]"),
    "copy_target": (rf"{TAG}(?:\.{IND})?(?:\.{CODE})?", "<tag>[.{{ind1,ind2}}][.<code>]"),
    "add_field": (rf"{TAG}(?:\.{IND})?\.{CODE}\..*", "<tag>[.{{ind1,ind2}}].<code>.<value>"),
    "add_control": (rf"{TAG}\..*", "<tag>.<value>"),
    "replace_src": (rf"{TAG}\.{CODE}(?:\..*)?", "<tag>.<code>.<value>"),
    "control_replace": (rf"{TAG}\.{POS}(?:\..*)?", "<tag>.{{<position>,<length>}}[.<value>]"),
    "fixed_replace": (rf"{TAG}\.{IND}\.{CODE}\.{POS}\..*",
                      "<tag>.{{<ind1>,<ind2>}}.<code>.{{<position>,<length>}}.<value>"),
    "split_src": (rf"{TAG}(?:\.{IND})?\.{CODE}\..+", "<tag>[.{{ind1,ind2}}].<code>.<delimiter>"),
    "data": (rf"{TAG}(?:\.{IND})?(?:\..*)?", "<tag>[.{{ind1,ind2}}][.<code>[.<value>]]"),
    "control": (rf"{TAG}(?:\.{POS})?(?:\..*)?", "<tag>[.{{<position>,<length>}}][.<value>]"),
    "fixed": (rf"{TAG}(?:\..*)?", "<tag>[.{{ind}}][.<code>][.{{pos,len}}][.<value>]"),
    "bool": (r"true|false", "true or false"),
    "any": (r"(?s:.*)", "any text"),
}

# Action signatures: S:<element> is a quoted string, K:<word> a keyword.
ACTIONS = {
    "changeControlField": ["S:tag", "K:to", "S:tag"],
    "changeField": ["S:tag", "K:to", "S:tag"],
    "changeSubField": ["S:tag_code", "K:to", "S:code"],
    "changeSubFieldOnlyFirst": ["S:tag_code", "K:to", "S:code"],
    "changeSubFieldExceptFirst": ["S:tag_code", "K:to", "S:code"],
    "changeFirstIndicator": ["S:tag", "K:to", "S:indicator_value"],
    "changeSecondIndicator": ["S:tag", "K:to", "S:indicator_value"],
    "combineFields": ["S:tag", "K:excluding", "S:code_csv"],
    "addField": ["S:add_field"],
    "addControlField": ["S:add_control"],
    "addSubField": ["S:add_field"],
    "addSystemNumber": ["S:tag_code", "K:from", "S:tag", "K:prefixed", "K:by", "S:any"],
    "copyField": ["S:tag_code_opt", "K:to", "S:copy_target"],
    "copyControlField": ["S:tag_code_opt", "K:to", "S:tag"],
    "removeControlField": ["S:tag"],
    "removeField": ["S:tag"],
    "removeSubField": ["S:tag_code"],
    "replaceControlContents": ["S:control_replace", "K:with", "S:any"],
    "replaceContents": ["S:replace_src", "K:with", "S:any"],
    "replaceContentsOnlyFirst": ["S:replace_src", "K:with", "S:any"],
    "replaceContentsExceptFirst": ["S:replace_src", "K:with", "S:any"],
    "replaceSubFieldContents": ["S:tag_code", "K:with", "S:tag_code"],
    "replaceFixedContents": ["S:fixed_replace", "K:with", "S:any"],
    "prefix": ["S:tag_code", "K:with", "S:any"],
    "prefixSubField": ["S:tag_code", "K:with", "S:tag_ind_code"],
    "suffix": ["S:tag_code", "K:with", "S:any"],
    "suffixSubField": ["S:tag_code", "K:with", "S:tag_ind_code"],
    "addCreatingAgency": ["S:tag_code"],
    "addModifyingAgency": ["S:tag_code"],
    "replaceModifyingAgency": ["S:tag_code"],
    "splitSubField": ["S:split_src"],  # optional: to "<target>" [addSeq "<code>"]
    "correctDuplicateSubfields": ["S:tag_list", "S:code_list"],
    "moveSubfieldsToEndOfField": ["S:tag", "S:code_list"],
    "correctDuplicateFields": ["S:tag_list"],
    "set": ["K:indication", "DOT", "S:bool"],  # indication rules
}
NO_IF = {"moveSubfieldsToEndOfField", "set"}
# actions that only appear in the official examples, not in the syntax table
EXAMPLE_ONLY = {"copyControlField"}

CONDITIONS = {
    "exists": "data",
    "existsMoreThanOnce": "data",
    "existsControl": "control",
    "existsFixedField": "fixed",
}
SCRIPTS = set("""Arabic Armenian Bengali Bopomofo Braille Buhid Canadian_Aboriginal
Cherokee Cyrillic Devanagari Ethiopic Georgian Greek Gujarati Gurmukhi Han Hangul
Hanunoo Hebrew Hiragana Inherited Kannada Katakana Khmer Lao Latin Limbu Malayalam
Mongolian Myanmar Ogham Oriya Runic Sinhala Syriac Tagalog Tagbanwa TaiLe Tamil
Telugu Thaana Thai Tibetan Yi""".split())

KEYWORDS = {"rule", "when", "then", "end", "priority", "salience", "if", "not",
            "to", "with", "from", "prefixed", "by", "excluding", "addSeq", "indication"}
BOOLEANS = {"TRUE", "true", "FALSE", "false"}
AND_OPS = {"AND", "and"}
OR_OPS = {"OR", "or"}
VALID_ESCAPES = set("btnfr\"'\\")

SMART_OPEN = {"\u201c": "\u201d", "\u2018": "\u2019"}
SMART_ALL = "\u201c\u201d\u2018\u2019\u201e\u2033"


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

class Issue:
    def __init__(self, severity, code, message, offset, fix=None, hint=None):
        self.severity = severity  # error | warning | info
        self.code = code
        self.message = message
        self.offset = offset
        self.fix = fix  # (start, end, replacement) or None
        self.hint = hint


class Source:
    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.starts = [0] + [m.end() for m in re.finditer(r"\n", text)]

    def pos(self, offset):
        line = bisect.bisect_right(self.starts, offset) - 1
        return line + 1, offset - self.starts[line] + 1

    def line_of(self, offset):
        return self.pos(offset)[0]


# --------------------------------------------------------------------------
# Lexer
# --------------------------------------------------------------------------

class Tok:
    def __init__(self, kind, value, start, end, quote=None):
        self.kind = kind  # WORD NUM STR LP RP DOT OP OTHER
        self.value = value
        self.start = start
        self.end = end
        self.quote = quote

    def __repr__(self):
        return "%s(%r)" % (self.kind, self.value)


def lex(src, issues):
    text, i, n, toks = src.text, 0, len(src.text), []
    while i < n:
        c = text[i]
        if c in " \t\r\n\ufeff\u00a0":
            i += 1
        elif c == "#" or text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c in "\"'" or c in SMART_OPEN:
            i = lex_string(src, i, toks, issues)
        elif c in SMART_ALL:
            issues.append(Issue("error", "smart-quote",
                                "typographic quote %r; use a straight quote" % c, i,
                                fix=(i, i + 1, '"')))
            i += 1
        elif c.isalpha() or c == "_":
            m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(text, i)
            toks.append(Tok("WORD", m.group(), i, m.end()))
            i = m.end()
        elif c.isdigit():
            m = re.compile(r"\d+").match(text, i)
            toks.append(Tok("NUM", m.group(), i, m.end()))
            i = m.end()
        elif c == "(":
            toks.append(Tok("LP", c, i, i + 1)); i += 1
        elif c == ")":
            toks.append(Tok("RP", c, i, i + 1)); i += 1
        elif c == ".":
            toks.append(Tok("DOT", c, i, i + 1)); i += 1
        elif text.startswith("&&", i) or text.startswith("||", i):
            toks.append(Tok("OP", text[i:i + 2], i, i + 2)); i += 2
        else:
            toks.append(Tok("OTHER", c, i, i + 1)); i += 1
    return toks


def lex_string(src, i, toks, issues):
    text, n = src.text, len(src.text)
    opener = text[i]
    smart = opener in SMART_OPEN
    closers = {SMART_OPEN[opener], '"' if opener == "\u201c" else "'"} if smart else {opener}
    j = i + 1
    while j < n:
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if ch in closers:
            break
        if ch == "\n":
            smart_close = {'"': "\u201d", "'": "\u2019"}.get(opener)
            k = text.rfind(smart_close, i + 1, j) if smart_close else -1
            if k >= 0:
                issues.append(Issue("error", "unterminated-string",
                                    "string is closed with a typographic quote %s" % text[k], k,
                                    fix=(k, k + 1, opener)))
            else:
                issues.append(Issue("error", "unterminated-string",
                                    "string is not closed before the end of the line", i))
            toks.append(Tok("STR", text[i + 1:j], i, j, quote=opener))
            return j
        j += 1
    if j >= n:
        issues.append(Issue("error", "unterminated-string", "string is not closed", i))
        toks.append(Tok("STR", text[i + 1:], i, n, quote=opener))
        return n
    if smart:
        straight = '"' if opener == "\u201c" else "'"
        issues.append(Issue("error", "smart-quote",
                            "typographic quotes %s...%s; use straight quotes %s...%s"
                            % (opener, text[j], straight, straight), i,
                            fix=(i, j + 1, straight + text[i + 1:j] + straight)))
        opener = straight
    tok = Tok("STR", text[i + 1:j], i, j + 1, quote=opener)
    toks.append(tok)
    check_string(src, tok, issues)
    return j + 1


def check_string(src, tok, issues):
    """Escape sequences and forbidden content, independent of context."""
    s, base = tok.value, tok.start + 1
    if "$$" in s:
        issues.append(Issue("error", "subfield-separator",
                            "the subfield separator $$ may not appear anywhere in a rule",
                            base + s.index("$$")))
    for m in re.finditer(r"\\+", s):
        run = len(m.group())
        if run % 2 == 0:
            continue
        nxt = s[m.end():m.end() + 1]
        if nxt in VALID_ESCAPES and nxt:
            continue
        if nxt == "u" and re.fullmatch(r"[0-9A-Fa-f]{4}", s[m.end() + 1:m.end() + 5] or ""):
            continue
        shown = m.group() + nxt
        fixed = "\\" * (run - 1) + nxt
        issues.append(Issue(
            "error", "invalid-escape",
            "invalid escape sequence %s (valid ones are \\b \\t \\n \\f \\r \\\" \\' \\\\)" % shown,
            base + m.start(), fix=(base + m.start(), base + m.end() + len(nxt), fixed),
            hint="use %s; a literal period at the end needs \\\\\\\\." % (fixed or "nothing")))


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class Rule:
    def __init__(self, start):
        self.start = start
        self.name = None
        self.name_tok = None
        self.priority = None
        self.when_tok = None
        self.preds = []      # (keyword, Tok) of the when condition
        self.and_count = 0
        self.or_count = 0
        self.actions = []    # Action


class Action:
    def __init__(self, name, tok):
        self.name = name
        self.tok = tok
        self.strings = []
        self.if_preds = []
        self.if_ops = 0


class ParseError(Exception):
    def __init__(self, issue):
        Exception.__init__(self, issue.message)
        self.issue = issue


class Parser:
    def __init__(self, src, toks, issues):
        self.src, self.toks, self.issues, self.i = src, toks, issues, 0
        self.rules = []
        self.lower_actions = {a.lower(): a for a in ACTIONS}

    # -- helpers -----------------------------------------------------------
    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def at_word(self, *words):
        tok = self.peek()
        return tok is not None and tok.kind == "WORD" and tok.value in words

    def eof_offset(self):
        return len(self.src.text)

    def fail(self, code, message, tok=None, hint=None):
        off = tok.start if tok else self.eof_offset()
        raise ParseError(Issue("error", code, message, off, hint=hint))

    def describe(self, tok):
        if tok is None:
            return "end of file"
        if tok.kind == "STR":
            return "string %s%s%s" % (tok.quote, tok.value, tok.quote)
        return repr(tok.value)

    def keyword(self, word, context):
        """Expect a keyword; accept and fix wrong casing."""
        tok = self.peek()
        if tok is not None and tok.kind == "WORD" and tok.value.lower() == word.lower():
            if tok.value != word:
                self.warn_case(tok, word)
            return self.next()
        self.fail("expected-keyword", "expected '%s' %s, found %s"
                  % (word, context, self.describe(tok)), tok)

    def warn_case(self, tok, canonical):
        self.issues.append(Issue("warning", "casing",
                                 "'%s' should be written '%s'" % (tok.value, canonical),
                                 tok.start, fix=(tok.start, tok.end, canonical)))

    def string(self, element, context):
        tok = self.peek()
        if tok is None or tok.kind != "STR":
            self.fail("expected-string", "expected a quoted %s %s, found %s"
                      % (ELEMENTS[element][1], context, self.describe(tok)), tok)
        self.next()
        regex, form = ELEMENTS[element]
        if not re.fullmatch(regex, tok.value):
            self.issues.append(Issue("error", "bad-element",
                                     "%s%s%s does not match %s %s"
                                     % (tok.quote, tok.value, tok.quote, form, context),
                                     tok.start, hint=element_hint(tok.value)))
        if tok.value.startswith("*"):
            self.issues.append(Issue("error", "leading-wildcard",
                                     "a wildcard cannot be the first character of an element",
                                     tok.start))
        return tok

    # -- grammar -------------------------------------------------------------
    def parse(self):
        while self.peek() is not None:
            start = self.i
            try:
                self.parse_rule()
            except ParseError as e:
                self.issues.append(e.issue)
                self.recover(start)
        return self.rules

    def recover(self, start):
        """Skip to the token after the next 'end', or to the next 'rule'."""
        if self.i <= start:
            self.i = start + 1
        while self.peek() is not None:
            tok = self.peek()
            if tok.kind == "WORD" and tok.value.lower() == "rule" and self.i > start:
                return
            self.i += 1
            if tok.kind == "WORD" and tok.value.lower() == "end":
                return

    def parse_rule(self):
        tok = self.peek()
        rule = Rule(tok.start)
        if not (tok.kind == "WORD" and tok.value.lower() == "rule"):
            self.fail("expected-rule", "expected 'rule \"<name>\"', found %s" % self.describe(tok), tok)
        self.keyword("rule", "to start a rule")
        name = self.peek()
        if name is None or name.kind != "STR":
            self.fail("expected-name", "expected the rule name as a quoted string after 'rule'", name)
        self.next()
        rule.name, rule.name_tok = name.value, name
        if name.quote != '"':
            self.issues.append(Issue("error", "name-quotes", "the rule name must be in double quotes",
                                     name.start, fix=(name.start, name.end, '"%s"' % name.value)))
        self.rules.append(rule)

        if self.at_word("priority", "salience", "Priority", "Salience", "PRIORITY", "SALIENCE"):
            kw = self.next()
            if kw.value not in ("priority", "salience"):
                self.warn_case(kw, kw.value.lower())
            num = self.peek()
            if num is None or num.kind != "NUM":
                self.fail("expected-priority", "expected a whole number after '%s'" % kw.value, num)
            self.next()
            rule.priority = int(num.value)

        rule.when_tok = self.keyword("when", "after the rule name/priority")
        first = self.peek()
        if first is not None and self.src.line_of(first.start) == self.src.line_of(rule.when_tok.start):
            self.issues.append(Issue("warning", "when-line",
                                     "'when' must be the only word on its line; put the condition on the next line",
                                     first.start, fix=(rule.when_tok.end, first.start, "\n    ")))
        if self.at_word("then"):
            self.fail("empty-condition", "missing condition after 'when'; use (TRUE) to always apply",
                      self.peek())
        self.parse_or(rule, rule.preds, top=True)
        tok = self.peek()
        if not (tok is not None and tok.kind == "WORD" and tok.value.lower() == "then"):
            self.fail("expected-keyword", "expected AND/OR or 'then' after the condition, found %s"
                      % self.describe(tok), tok)
        self.keyword("then", "after the condition")

        if self.at_word("end"):
            self.fail("no-actions", "a rule needs at least one action between 'then' and 'end'", self.peek())
        while True:
            tok = self.peek()
            if tok is None:
                self.fail("expected-end", "rule \"%s\" is not closed with 'end'" % rule.name)
            if tok.kind == "WORD" and tok.value.lower() == "end":
                self.keyword("end", "")
                break
            if tok.kind == "WORD" and tok.value.lower() == "rule":
                self.fail("expected-end", "rule \"%s\" is not closed with 'end' before the next rule"
                          % rule.name, tok)
            rule.actions.append(self.parse_action())

    # conditions -------------------------------------------------------------
    def parse_or(self, rule, preds, top=False):
        counts = rule if top else None
        self.parse_and(rule, preds, top)
        while True:
            tok = self.peek()
            if tok is None:
                return
            if tok.kind == "WORD" and tok.value in OR_OPS | {"Or"}:
                if tok.value == "Or":
                    self.warn_case(tok, "OR")
                self.next()
            elif tok.kind == "OP" and tok.value == "||":
                self.issues.append(Issue("error", "operator", "use OR instead of ||", tok.start,
                                         fix=(tok.start, tok.end, "OR")))
                self.next()
            else:
                return
            if counts:
                counts.or_count += 1
            else:
                self._if_ops += 1
            self.parse_and(rule, preds, top)

    def parse_and(self, rule, preds, top):
        self.parse_term(rule, preds, top)
        while True:
            tok = self.peek()
            if tok is None:
                return
            if tok.kind == "WORD" and tok.value in AND_OPS | {"And"}:
                if tok.value == "And":
                    self.warn_case(tok, "AND")
                self.next()
            elif tok.kind == "OP" and tok.value == "&&":
                self.issues.append(Issue("error", "operator", "use AND instead of &&", tok.start,
                                         fix=(tok.start, tok.end, "AND")))
                self.next()
            else:
                return
            if top:
                rule.and_count += 1
            else:
                self._if_ops += 1
            self.parse_term(rule, preds, top)

    def parse_term(self, rule, preds, top):
        tok = self.peek()
        if tok is not None and tok.kind == "LP":
            self.next()
            self.parse_or(rule, preds, top)
            close = self.peek()
            if close is None or close.kind != "RP":
                self.fail("expected-paren", "expected ')' to close the condition, found %s"
                          % self.describe(close), close)
            self.next()
            return
        self.parse_predicate(preds)

    def parse_predicate(self, preds):
        tok = self.peek()
        if tok is None or tok.kind not in ("WORD", "OTHER", "OP"):
            self.fail("expected-condition", "expected a condition (TRUE, exists \"...\", ...), found %s"
                      % self.describe(tok), tok)
        if tok.kind == "OTHER" and tok.value == "!":
            self.issues.append(Issue("error", "operator", "use 'not' instead of !", tok.start,
                                     fix=(tok.start, tok.end, "not ")))
            self.next()
            tok = self.peek()
        word = tok.value if tok is not None else ""
        if word in BOOLEANS or word.upper() in ("TRUE", "FALSE"):
            if word not in BOOLEANS:
                self.warn_case(tok, word.upper())
            self.next()
            preds.append((word.upper(), tok))
            return
        if word.lower() == "not":
            if word != "not":
                self.warn_case(tok, "not")
            self.next()
            tok = self.peek()
            word = tok.value if tok is not None else ""
        canon = {k.lower(): k for k in CONDITIONS}.get(word.lower())
        if canon:
            if canon != word:
                self.warn_case(tok, canon)
            self.next()
            preds.append((canon, self.string(CONDITIONS[canon], "after %s" % canon)))
            return
        if word == "containsScript":
            self.next()
            script = self.string("any", "(script name) after containsScript")
            tag = self.string("tag", "(field) after containsScript")
            if script.value not in SCRIPTS:
                self.issues.append(Issue("error", "unknown-script",
                                         "unknown script %r for containsScript" % script.value,
                                         script.start, hint=suggest(script.value, SCRIPTS)))
            preds.append((word, tag))
            return
        if word == "recordHasDuplicateSubfields":
            self.next()
            tags = self.string("tag_list", "after recordHasDuplicateSubfields")
            self.string("code_list", "(subfield codes) after the tags")
            self.string("any", "(characters to ignore) after the codes")
            preds.append((word, tags))
            return
        if word == "recordHasDuplicateFields":
            self.next()
            preds.append((word, self.string("tag_list", "after recordHasDuplicateFields")))
            return
        known = list(CONDITIONS) + ["TRUE", "not", "containsScript",
                                    "recordHasDuplicateSubfields", "recordHasDuplicateFields"]
        self.fail("unknown-condition", "unknown condition %s" % self.describe(tok), tok,
                  hint=suggest(word, known))

    # actions ----------------------------------------------------------------
    def parse_action(self):
        tok = self.peek()
        if tok.kind != "WORD":
            self.fail("expected-action", "expected an action or 'end', found %s" % self.describe(tok), tok)
        name = tok.value
        if name not in ACTIONS:
            canon = self.lower_actions.get(name.lower())
            if canon:
                self.warn_case(tok, canon)
                name = canon
            else:
                self.fail("unknown-action", "unknown action %r" % name, tok,
                          hint=suggest(name, ACTIONS))
        self.next()
        act = Action(name, tok)
        for item in ACTIONS[name]:
            kind, _, arg = item.partition(":")
            if kind == "S":
                act.strings.append(self.string(arg, "for %s" % name))
            elif kind == "K":
                self.keyword(arg, "in %s" % name)
            elif kind == "DOT":
                dot = self.peek()
                if dot is None or dot.kind != "DOT":
                    self.fail("expected-dot", "expected '.' in %s" % name, dot)
                self.next()
        if name == "splitSubField":
            if self.at_word("to"):
                self.next()
                act.strings.append(self.string("tag_ind_code", "after splitSubField ... to"))
                if self.at_word("addSeq"):
                    self.next()
                    act.strings.append(self.string("code", "after addSeq"))
            elif self.at_word("addSeq"):
                self.issues.append(Issue("warning", "addseq-without-to",
                                         "addSeq is only relevant together with 'to'", self.peek().start))
                self.next()
                self.string("code", "after addSeq")
        if self.at_word("if", "If", "IF"):
            if_tok = self.next()
            if if_tok.value != "if":
                self.warn_case(if_tok, "if")
            if name in NO_IF:
                self.issues.append(Issue("error", "if-not-supported",
                                         "%s does not support an if clause" % name, if_tok.start))
            lp = self.peek()
            if lp is None or lp.kind != "LP":
                self.fail("expected-paren", "expected '(' after 'if'", lp)
            self._if_ops = 0
            self.parse_term(None, act.if_preds, top=False)
            act.if_ops = self._if_ops
        return act


def suggest(word, choices):
    match = difflib.get_close_matches(word, list(choices), n=1, cutoff=0.6)
    if not match:
        match = [c for c in choices if c.lower() == word.lower()]
    return "did you mean %s?" % match[0] if match else None


def element_hint(value):
    if re.match(r"^\d{1,2}(\.|$)", value):
        return "a tag has 3 characters, e.g. 020 not 20"
    if "{" in value and not re.search(IND, value) and not re.search(POS, value):
        return "indicators are written {ind1,ind2}, positions {start,length}"
    if re.match(r"^\d{3}\$", value) or "$" in value[:5]:
        return "write subfields as <tag>.<code>, e.g. 245.a (no $)"
    return None


# --------------------------------------------------------------------------
# Semantic checks
# --------------------------------------------------------------------------

def tag_of(value):
    m = re.match(TAG, value)
    return m.group() if m else None


def tags_compatible(a, b):
    if not a or not b:
        return True
    pa, pb = a.rstrip("*"), b.rstrip("*")
    return pa.startswith(pb) or pb.startswith(pa)


TRAILING_PERIOD_ACTIONS = {"addField", "addSubField", "replaceContents", "replaceContentsOnlyFirst",
                           "replaceContentsExceptFirst"}


def check_rules(src, rules, issues):
    names = {}
    for rule in rules:
        if rule.name is None:
            continue
        if rule.name in names:
            issues.append(Issue("error", "duplicate-name",
                                "duplicate rule name \"%s\"; every rule in a file needs a unique name"
                                % rule.name, rule.name_tok.start))
        names.setdefault(rule.name, rule)
        if len(rule.name) > 255:
            issues.append(Issue("error", "name-length", "rule names are limited to 255 characters",
                                rule.name_tok.start))
        if "\\" in rule.name:
            issues.append(Issue("warning", "name-backslash",
                                "do not use a backslash in the rule name; the rule cannot be used for filter sets",
                                rule.name_tok.start))
        if not rule.name.strip():
            issues.append(Issue("warning", "name-empty", "give the rule a short descriptive name",
                                rule.name_tok.start))
        ops = rule.and_count + rule.or_count
        if ops > 200:
            issues.append(Issue("warning", "too-many-operators",
                                "%d boolean operators; keep it under 200 for performance" % ops,
                                rule.when_tok.start))
        if rule.or_count:
            issues.append(Issue("info", "or-multiple-firing",
                                "OR in 'when': if several branches are true the rule can fire more than "
                                "once for the same record; make sure the actions are idempotent or use "
                                "a pipe value (exists \"900.a.A|B\") / separate rules",
                                rule.when_tok.start))
        removed_008 = any(a.name == "removeControlField" and a.strings and a.strings[0].value == "008"
                          for a in rule.actions)
        added_008 = any(a.name == "addControlField" and a.strings and a.strings[0].value.startswith("008.")
                        for a in rule.actions)
        if removed_008 and not added_008:
            issues.append(Issue("warning", "removed-008",
                                "Alma recreates 008 when it is removed; add it back with addControlField \"008.<value>\"",
                                rule.start))
        for act in rule.actions:
            check_action(src, act, issues)
        for kind, tok in rule.preds + [p for a in rule.actions for p in a.if_preds]:
            if CONDITIONS.get(kind) == "data":
                m = re.fullmatch(rf"{TAG}(?:\.{IND})?\.{CODE}\.(.*)", tok.value, re.S)
                if m:
                    check_trailing_period(tok, m.group(1), issues)

    # Priority is only needed when rules work on the same fields: report each rule
    # once, against the first earlier rule with the same priority and a shared field.
    seen = []
    for rule in rules:
        fields = {tag_of(s.value) for a in rule.actions for s in a.strings[:1]} - {None}
        for other, other_fields in seen:
            if other.priority != rule.priority:
                continue
            shared = {a for a in fields for b in other_fields if tags_compatible(a, b)}
            if shared:
                issues.append(Issue(
                    "warning", "same-priority",
                    "rules \"%s\" and \"%s\" both change %s with %s; give them distinct "
                    "priorities (higher runs first) so the order is explicit"
                    % (other.name, rule.name, ",".join(sorted(shared)),
                       "no priority" if rule.priority is None else "priority %d" % rule.priority),
                    rule.start))
                break
        seen.append((rule, fields))


def check_action(src, act, issues):
    target = act.strings[0] if act.strings else None
    target_tag = tag_of(target.value) if target else None
    if act.name in EXAMPLE_ONLY:
        issues.append(Issue("info", "example-only",
                            "%s is used in the official examples but not listed in the syntax table" % act.name,
                            act.tok.start))
    if act.name in ("replaceContents", "replaceContentsOnlyFirst", "replaceContentsExceptFirst") and target:
        if not re.fullmatch(rf"{TAG}\.{CODE}\..+", target.value):
            issues.append(Issue("warning", "replace-without-value",
                                "%s expects \"<tag>.<code>.<value to replace>\"" % act.name, target.start))
    if act.name in TRAILING_PERIOD_ACTIONS and target:
        check_trailing_period(target, value_part(act.name, target.value), issues,
                              match=act.name.startswith("replace"))
    if act.name in ("prefix", "suffix") and len(act.strings) > 1:
        check_trailing_period(act.strings[1], act.strings[1].value, issues, match=False)
    if act.name == "addSystemNumber" and len(act.strings) > 2 and not re.fullmatch(TAG, act.strings[2].value):
        issues.append(Issue("info", "prefix-not-tag",
                            "prefixed by \"%s\" is not a field tag; the examples use this to add no prefix"
                            % act.strings[2].value, act.strings[2].start))
    for kind, tok in act.if_preds:
        if kind not in CONDITIONS:
            issues.append(Issue("error", "if-condition",
                                "an if clause supports exists / existsControl / existsMoreThanOnce / "
                                "existsFixedField, not %s" % kind, tok.start))
            continue
        cond_tag = tag_of(tok.value)
        if not tags_compatible(target_tag, cond_tag):
            issues.append(Issue("warning", "if-other-field",
                                "the if clause tests %s but the action changes %s; an if clause is evaluated "
                                "per field, so both must be the same field (move the test to 'when' to "
                                "test the record)" % (cond_tag, target_tag), tok.start))
        if act.name == "removeControlField" or act.name.endswith("ControlContents") \
                or act.name == "changeControlField":
            if kind != "existsControl":
                issues.append(Issue("warning", "control-exists",
                                    "use existsControl for control fields (LDR, 00X)", tok.start))
    if act.if_ops:
        issues.append(Issue("warning", "if-boolean",
                            "AND/OR inside an if clause is not documented; use one test per action, "
                            "a pipe for alternatives (\"650.a.A|B\") or move the logic to 'when'",
                            act.tok.start))


def value_part(action, value):
    if action in ("addField", "addSubField"):
        m = re.fullmatch(rf"{TAG}(?:\.{IND})?\.{CODE}\.(.*)", value, re.S)
    else:
        m = re.fullmatch(rf"{TAG}\.{CODE}\.(.*)", value, re.S)
    return m.group(1) if m else ""


def check_trailing_period(tok, value, issues, match=True):
    """match: the value is matched against record text (a lone "." counts too)."""
    if value.endswith(".") and not value.endswith("\\\\\\\\.") and (match or value != "."):
        end = tok.end - 1  # offset of the closing quote
        run = re.search(r"\\*\.$", value).group()
        issues.append(Issue("warning", "trailing-period",
                            "a period at the end of a value must be written \\\\\\\\. to be matched/added literally",
                            end - len(run), fix=(end - len(run), end, "\\\\\\\\.")))


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def validate(name, text):
    src = Source(name, text)
    issues = []
    toks = lex(src, issues)
    if not toks:
        issues.append(Issue("error", "empty", "no rules found", 0))
        return src, [], issues
    rules = Parser(src, toks, issues).parse()
    check_rules(src, rules, issues)
    issues.sort(key=lambda x: x.offset)
    return src, rules, issues


def apply_fixes(text, issues):
    fixes = sorted({x.fix for x in issues if x.fix}, key=lambda f: (f[0], f[1]))
    out, last, applied = [], 0, 0
    for start, end, repl in fixes:
        if start < last:
            continue  # overlapping, picked up in the next pass
        out.append(text[last:start])
        out.append(repl)
        last = end
        applied += 1
    out.append(text[last:])
    return "".join(out), applied


def fix(name, text, passes=5):
    total = 0
    for _ in range(passes):
        _, _, issues = validate(name, text)
        text, applied = apply_fixes(text, issues)
        total += applied
        if not applied:
            break
    return text, total


def report(src, rules, issues, as_json):
    counts = {s: sum(1 for x in issues if x.severity == s) for s in ("error", "warning", "info")}
    if as_json:
        return {
            "file": src.name,
            "rules": [r.name for r in rules],
            "errors": counts["error"], "warnings": counts["warning"], "infos": counts["info"],
            "issues": [{
                "severity": x.severity, "code": x.code, "message": x.message,
                "line": src.pos(x.offset)[0], "column": src.pos(x.offset)[1],
                "fixable": bool(x.fix), "hint": x.hint,
            } for x in issues],
        }
    lines = []
    for x in issues:
        line, col = src.pos(x.offset)
        msg = "%s:%d:%d: %s: %s [%s]" % (src.name, line, col, x.severity, x.message, x.code)
        if x.hint:
            msg += "\n    hint: " + x.hint
        if x.fix:
            msg += "\n    fixable with --fix"
        lines.append(msg)
    lines.append("%s: %d rule(s), %d error(s), %d warning(s), %d info"
                 % (src.name, len(rules), counts["error"], counts["warning"], counts["info"]))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate Alma MARC normalization rules.")
    ap.add_argument("files", nargs="+", help="rule files, or - for stdin")
    ap.add_argument("--json", action="store_true", help="print a JSON report")
    ap.add_argument("--fix", action="store_true", help="apply mechanical fixes and print the result")
    ap.add_argument("--in-place", action="store_true", help="with --fix, rewrite the files")
    args = ap.parse_args(argv)
    if args.in_place and not args.fix:
        ap.error("--in-place requires --fix")

    status, reports = 0, []
    for path in args.files:
        text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        name = "<stdin>" if path == "-" else path
        if args.fix:
            text, applied = fix(name, text)
            if args.in_place and path != "-":
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            else:
                sys.stdout.write(text)
            print("%s: applied %d fix(es)" % (name, applied), file=sys.stderr)
        src, rules, issues = validate(name, text)
        if any(x.severity == "error" for x in issues):
            status = 1
        rep = report(src, rules, issues, args.json)
        if args.json:
            reports.append(rep)
        else:
            print(rep, file=sys.stderr if args.fix else sys.stdout)
    if args.json:
        out = json.dumps(reports if len(reports) > 1 else reports[0], indent=2, ensure_ascii=False)
        print(out, file=sys.stderr if args.fix else sys.stdout)
    return status


if __name__ == "__main__":
    sys.exit(main())
