#!/usr/bin/env python3
"""Well-formedness check for an ISO 14977 EBNF file.

Reports unbalanced brackets, undefined nonterminals, duplicate definitions and
productions that cannot be reached from the start symbol.

usage: check_ebnf.py <file.ebnf> [--start rule_file,comment]
"""
import argparse
import re
import sys

PAIRS = {"(": ")", "[": "]", "{": "}"}


def strip(text):
    """Remove (* comments *), quoted terminals and ? special sequences ?."""
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("(*", i):
            j = text.find("*)", i + 2)
            if j < 0:
                raise SyntaxError("unterminated comment at offset %d" % i)
            i = j + 2
            out.append(" ")
        elif text[i] in "'\"?":
            q = text[i]
            j = text.find(q, i + 1)
            if j < 0:
                raise SyntaxError("unterminated %s at offset %d" % (q, i))
            i = j + 1
            out.append(" TERMINAL ")
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--start", default="rule_file,comment",
                    help="comma separated root productions")
    args = ap.parse_args()

    body = strip(open(args.file, encoding="utf-8").read())
    problems = []
    rules = {}
    for stmt in body.split(";"):
        if not stmt.strip():
            continue
        if "=" not in stmt:
            problems.append("statement without '=': %r" % stmt.strip()[:60])
            continue
        lhs, rhs = stmt.split("=", 1)
        name = lhs.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            problems.append("bad production name %r" % name)
            continue
        if name in rules:
            problems.append("duplicate definition of %s" % name)
        stack = []
        for ch in rhs:
            if ch in PAIRS:
                stack.append(ch)
            elif ch in PAIRS.values():
                if not stack or PAIRS[stack.pop()] != ch:
                    problems.append("unbalanced %r in %s" % (ch, name))
                    break
        if stack:
            problems.append("unclosed %r in %s" % (stack[-1], name))
        rules[name] = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", rhs)) - {"TERMINAL"}

    for name, refs in rules.items():
        for ref in sorted(refs - rules.keys()):
            problems.append("%s references undefined %s" % (name, ref))

    roots = args.start.split(",")
    for root in roots:
        if root not in rules:
            problems.append("start symbol %s is not defined" % root)
    if all(root in rules for root in roots):
        seen, todo = set(), list(roots)
        while todo:
            cur = todo.pop()
            if cur in seen or cur not in rules:
                continue
            seen.add(cur)
            todo.extend(rules[cur])
        for name in rules:
            if name not in seen:
                problems.append("%s is unreachable from %s" % (name, args.start))

    for p in problems:
        print("ebnf: " + p)
    print("%d productions, %d problem(s)" % (len(rules), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
