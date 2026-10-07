-- Drafts are immutable versioned records; a request can have multiple revisions.
alter table public.vendor_drafts drop constraint if exists vendor_drafts_request_id_key;
alter table public.po_drafts drop constraint if exists po_drafts_request_id_key;

create unique index if not exists idx_vendor_drafts_request_version
    on public.vendor_drafts(request_id, version);
create unique index if not exists idx_po_drafts_request_version
    on public.po_drafts(request_id, version);
