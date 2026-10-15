-- Applied only by the verified project bootstrap connection, never the application.
DO $roles$
DECLARE n text;
BEGIN
 FOREACH n IN ARRAY ARRAY['ai_owner','ai_policy_executor','ai_web','ai_index','ai_meter'] LOOP
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=n) THEN
   EXECUTE format('CREATE ROLE %I NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE NOREPLICATION',n);
  END IF;
 END LOOP;
END;
$roles$;
ALTER ROLE ai_owner NOLOGIN;
ALTER ROLE ai_policy_executor NOLOGIN;
ALTER ROLE ai_web LOGIN;
ALTER ROLE ai_index LOGIN;
ALTER ROLE ai_meter LOGIN;
