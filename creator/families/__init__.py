"""The model families. One package per family; the pack's core imports down
into them, never the other way.

What earns a module a place under a family is that it speaks the family's
protocol — the things a checkpoint's training decided and no other family will
share. Everything a second family could reuse stays above this package.

Deliberately empty of imports: `families.h3.payload` pulls in torch, and the
suites load the pure modules without booting anything.
"""
