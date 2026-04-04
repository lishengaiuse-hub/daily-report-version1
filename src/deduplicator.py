#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Multi-Layer Deduplication Module for Samsung CE Intelligence
Implements URL hash, title similarity, and semantic embedding deduplication
"""

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import json

# Add numpy import - FIX THE ERROR
import numpy as np

# Optional imports with fallbacks
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    from difflib import SequenceMatcher
    RAPIDFUZZ_AVAILABLE = False
    print("⚠️ rapidfuzz not available, falling back to difflib")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    print("⚠️ sentence-transformers not available, semantic dedup disabled")
