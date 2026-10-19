"""User-defined category rules: conditions on a transaction's columns -> a category.

config.py says which columns and operators exist; conditions.py checks and compiles a rule's
conditions to SQL; engine.py applies rules to stored transactions.
"""
