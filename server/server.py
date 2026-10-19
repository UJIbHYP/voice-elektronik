#!/usr/bin/env python3
"""Тонкая обёртка для запуска локального сервера Elektronic."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pisar import serve

if __name__ == "__main__":
    serve(model_dir="")
