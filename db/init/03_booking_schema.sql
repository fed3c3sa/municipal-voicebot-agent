-- Appointment booking schema (single shared municipal calendar).
--
-- Overlap rule: two active appointments may not have intersecting time ranges.
-- This is enforced at the database level by an exclusion constraint over
-- tstzrange(start_at, end_at). end_at is stored as a plain column (computed by
-- the application as start_at + duration) on purpose: timestamptz + interval is
-- only STABLE, not IMMUTABLE, so it cannot live inside an index/constraint
-- expression or a generated column. Keeping end_at plain keeps the constraint
-- valid and the logic obvious.

CREATE TABLE IF NOT EXISTS booking.appointments (
    id                BIGSERIAL PRIMARY KEY,
    citizen_name      TEXT NOT NULL,
    citizen_surname   TEXT NOT NULL,
    phone             TEXT NOT NULL,
    reason            TEXT,
    start_at          TIMESTAMPTZ NOT NULL,
    end_at            TIMESTAMPTZ NOT NULL,
    duration_minutes  INT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT appointments_time_order CHECK (end_at > start_at),
    CONSTRAINT appointments_no_overlap
        EXCLUDE USING gist (tstzrange(start_at, end_at) WITH &&)
        WHERE (status = 'active')
);

-- Cancellation log. A cancelled appointment is copied here before the active
-- row is removed, so no information is lost for the (AI or human) operator.
--
-- Operational note: an AFTER INSERT trigger on this table could enqueue an
-- email asking the citizen to confirm the cancellation. The notification_required
-- flag marks rows whose email has not yet been sent. This is intentionally left
-- as a documented extension point and is not wired up here.
CREATE TABLE IF NOT EXISTS booking.cancelled_appointments (
    id                      BIGSERIAL PRIMARY KEY,
    original_appointment_id BIGINT,
    citizen_name            TEXT NOT NULL,
    citizen_surname         TEXT NOT NULL,
    phone                   TEXT NOT NULL,
    reason                  TEXT,
    start_at                TIMESTAMPTZ NOT NULL,
    end_at                  TIMESTAMPTZ NOT NULL,
    cancelled_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_by            TEXT,
    cancellation_note       TEXT,
    notification_required   BOOLEAN NOT NULL DEFAULT true
);
