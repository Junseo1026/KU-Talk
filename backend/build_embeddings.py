"""Wrapper script to build embeddings for parsed posts.

Usage:
  python build_embeddings.py [batch_size]

This script loads OPENAI_API_KEY from backend/.env if present in the shell.
"""
import sys
import os

def main():
    bs = 10
    if len(sys.argv) > 1:
        try:
            bs = int(sys.argv[1])
        except Exception:
            pass
    # ensure backend package imports work
    sys.path.insert(0, os.path.dirname(__file__))
    from embeddings import build_embeddings, load_embeddings
    print('Building embeddings with batch_size=', bs)
    build_embeddings(batch_size=bs)
    em = load_embeddings()
    print('Done. embeddings count =', len(em))

if __name__ == '__main__':
    main()

