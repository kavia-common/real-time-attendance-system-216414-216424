import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Date,
    Time,
    ForeignKey,
    Enum,
    UniqueConstraint,
    Index,
    Boolean,
    text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class TimestampMixin:
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=datetime.utcnow,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, index=True, default=UserRole.STUDENT)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    # relationships
    taught_courses = relationship("Course", back_populates="teacher", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
    attendance = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class Course(TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (
        Index("ix_courses_teacher_id", "teacher_id"),
        UniqueConstraint("code", name="uq_courses_code"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    code = Column(String(64), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # relationships
    teacher = relationship("User", back_populates="taught_courses")
    enrollments = relationship("Enrollment", back_populates="course", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="course", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Course id={self.id} code={self.code} name={self.name}>"


class Enrollment(TimestampMixin, Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="uq_enrollments_course_student"),
        Index("ix_enrollments_student_id", "student_id"),
        Index("ix_enrollments_course_id", "course_id"),
    )

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # relationships
    course = relationship("Course", back_populates="enrollments")
    student = relationship("User", back_populates="enrollments")


class Session(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_course_id", "course_id"),
        Index("ix_sessions_date", "session_date"),
    )

    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    session_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    topic = Column(String(255), nullable=True)

    # relationships
    course = relationship("Course", back_populates="sessions")
    attendance_records = relationship("Attendance", back_populates="session", cascade="all, delete-orphan")


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"


class Attendance(TimestampMixin, Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("session_id", "student_id", name="uq_attendance_session_student"),
        Index("ix_attendance_session_id", "session_id"),
        Index("ix_attendance_student_id", "student_id"),
    )

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.PRESENT)
    marked_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # relationships
    session = relationship("Session", back_populates="attendance_records")
    student = relationship("User", back_populates="attendance")
