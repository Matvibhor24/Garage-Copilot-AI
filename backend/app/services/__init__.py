"""Service layer: the only code that touches Firestore.

Every write goes: check tenant -> write data -> write audit_log -> notify().
"""
