import json

from sqlalchemy import Index, text

from backend.core import app, db, _utcnow


class AnalysisResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, default=_utcnow)
    counts = db.Column(db.Text)
    peak_hour = db.Column(db.Integer)
    peak_count = db.Column(db.Integer)
    recommendations = db.Column(db.Text)
    analysis_name = db.Column(db.String(256))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "counts": json.loads(self.counts),
            "peak_hour": self.peak_hour,
            "peak_count": self.peak_count,
            "recommendations": json.loads(self.recommendations),
            "analysis_name": self.analysis_name,
        }


class AnalysisJob(db.Model):
    __table_args__ = (
        Index("ix_analysis_job_status", "status"),
        Index("ix_analysis_job_status_created_at", "status", "created_at"),
        Index("ix_analysis_job_completed_at", "completed_at"),
        Index("ix_analysis_job_worker_id", "worker_id"),
    )

    job_id = db.Column(db.String(32), primary_key=True)
    correlation_id = db.Column(db.String(128), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="queued")
    analysis_name = db.Column(db.String(256), nullable=True)
    input_path = db.Column(db.Text, nullable=True)
    source_kind = db.Column(db.String(32), nullable=False, default="upload")
    save_annotated = db.Column(db.Boolean, nullable=False, default=False)
    cancel_requested = db.Column(db.Boolean, nullable=False, default=False)
    progress_percent = db.Column(db.Integer, nullable=True)
    progress_message = db.Column(db.String(256), nullable=True)
    error = db.Column(db.Text, nullable=True)
    result_json = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    last_retried_at = db.Column(db.DateTime, nullable=True)
    worker_id = db.Column(db.String(128), nullable=True)
    heartbeat_at = db.Column(db.DateTime, nullable=True)
    lease_expires_at = db.Column(db.DateTime, nullable=True)
    start_dt = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)


def _ensure_analysis_job_columns():
    existing_columns = {
        row[1]
        for row in db.session.execute(text("PRAGMA table_info(analysis_job)")).fetchall()
    }
    missing_column_sql = {
        "correlation_id": "ALTER TABLE analysis_job ADD COLUMN correlation_id VARCHAR(128)",
        "retry_count": "ALTER TABLE analysis_job ADD COLUMN retry_count INTEGER DEFAULT 0 NOT NULL",
        "last_retried_at": "ALTER TABLE analysis_job ADD COLUMN last_retried_at DATETIME",
        "worker_id": "ALTER TABLE analysis_job ADD COLUMN worker_id VARCHAR(128)",
        "heartbeat_at": "ALTER TABLE analysis_job ADD COLUMN heartbeat_at DATETIME",
        "lease_expires_at": "ALTER TABLE analysis_job ADD COLUMN lease_expires_at DATETIME",
    }
    for column_name, sql in missing_column_sql.items():
        if column_name not in existing_columns:
            db.session.execute(text(sql))
    db.session.commit()


def _ensure_analysis_job_indexes():
    index_sql = [
        "CREATE INDEX IF NOT EXISTS ix_analysis_job_status ON analysis_job (status)",
        "CREATE INDEX IF NOT EXISTS ix_analysis_job_status_created_at ON analysis_job (status, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_analysis_job_completed_at ON analysis_job (completed_at)",
        "CREATE INDEX IF NOT EXISTS ix_analysis_job_worker_id ON analysis_job (worker_id)",
        "CREATE INDEX IF NOT EXISTS ix_analysis_job_correlation_id ON analysis_job (correlation_id)",
    ]
    for sql in index_sql:
        db.session.execute(text(sql))
    db.session.commit()


def initialize_database():
    db.create_all()
    _ensure_analysis_job_columns()
    _ensure_analysis_job_indexes()


with app.app_context():
    initialize_database()
