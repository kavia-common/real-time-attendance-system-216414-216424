from flask.views import MethodView
from flask_smorest import Blueprint
from flask_jwt_extended import jwt_required
from flask import abort
from sqlalchemy import select, and_

from ..db import session_scope
from ..models import UserRole, Course, Session, Enrollment, Attendance, AttendanceStatus
from ..schemas import AttendanceMark, AttendanceOut
from ..security import current_user_identity, require_roles

blp = Blueprint(
    "Attendance",
    "attendance",
    url_prefix="/sessions",
    description="Attendance operations",
)


@blp.route("/<int:session_id>/attendance")
class SessionAttendance(MethodView):
    """Mark and view attendance for a session."""
    @jwt_required()
    @blp.response(200, AttendanceOut(many=True))
    def get(self, session_id: int):
        ident = current_user_identity()
        with session_scope() as db:
            session = db.get(Session, session_id)
            if not session:
                abort(404, description="Session not found")
            course = db.get(Course, session.course_id)
            if not course:
                abort(404, description="Course not found")

            # Access: teacher/admin of course or enrolled student
            allowed = False
            if ident["role"] in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
                if ident["role"] == UserRole.ADMIN.value or course.teacher_id == ident["id"]:
                    allowed = True
            else:
                enrolled = (
                    db.execute(
                        select(Enrollment).where(
                            and_(Enrollment.course_id == course.id, Enrollment.student_id == ident["id"])
                        )
                    ).scalar_one_or_none()
                    is not None
                )
                if enrolled:
                    allowed = True
            if not allowed:
                abort(403, description="Not allowed to view attendance for this session")

            rows = db.execute(select(Attendance).where(Attendance.session_id == session_id)).scalars().all()
            return [
                {
                    "id": a.id,
                    "session_id": a.session_id,
                    "student_id": a.student_id,
                    "status": a.status.value,
                    "marked_at": a.marked_at,
                }
                for a in rows
            ]

    @jwt_required()
    @require_roles(UserRole.TEACHER, UserRole.ADMIN)
    @blp.arguments(AttendanceMark, location="json")
    @blp.response(201, AttendanceOut)
    def post(self, session_id: int, payload):
        ident = current_user_identity()
        with session_scope() as db:
            session = db.get(Session, session_id)
            if not session:
                abort(404, description="Session not found")
            course = db.get(Course, session.course_id)
            if not course:
                abort(404, description="Course not found")
            if ident["role"] != UserRole.ADMIN.value and course.teacher_id != ident["id"]:
                abort(403, description="Only the course teacher can mark attendance")

            student_id = payload["student_id"]
            status = AttendanceStatus(payload["status"])
            # upsert-like: if exists, update; else create
            existing = db.execute(
                select(Attendance).where(
                    and_(Attendance.session_id == session_id, Attendance.student_id == student_id)
                )
            ).scalar_one_or_none()
            if existing:
                existing.status = status
                db.flush()
                return {
                    "id": existing.id,
                    "session_id": existing.session_id,
                    "student_id": existing.student_id,
                    "status": existing.status.value,
                    "marked_at": existing.marked_at,
                }
            a = Attendance(session_id=session_id, student_id=student_id, status=status)
            db.add(a)
            db.flush()
            return {
                "id": a.id,
                "session_id": a.session_id,
                "student_id": a.student_id,
                "status": a.status.value,
                "marked_at": a.marked_at,
            }
