from marshmallow import Schema, fields, validate, EXCLUDE
from .models import UserRole, AttendanceStatus


class BaseSchema(Schema):
    class Meta:
        unknown = EXCLUDE


# User schemas
class UserOut(BaseSchema):
    id = fields.Int(required=True, description="User ID")
    email = fields.Email(required=True, description="Email")
    name = fields.Str(required=True, description="Full name")
    role = fields.Str(required=True, validate=validate.OneOf([r.value for r in UserRole]), description="Role")


class LoginInput(BaseSchema):
    email = fields.Email(required=True, description="Email")
    password = fields.Str(required=True, load_only=True, description="Password")


class LoginOutput(BaseSchema):
    access_token = fields.Str(required=True, description="JWT access token")
    token_type = fields.Str(required=True, dump_default="bearer")


# Course schemas
class CourseCreate(BaseSchema):
    name = fields.Str(required=True)
    code = fields.Str(required=True)


class CourseOut(BaseSchema):
    id = fields.Int(required=True)
    name = fields.Str(required=True)
    code = fields.Str(required=True)
    teacher_id = fields.Int(required=True)


# Session schemas
class SessionCreate(BaseSchema):
    session_date = fields.Date(required=True)
    start_time = fields.Time(required=False, allow_none=True)
    end_time = fields.Time(required=False, allow_none=True)
    topic = fields.Str(required=False, allow_none=True)


class SessionOut(BaseSchema):
    id = fields.Int(required=True)
    course_id = fields.Int(required=True)
    session_date = fields.Date(required=True)
    start_time = fields.Time(required=False, allow_none=True)
    end_time = fields.Time(required=False, allow_none=True)
    topic = fields.Str(required=False, allow_none=True)


# Attendance schemas
class AttendanceMark(BaseSchema):
    student_id = fields.Int(required=True, description="Student ID")
    status = fields.Str(
        required=True,
        validate=validate.OneOf([s.value for s in AttendanceStatus]),
        description="present/absent/late",
    )


class AttendanceOut(BaseSchema):
    id = fields.Int(required=True)
    session_id = fields.Int(required=True)
    student_id = fields.Int(required=True)
    status = fields.Str(required=True)
    marked_at = fields.DateTime(required=True)


# Reports schemas
class ReportFilter(BaseSchema):
    start_date = fields.Date(required=True, description="Start date inclusive")
    end_date = fields.Date(required=True, description="End date inclusive")
    course_id = fields.Int(required=False)
    student_id = fields.Int(required=False)


class DailyReportOut(BaseSchema):
    date = fields.Date(required=True)
    present = fields.Int(required=True)
    absent = fields.Int(required=True)
    late = fields.Int(required=True)
    total = fields.Int(required=True)


class WeeklyReportOut(BaseSchema):
    week_start = fields.Date(required=True)
    week_end = fields.Date(required=True)
    present = fields.Int(required=True)
    absent = fields.Int(required=True)
    late = fields.Int(required=True)
    total = fields.Int(required=True)
