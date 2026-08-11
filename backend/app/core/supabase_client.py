"""Supabase client setup (placeholder).

Provides configured clients for Postgres (data + immutable audit trail) and
Storage (uploaded documents, generated reports). The audit-trail writer exposed
here is append-only by construction — no update/delete helpers.
"""
