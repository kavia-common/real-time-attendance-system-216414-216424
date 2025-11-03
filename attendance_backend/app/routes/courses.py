from flask.views import MethodView
from flask_smorest import Blueprint
from flask_jwt_extended import jwt_required
from flask import abort
from sqlalchemy import select, and_

from ..db import session_scope
from ..models import UserRole, Course, Enrollment, Session
from ..schemas import CourseOut, SessionOut, SessionCreate
from ..security import current_user_identity, require_roles

blp = Blueprint(
    "Courses",
    "courses",
    url_prefix="/courses",
    description="Course and Session management",
)


@blp.route("")
class CourseList(MethodView):
    """List courses available to the current user."""
    @jwt_required()
    @blp.response(200, CourseOut(many=True))
    def get(self):
        ident = current_user_identity()
        with session_scope() as db:
            if ident["role"] == UserRole.TEACHER.value or ident["role"] == UserRole.ADMIN.value:
                # teacher/admin: courses they teach (admin sees all)
                if ident["role"] == UserRole.ADMIN.value:
                    rows = db.execute(select(Course)).scalars().all()
                else:
                    rows = db.execute(select(Course).where(Course.teacher_id == ident["id"])).scalars().all()
            else:
                # student: courses they're enrolled in
                rows = (
                    db.execute(
                        select(Course)
                        .join(Enrollment, Enrollment.course_id == Course.id)
                        .where(Enrollment.student_id == ident["id"])
                    )
                    .scalars()
                    .all()
                )
            return [
                {"id": c.id, "name": c.name, "code": c.code, "teacher_id": c.teacher_id}
                for c in rows
            ]


@blp.route("/<int:course_id>/sessions")
class CourseSessions(MethodView):
    """List or create sessions for a course."""
    @jwt_required()
    @blp.response(200, SessionOut(many=True))
    def get(self, course_id: int):
        ident = current_user_identity()
        with session_scope() as db:
            course = db.get(Course, course_id)
            if not course:
                abort(404, description="Course not found")

            # Access control: teacher/admin or enrolled student
            allowed = False
            if ident["role"] in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
                if ident["role"] == UserRole.ADMIN.value or course.teacher_id == ident["id"]:
                    allowed = True
            else:
                enrolled = (
                    db.execute(
                        select(Enrollment).where(
                            and_(Enrollment.course_id == course_id, Enrollment.student_id == ident["id"])
                        )
                    ).scalar_one_or_none()
                    is not None
                )
                if enrolled:
                    allowed = True
            if not allowed:
                abort(403, description="Not allowed to view sessions for this course")

            sessions = db.execute(select(Session).where(Session.course_id == course_id).order_by(Session.session_date.desc())).scalars().all()
            return [
                {
                    "id": s.id,
                    "course_id": s.course_id,
                    "session_date": s.session_date,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "topic": s.topic,
                }
                for s in sessions
            ]

    @jwt_required()
    @require_roles(UserRole.TEACHER, UserRole.ADMIN)
    @blp.arguments(SessionCreate, location="json")
    @blp.response(201, SessionOut)
    def post(self, course_id: int, payload):
        ident = current_user_identity()
        with session_scope() as db:
            course = db.get(Course, course_id)
            if not course:
                abort(404, description="Course not found")
            # Only teacher of the course or admin can create sessions
            if ident["role"] != UserRole.ADMIN.value and course.teacher_id != ident["id"]:
                abort(403, description="Only the course teacher can create sessions")

            s = Session(
                course_id=course_id,
                session_date=payload["session_date"],
                start_time=payload.get("start_time"),
                end_time=payload.get("end_time"),
                topic=payload.get("topic"),
            )
            db.add(s)
            db.flush()  # get s.id
            return {
                "id": s.id,
                "course_id": s.course_id,
                "session_date": s.session_date,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "topic": s.topic,
            }
