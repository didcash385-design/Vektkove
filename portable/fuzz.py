#!/usr/bin/env python3
"""Randomised differential fuzz: macOS engine (./vk) vs portable runner.

Generates random .vk programs from every instruction family and checks that both
engines agree on compile result, bytecode, run exit status, stdout and the first
error line. Usage: portable/fuzz.py /path/to/vkport [count] [seed]
"""
import os
import random
import subprocess
import sys
import tempfile

PORT = sys.argv[1]
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 12345
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VK = os.path.join(ROOT, "vk")
rnd = random.Random(SEED)

NAMES = ["a", "b", "c", "n", "s", "Total"]
NUMS = ["0", "1", "-1", "2", "3", "7", "10", "0.5", "-2.5", "1e3", "255", "100000", "0.1", "1e15", "1e20", "-0", "3.", ".5"]
STRS = ['""', '"hi"', '"Hello World"', '"  pad  "', '"ß"', '"é😀"', '"a\\nb"', '"x"', '"aaa"', '"12"', '"ÀÉ"']
WORDS = ["foo", "0x1f", "inf", "nan", "1e400", "+5"]
TWO_NUM = ["add", "subtract", "multiply", "divide", "modulo", "power", "min", "max", "less", "less_equal",
           "greater", "greater_equal", "and", "or", "equal", "not_equal"]
ONE_NUM = ["negate", "abs", "round", "floor", "ceil", "sqrt", "not", "sin", "cos", "tan", "asin", "acos",
           "atan", "log", "log10", "exp", "sign", "truncate"]
ONE_ANY = ["upper", "lower", "length", "trim", "is_number", "is_text", "empty"]
TWO_TEXT = ["concat", "contains", "starts_with", "ends_with"]
PREFIX = ["", "", "", "vk_", "do_", "op_"]


def value():
    kind = rnd.random()
    if kind < 0.35:
        return rnd.choice(NUMS)
    if kind < 0.6:
        return rnd.choice(STRS)
    if kind < 0.8:
        return "$" + rnd.choice(NAMES)
    return rnd.choice(WORDS)


def name():
    return rnd.choice(NAMES + ["Bad-Name", "1x"]) if rnd.random() < 0.03 else rnd.choice(NAMES)


def line(labels):
    r = rnd.random()
    p = rnd.choice(PREFIX)
    if r < 0.14:
        return f"{p}set {name()} {value()}"
    if r < 0.2:
        return f"{p}text {name()} {value()}"
    if r < 0.4:
        return f"{p}{rnd.choice(TWO_NUM)} {name()} {value()}"
    if r < 0.5:
        return f"{p}{rnd.choice(ONE_NUM)} {name()}"
    if r < 0.58:
        return f"{p}{rnd.choice(ONE_ANY)} {name()}"
    if r < 0.67:
        return f"{p}{rnd.choice(TWO_TEXT)} {name()} {value()}"
    if r < 0.7:
        return f"{p}replace {name()} {value()} {value()}"
    if r < 0.82:
        return f"out {value()}"
    if r < 0.86:
        return f"{rnd.choice(['set', 'subtract', 'multiply', 'divide'])}_{rnd.choice([0, 1, 2, 9, 10, 99, 1000, 159860, 159861])} {name()}"
    if r < 0.9 and labels:
        return f"{rnd.choice(['if', 'unless'])} {value()} {rnd.choice(labels)}"
    if r < 0.92 and labels:
        return f"jump {rnd.choice(labels)}"
    if r < 0.94:
        return "# a comment"
    if r < 0.96:
        return ""
    if r < 0.97:
        return "halt"
    return f"out {value()}"


def program():
    labels = ["L1", "L2", "L3"]
    lines = []
    for _ in range(rnd.randint(1, 14)):
        lines.append(line(labels))
        if rnd.random() < 0.06:
            lines.append(f"label {rnd.choice(labels)}")
    return "\n".join(lines)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, timeout=30)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace").splitlines()[:1]


def main():
    failures = 0
    ran = 0
    compiled = 0
    with tempfile.TemporaryDirectory() as work:
        src, mac_bc, port_bc = (os.path.join(work, n) for n in ("p.vk", "mac.vkb", "port.vkb"))
        for index in range(COUNT):
            text = program()
            with open(src, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            mc, _, me = run([VK, "compile", src, mac_bc])
            pc, _, pe = run([PORT, "compile", src, port_bc])
            ran += 1
            if mc != pc:
                failures += 1
                print(f"COMPILE STATUS DIFFERS #{index} (mac {mc} {me}, port {pc} {pe})\n{text}\n")
                continue
            if mc != 0:
                continue
            compiled += 1
            if open(mac_bc, "rb").read() != open(port_bc, "rb").read():
                failures += 1
                print(f"BYTECODE DIFFERS #{index}\n{text}\n")
                continue
            mr, mo, mre = run([VK, "run", mac_bc])
            pr, po, pre = run([PORT, "run", mac_bc])
            if mr != pr or mo != po or (mr != 0 and mre != pre):
                failures += 1
                print(f"RUN DIFFERS #{index} (mac {mr} {mre}, port {pr} {pre})\n"
                      f"  mac out : {mo[:200]!r}\n  port out: {po[:200]!r}\n{text}\n")
    print(f"fuzz programs: {ran}  compiled: {compiled}  failures: {failures}  (seed {SEED})")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
