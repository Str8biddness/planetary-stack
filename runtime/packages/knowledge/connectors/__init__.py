"""Synthesus expansion-drive connectors — pull a user's external sources
(GitHub, cloud storage) and feed them into the local grounding index.

Every connector's job is the same: fetch the user's files from source X, then
hand them to the RAG ingestion pipeline. Fetch is from the user's own source;
embedding + indexing stay LOCAL (private).
"""
