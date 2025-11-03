from datetime import timedelta
from flask.views import MethodView
from flask_smorest import Blueprint
from flask_jwt_extended import jwt_required
from flask import abort
from sqlalchemy import select, func, and_

from ..db import session_scope
from ..models import UserRole, Course, Session, Attendance, AttendanceStatus, Enrollment
from ..schemas import ReportFilter, DailyReportOut, WeeklyReportOut
from ..security import current_user_identity

blp = Blueprint(
    "Reports",
    "reports",
    url_prefix="/reports",
    description="Attendance reports",
)


@blp.route("/daily")
class DailyReport(MethodView):
    """Daily report: aggregated attendance by date."""
    @jwt_required()
    @blp.arguments(ReportFilter, location="query")
    @blp.response(200, DailyReportOut(many=True))
    def get(self, q):
        ident = current_user_identity()
        start_date = q["start_date"]
        end_date = q["end_date"]
        course_id = q.get("course_id")
        student_id = q.get("student_id")

        with session_scope() as db:
            # Access control
            if course_id:
                course = db.get(Course, course_id)
                if not course:
                    abort(404, description="Course not found")
                if ident["role"] not in [UserRole.ADMIN.value] and not (
                    ident["role"] == UserRole.TEACHER.value and course.teacher_id == ident["id"]
                ):
                    # if student, ensure enrolled
                    if ident["role"] == UserRole.STUDENT.value:
                        enrolled = db.execute(
                            select(Enrollment).where(
                                and_(Enrollment.course_id == course_id, Enrollment.student_id == ident["id"])
                            )
                        ).scalar_one_or_none()
                        if not enrolled:
                            abort(403, description="Not allowed to view this course report")
                    else:
                        abort(403, description="Not allowed to view this course report")

            # Build query
            join_stmt = (
                select(
                    Session.session_date.label("date"),
                    func.sum(func.case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)).label("present"),
                    func.sum(func.case((Attendance.status == AttendanceStatus.ABSENT, 1), else_=0)).label("absent"),
                    func.sum(func.case((Attendance.status == AttendanceStatus.LATE, 1), else_=0)).label("late"),
                    func.count(Attendance.id).label("total"),
                )
                .join(Attendance, Attendance.session_id == Session.id, isouter=True)
                .where(and_(Session.session_date >= start_date, Session.session_date <= end_date))
                .group_by(Session.session_date)
                .order_by(Session.session_date.asc())
            )

            if course_id:
                join_stmt = join_stmt.where(Session.course_id == course_id)
            if student_id:
                join_stmt = join_stmt.where(Attendance.student_id == student_id)

            rows = db.execute(join_stmt).all()
            return [
                {
                    "date": r.date,
                    "present": int(r.present or 0),
                    "absent": int(r.absent or 0),
                    "late": int(r.late or 0),
                    "total": int(r.total or 0),
                }
                for r in rows
            ]


@blp.route("/weekly")
class WeeklyReport(MethodView):
    """Weekly report: aggregates per week in the range [start_date, end_date]."""
    @jwt_required()
    @blp.arguments(ReportFilter, location="query")
    @blp.response(200, WeeklyReportOut(many=True))
    def get(self, q):
        ident = current_user_identity()
        start_date = q["start_date"]
        end_date = q["end_date"]
        course_id = q.get("course_id")
        student_id = q.get("student_id")

        with session_scope() as db:
            # Access control similar to daily
            if course_id:
                course = db.get(Course, course_id)
                if not course:
                    abort(404, description="Course not found")
                if ident["role"] not in [UserRole.ADMIN.value] and not (
                    ident["role"] == UserRole.TEACHER.value and course.teacher_id == ident["id"]
                ):
                    if ident["role"] == UserRole.STUDENT.value:
                        enrolled = db.execute(
                            select(Enrollment).where(
                                and_(Enrollment.course_id == course_id, Enrollment.student_id == ident["id"])
                            )
                        ).scalar_one_or_none()
                        if not enrolled:
                            abort(403, description="Not allowed to view this course report")
                    else:
                        abort(403, description="Not allowed to view this course report")

            # Compute Monday as week_start
            # Using SQL: week_start = session_date - extract(dow) + 1 (assuming Monday)
            # For portability, aggregate by date_trunc('week', ...)
            # For Postgres this groups Monday-Sunday when setlocale; use date_trunc('week', timestamp)
            join_stmt = (
                select(
                    (func.date_trunc("week", func.cast(Session.session_date, type_=func.timestamp()))).label("week"),
                    func.sum(func.case((Attendance.status == AttendanceStatus.PRESENT, 1), else_=0)).label("present"),
                    func.sum(func.case((Attendance.status == AttendanceStatus.ABSENT, 1), else_=0)).label("absent"),
                    func.sum(func.case((Attendance.status == AttendanceStatus.LATE, 1), else_=0)).label("late"),
                    func.count(Attendance.id).label("total"),
                )
                .join(Attendance, Attendance.session_id == Session.id, isouter=True)
                .where(and_(Session.session_date >= start_date, Session.session_date <= end_date))
                .group_by("week")
                .order_by("week")
            )
            if course_id:
                join_stmt = join_stmt.where(Session.course_id == course_id)
            if student_id:
                join_stmt = join_stmt.where(Attendance.student_id == student_id)

            rows = db.execute(join_stmt).all()
            # Convert week (timestamp) to week_start/week_end dates
            out = []
            for r in rows:
                week_start = r.week.date()
                week_end = week_start + timedelta(days=6)
                out.append(
                    {
                        "week_start": week_start,
                        "week_end": week_end,
                        "present": int(r.present or 0),
                        "absent": int(r.absent or 0),
                        "late": int(r.late or 0),
                        "total": int(r.total or 0),
                    }
                )
            return out
