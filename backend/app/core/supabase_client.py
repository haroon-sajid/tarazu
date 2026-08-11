"""Supabase client setup (placeholder).

Provides configured clients for Postgres (data and the immutable audit trail)
and Storage (uploaded documents, generated reports). The audit-trail writer
exposed here is append-only by construction; it has no update or delete
helpers.
"""
