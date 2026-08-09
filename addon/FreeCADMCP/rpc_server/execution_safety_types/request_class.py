"""Execute-code request classification enum."""

from enum import Enum


class RequestClass(Enum):
    GUI_MUTATION = "gui_mutation"
    GUI_LIGHTWEIGHT_READ = "gui_lightweight_read"
    WORKER_ANALYSIS = "worker_analysis"
    UNKNOWN = "unknown"
