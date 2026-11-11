# Future MCP integration points

Phase 4 prepares the code review business layer for MCP without implementing protocol transport.

Potential tools in a later phase:
- `analyze_code`: call `CodeReviewService.analyze_code` with the same source, authorization, limits, analyzer status, and finding validation rules as REST.
- `get_review`: call owner-scoped `CodeReviewService.get_review` and return review metadata/status.
- `list_findings`: call owner-scoped `CodeReviewService.list_findings` with severity/category filters.
- `generate_patch`: call `CodeReviewService.generate_patch` to produce a preview only; an MCP caller must still invoke a separate explicit approval action before updating the uploaded-source snapshot.

The future MCP transport must authenticate users, preserve tenant/project scoping, apply source and output limits, and never expose arbitrary filesystem access. It must not call analyzers through a shell or execute submitted programs. The current API and service remain the only completed interfaces; no MCP server/client or MCP tools are claimed as implemented.
