from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.models import (
    Assignment,
    AssignmentCompletion,
    COMPLETION_COMPLETED,
    COMPLETION_LABELS,
    Provider,
)

foamfrat_bp = Blueprint("foamfrat", __name__, url_prefix="/foamfrat")


def _parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@foamfrat_bp.route("/")
@login_required
def index():
    assignments = Assignment.query.order_by(Assignment.assigned_date.desc().nullslast()).all()
    return render_template("foamfrat_index.html", assignments=assignments)


@foamfrat_bp.route("/assignments/new", methods=["POST"])
@login_required
def assignment_new():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Give the assignment a name.", "danger")
        return redirect(url_for("foamfrat.index"))

    assignment = Assignment(
        name=name,
        description=request.form.get("description", "").strip() or None,
        assigned_date=_parse_date(request.form.get("assigned_date")),
        due_date=_parse_date(request.form.get("due_date")),
    )
    db.session.add(assignment)
    db.session.flush()

    active_providers = Provider.query.filter_by(active=True).all()
    for provider in active_providers:
        db.session.add(AssignmentCompletion(provider_id=provider.id, assignment_id=assignment.id))
    db.session.commit()

    flash(
        f"Created '{assignment.name}' and assigned it to {len(active_providers)} active provider(s).",
        "success",
    )
    return redirect(url_for("foamfrat.assignment_detail", assignment_id=assignment.id))


@foamfrat_bp.route("/assignments/<int:assignment_id>")
@login_required
def assignment_detail(assignment_id):
    assignment = db.get_or_404(Assignment, assignment_id)
    completions = sorted(
        assignment.completions, key=lambda c: (c.provider.last_name, c.provider.first_name)
    )
    completed, total = assignment.progress()
    return render_template(
        "foamfrat_assignment.html",
        assignment=assignment,
        completions=completions,
        completed=completed,
        total=total,
        completion_labels=COMPLETION_LABELS,
    )


@foamfrat_bp.route("/completions/<int:completion_id>/edit", methods=["POST"])
@login_required
def completion_edit(completion_id):
    completion = db.get_or_404(AssignmentCompletion, completion_id)
    completion.status = request.form.get("status", completion.status)
    completion.completed_date = _parse_date(request.form.get("completed_date"))
    completion.notes = request.form.get("notes", "").strip() or None
    if completion.status == COMPLETION_COMPLETED and not completion.completed_date:
        from datetime import date
        completion.completed_date = date.today()
    db.session.commit()
    return redirect(url_for("foamfrat.assignment_detail", assignment_id=completion.assignment_id))


@foamfrat_bp.route("/completions/<int:completion_id>/remove", methods=["POST"])
@login_required
def completion_remove(completion_id):
    completion = db.get_or_404(AssignmentCompletion, completion_id)
    assignment_id = completion.assignment_id
    name = completion.provider.full_name
    db.session.delete(completion)
    db.session.commit()
    flash(f"Removed {name} from this assignment.", "success")
    return redirect(url_for("foamfrat.assignment_detail", assignment_id=assignment_id))


@foamfrat_bp.route("/assignments/<int:assignment_id>/delete", methods=["POST"])
@login_required
def assignment_delete(assignment_id):
    assignment = db.get_or_404(Assignment, assignment_id)
    name = assignment.name
    db.session.delete(assignment)
    db.session.commit()
    flash(f"Deleted assignment '{name}'.", "success")
    return redirect(url_for("foamfrat.index"))
