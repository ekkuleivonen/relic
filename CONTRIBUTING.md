# Contributing

Pithosys is an experimental metadata catalog. Before substantial changes, open an issue describing the problem and expected behavior. Keep fixes focused and include reproduction steps and relevant tests.

Use Go 1.26.7+, Node 24, and a dedicated PostgreSQL 17 test database. See the README for startup and checks. Database tests create and remove isolated schemas; never use a production database. Leave `TEST_DATABASE_SCHEMA` unset unless testing an explicit migration schema.

Use synthetic objects and placeholder credentials in fixtures. Never commit `.env`, database dumps, tokens, real customer metadata, or screenshots of private storage. Run dependency and secret checks before pushing.

Changes to job recovery must cover interruption and retry. Search changes should cover parsing, binding, parameterized SQL, and invalid input. Database changes need reversible migrations and upgrade tests. Frontend changes should pass lint/build and be exercised against the local demo.

The repository license and ownership review are pending. Please wait to submit third-party code until the maintainer publishes contribution terms.
