"""S3-shaped gateway operations.

Public mutation entry point: ``object_mutations`` (UnitOfWork + cache invalidation).
Session-level verb modules (``object_writes``, ``object_reads``, …) are internal
primitives — prefer ``object_mutations`` from routes and workers.
"""
