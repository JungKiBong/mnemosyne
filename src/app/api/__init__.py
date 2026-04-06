"""
API Routes Module
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
terminology_bp = Blueprint('terminology', __name__)

from . import graph  # noqa: E402, F401
from . import terminology  # noqa: E402, F401
