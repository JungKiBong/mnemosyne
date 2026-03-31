from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Define the limiter instance
# Uses in-memory storage by default, can be overridden by app.config['RATELIMIT_STORAGE_URI']
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"]
)
