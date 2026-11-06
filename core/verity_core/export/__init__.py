"""The snapshot export (M9, ADR 0029): the only file the public demo reads.

A commit of this file to a public repository cannot be taken back, so every step fails closed:
a public field is listed and never assumed, redaction rebuilds the hashes it invalidates, and an
independent scanner has the last word. Export reads the graph only through
`GraphRepository.load_graph()`, and never an env var value.
"""
