# 002. Docling for PDF-to-markdown conversion

## Status

Accepted

## Context

Imported papers arrive as PDFs. Downstream embed and analysis need markdown. Conversion failures must be classified without raising pipeline exceptions from the adapter.

## Decision

Use Docling behind the `Converter` port (`src/papers/infra/converter_docling/`). `pdf_to_markdown` returns a `ConverterResult`:

- empty or whitespace-only markdown → `EMPTY_OUTPUT`
- converter exception → `CONVERSION_FAILED`

The convert **handler** (not the adapter) rejects files that fail the `%PDF-` magic check with `CORRUPT_PDF`. Protected-PDF, converter timeout, and converter OOM codes are not claimed.

## Consequences

- Startup validation reports missing Docling as a `ConfigurationError` naming the module before adapter construction. `build_docling_converter` may still raise a lower-level install-time `PipelineError` when called without that validated startup path; neither failure is a per-job adapter raise.
- Handlers map `ConverterResult.error_code` into job failure; they do not expect `PipelineError` from `pdf_to_markdown`.
