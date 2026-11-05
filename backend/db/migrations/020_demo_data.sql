-- This marker is set only by the local development seed command, never by signup.
ALTER TABLE users ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT false;
