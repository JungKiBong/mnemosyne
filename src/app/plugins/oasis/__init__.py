from flask import Blueprint

simulation_bp = Blueprint('simulation', __name__)

from . import simulation  # noqa: E402, F401
