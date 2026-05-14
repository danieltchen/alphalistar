-- Create a new user with password authentication
CREATE USER llm_reader WITH PASSWORD 'secure_password_to_be_changed';

-- Grant CONNECT privilege on the database
GRANT CONNECT ON DATABASE postgres TO llm_reader;

-- Grant USAGE privilege on schema(s)
GRANT USAGE ON SCHEMA public TO llm_reader;

-- Grant SELECT privilege on all existing tables in the schema
GRANT SELECT ON ALL TABLES IN SCHEMA public TO llm_reader;

-- Grant SELECT privilege on future tables in the schema
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO llm_reader;