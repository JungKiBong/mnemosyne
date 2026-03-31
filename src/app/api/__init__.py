"""
API Routes Module
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
terminology_bp = Blueprint('terminology', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import terminology  # noqa: E402, F401
