from datetime import date

from app.models import STATUS_CRITICAL, STATUS_EXPIRED, STATUS_WARNING

STATUS_CSS = {
    STATUS_EXPIRED: "status-expired",
    STATUS_CRITICAL: "status-critical",
    STATUS_WARNING: "status-warning",
    "current": "status-current",
}


def register_template_helpers(app):
    @app.context_processor
    def inject_globals():
        return {"today": date.today(), "status_css": STATUS_CSS}
