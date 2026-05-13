## Parser toolchain plan

The parser system should not make every file type invent its own metadata schema. That creates wide JSONB, inconsistent query behavior, and too many fields that are only interesting because a library happened to expose them.

Instead, every parser should boil the file down into the same compact discovery shape. The goal is to help a user search, group, and understand a home directory or imported dump containing millions of mixed files.

## Common meta schema

Every file has exactly one metadata object on `File.meta`. Upload-time metadata and parser output must both fit this schema:

- `schema_version`: currently `1.0.0`.
- `size`: file size in bytes.
- `extension`: extension from the logical file name.
- `mimetype`: best known MIME type.
- `original_filename`: the upload-time filename.
- `tags`: controlled-vocabulary labels for filtering and grouping.
- `keywords`: capped human-searchable terms.
- `summary`: one short parser/user-provided description when available.
- `kvs`: scalar key/value facts that are useful enough to keep.

When upload-time metadata and parser output overlap, upload-time values win. Parsers may add tags, keywords, and scalar `kvs`, but they should not overwrite user-provided values.

The important fields are `tags` and `keywords`. `summary` is a compact human-readable description. `kvs` is supporting data for compact facts such as `row_count`, `column_count`, `width`, `height`, `duration_seconds`, or `page_count`. It is not an invitation to recreate per-format schemas.

## Reliability bar

Parser output must be achievable with deterministic parsing, file-format libraries, and simple heuristics. Do not depend on ML, LLMs, OCR, computer vision, speech transcription, or semantic classification.

The rule: store observed facts, not guessed meaning.

Good sources:

- Embedded metadata that the file format exposes directly.
- Visible or sampled text already present in the file.
- Filenames, extensions, MIME type, and container structure.
- Schema labels such as columns, keys, tables, sheets, layers, headings, and attachment names.
- Cheap structural measurements such as counts, dimensions, duration, and page count.

Allowed heuristics:

- Low-risk shape labels from measured facts, such as `wide`, `tall`, `short`, `long`, `large`, `small`, `hd`, `4k`, or `multi-sheet`.
- Format-family labels from file structure, such as `spreadsheet`, `archive`, `notebook`, `rss`, `svg`, `jsonl`, or `sqlite`.
- Domain hints only when the words appear in observed labels or sampled text. For example, add `budget` only if a sheet, heading, filename, or sampled text says budget.

Do not infer:

- Image contents such as `cat`, `person`, `landscape`, `receipt`, or `screenshot` from pixels.
- Audio contents such as music, podcast, audiobook, or voice unless tags or filenames say so.
- Video contents such as movie, screen recording, meeting, or phone clip unless metadata or filenames say so.
- Document type or topic such as contract, report, invoice, or manual unless title, headings, filename, or sampled text says so.
- Dataset domain such as customers, orders, budget, or inventory unless schema labels say so.

## Output discipline

`tags` should be normalized and low-cardinality. They are for queries like "show me all spreadsheets", "show encrypted archives", "show long videos", or "show scanned PDFs".

Examples:

- `image`
- `photo`
- `screenshot`
- `document`
- `dataset`
- `spreadsheet`
- `archive`
- `code`
- `ebook`
- `encrypted`
- `signed`
- `has-text`
- `has-images`
- `has-attachments`
- `has-macros`
- `small`
- `large`
- `short`
- `long`

`keywords` should be user-facing search terms. They may be higher-cardinality than tags, but they must still be capped, normalized, deduplicated, and worth searching.

Good keyword sources:

- Human labels: titles, artists, albums, authors, subjects, publishers, ISBNs.
- Web labels: page title, meta description, Open Graph title/description, canonical host.
- Data labels: column names, top-level JSON keys, table names, sheet names, schema names.
- Domain terms: codec names, camera make/model, programming language, coordinate system, font family.
- Filename-derived words when embedded metadata is sparse.

Weak keyword sources:

- Library names and generator strings.
- Exact byte sizes and hashes.
- Internal parser diagnostics.
- Long unbounded lists copied wholesale.
- Low-level formatting details such as quote char, line terminator, XML encoding, or PDF version.

`kvs` should stay very small. It exists for scalar facts, range queries, and compact UI summaries, not detailed inspection. Prefer generic numeric names that work across toolchains where possible, such as:

- `item_count`
- `width`
- `height`
- `duration_seconds`
- `page_count`
- `row_count`
- `column_count`
- `word_count`

If a number is mostly a derived convenience, do not store it. The UI can compute things like aspect ratio, megapixels, compression ratio, or minutes from the persisted basics.

## Caps and normalization

Use the same limits everywhere so the storage cost is predictable.

- `tags`: target 3-12 values.
- `keywords`: target 10-50 values.
- `summary`: target one short sentence when useful.
- List-derived keywords: cap each source before merging, then dedupe globally.
- Normalize case, trim whitespace, collapse repeated punctuation, and drop empty values.
- Prefer singular canonical tags: `image`, not both `image` and `images`.
- Keep exact identifiers when they are useful search handles: ISBNs, album names, artist names, package names, domains.
- Do not duplicate facts outside the schema. Keep content hash and storage path on Blob, not in `meta`.

## base - universal fallback

Always runs for any file. It should seed the common output with baseline tags and filename-derived keywords.

How it gets there:

- Sniff MIME type from bytes and update `mimetype` only when upload-time metadata did not already provide one.
- Add broad tags from MIME family and extension, such as `image`, `text`, `archive`, `audio`, or `video`.
- Extract useful words from the filename and extension into `keywords`.
- Leave Blob-only facts on Blob. Do not copy hash or storage path into file meta.

## image - JPEG, PNG, WebP, GIF, HEIC, BMP, TIFF, AVIF

Images should describe what kind of visual asset the dump contains, not expose a full EXIF database.

How it gets there:

- Inspect dimensions and format to add tags such as `image`, `animated`, `transparent`, `grayscale`, `large`, or `small`.
- Add `photo`, `screenshot`, `icon`, or `wallpaper` only when supported by filename/path terms, metadata, or simple format/dimension conventions. Do not infer visual contents from pixels.
- Use EXIF camera make/model, when present, as keywords because users may search for files from a camera or phone model.
- Use date/location metadata only as keyword material if the product intentionally supports time/place grouping.
- Put width and height in `kvs` because they support meaningful range queries.
- Summarize the asset in broad terms, for example "animated transparent webp image" or "large jpeg photo".

## csv - CSV, TSV, and other delimited text

Delimited files should look like datasets in the search system.

How it gets there:

- Sniff delimiter/header/encoding enough to parse safely.
- Add tags such as `data`, `table`, `csv`, `tsv`, `dataset`, `wide`, `tall`, or `empty`.
- Promote column names and recognizable column labels into keywords.
- Add domain hints from explicit column labels, such as `email`, `date`, `price`, `latitude`, `longitude`, or `id`.
- Do not infer broader dataset meaning unless schema labels contain those words.
- Put row and column counts in `kvs`.
- Summarize the shape, for example "CSV table with 12 columns and customer/order-like fields".

## json - JSON and JSON Lines

JSON should be treated as structured data with searchable schema hints.

How it gets there:

- Detect document shape: object, array, JSONL, scalar, malformed.
- Add tags such as `json`, `data`, `config`, `api`, `records`, `jsonl`, `array`, `object`, or `malformed`.
- Promote top-level keys, repeated object keys, and recognizable schema labels into keywords.
- Use filenames, keys, and known file signatures to add domain hints such as `package`, `lockfile`, `notebook`, `geo`, `config`, or `export`.
- Keep those domain hints tied to explicit filenames, keys, or known file signatures.
- Put record count in `kvs` when there is a record-like structure.
- Summarize the shape, for example "JSONL records with user/event-like keys".

## pdf - PDF documents

PDFs should become searchable documents, with enough tags to separate scans, forms, manuals, and signed/encrypted files.

How it gets there:

- Read structural flags and lightweight metadata without full content extraction.
- Add tags such as `pdf`, `document`, `has-text`, `scanned`, `has-images`, `form`, `signed`, `encrypted`, `short`, or `long`.
- Use title, author, subject, embedded language, and first-page text snippets as keyword sources.
- Treat `scanned` as a narrow structural heuristic: no extractable text plus embedded page images. Do not classify document topic without observed text.
- Include producer/creator only if they are meaningful user-facing terms, not generic generator noise.
- Put page count in `kvs`.
- Summarize whether it looks like a text PDF, scanned PDF, form, long manual, or protected document.

## text - plain text and unknown readable files

Text fallback should produce basic search terms and coarse content tags.

How it gets there:

- Decode safely and sample enough text to classify the file.
- Add tags such as `text`, `plain-text`, `notes`, `log`, `config`, `readme`, `license`, `short`, or `long`.
- Extract keywords from headings, repeated terms, key-value labels, and filename words.
- Add role tags like `log`, `config`, `readme`, or `license` only from filename conventions or obvious textual markers.
- Detect language only when confidence is high and add it as a keyword or tag.
- Put line count and word count in `kvs`.
- Summarize the apparent role, for example "short plain text note" or "large log-like text file".

## audio - MP3, FLAC, WAV, AAC, OGG, OPUS, M4A

Audio should make music and spoken-word collections easy to group.

How it gets there:

- Use mutagen to read technical format and common tags.
- Add tags such as `audio`, `music`, `podcast`, `audiobook`, `voice`, `lossless`, `compressed`, `mono`, `stereo`, `short`, or `long`.
- Promote title, artist, album, album artist, genre, year, track number, and disc number into keywords.
- Add `music`, `podcast`, `audiobook`, or `voice` only when embedded tags, genre, album/title, or filename terms support it.
- Use codec/container and lossless/lossy status as tags or keywords.
- Put duration in `kvs`.
- Summarize the observed media labels, for example "flac audio tagged as music by Radiohead" or "long audio file with spoken-word filename terms".

## video - MP4, MOV, MKV, WebM, AVI

Video should be searchable as media, screen recordings, phone clips, movies, or long-form content.

How it gets there:

- Read container and stream metadata with pymediainfo or ffmpeg tooling.
- Add tags such as `video`, `movie`, `clip`, `screen-recording`, `phone-video`, `has-audio`, `silent`, `short`, `long`, `hd`, `4k`, or `vertical`.
- Promote title, creation app, camera model, codec, and container terms when they help search.
- Add semantic media tags like `movie`, `screen-recording`, or `phone-video` only from metadata, filename terms, or deterministic capture/app signatures.
- Put duration, width, and height in `kvs`.
- Summarize the media shape, for example "short vertical phone video with audio" or "long 1080p video".

## parquet - Apache Parquet

Parquet should be represented as a dataset with schema-derived keywords.

How it gets there:

- Read only the footer.
- Add tags such as `data`, `dataset`, `parquet`, `table`, `columnar`, `wide`, `tall`, or `partitioned` if derivable.
- Promote capped column names and explicit type/domain labels into keywords.
- Domain hints must come from column names or paths, not inferred from data values.
- Use compression and row group shape only when they help summarize the dataset.
- Put row and column counts in `kvs`.
- Summarize the table shape, for example "large parquet dataset with event/user-like columns".

## archive - ZIP, TAR, TAR.GZ, 7Z, RAR

Archives should reveal what kind of bundle was ingested without indexing every member path as metadata.

How it gets there:

- Inspect entries without extracting content.
- Add tags such as `archive`, `compressed`, `encrypted`, `bundle`, `backup`, `source-code`, `photos`, `documents`, `single-folder`, or `many-files`.
- Promote dominant extensions, top-level folder names, and a small capped sample of meaningful entry names into keywords.
- Infer bundle type from extension distribution, such as code project, photo set, document pack, or backup.
- Keep bundle type labels shallow and deterministic; they should come from extension distribution, top-level names, or explicit filenames.
- Put entry count and uncompressed size in `kvs` if not already represented on Blob.
- Summarize the contents, for example "zip archive containing mostly images" or "tarball containing source code".

## office_doc - DOCX, DOC, ODT, RTF

Word-processing documents should behave like searchable human documents.

How it gets there:

- Read document properties and lightweight structure.
- Add tags such as `document`, `word-document`, `report`, `letter`, `contract`, `has-images`, `has-tables`, `has-comments`, or `tracked-changes`.
- Promote title, author, subject, headings, and strong document labels into keywords.
- Add type/topic tags like `report`, `letter`, or `contract` only when those terms appear in filename, title, subject, headings, or sampled text.
- Put word count or approximate page count in `kvs`.
- Summarize the document shape, for example "word document with tables and comments".

## spreadsheet - XLSX, XLS, ODS

Spreadsheets should be searchable as workbooks, datasets, budgets, inventories, or analysis files.

How it gets there:

- Read workbook metadata and sheet dimensions without loading all cells.
- Add tags such as `spreadsheet`, `workbook`, `data`, `budget`, `inventory`, `has-formulas`, `has-charts`, `has-macros`, `wide`, or `multi-sheet`.
- Promote sheet names, header labels, workbook title, author, and obvious domain terms into keywords, capped aggressively.
- Add domain tags like `budget` or `inventory` only when sheet names, headers, title, filename, or sampled cells say so.
- Put sheet count, row count, and column count in `kvs`.
- Summarize the workbook, for example "multi-sheet spreadsheet with formulas and finance-like labels".

## presentation - PPTX, PPT, ODP

Presentations should surface observed deck labels and broad structure.

How it gets there:

- Read slide structure and document properties.
- Add tags such as `presentation`, `slides`, `deck`, `has-images`, `has-notes`, `animated`, `short`, or `long`.
- Promote title, author, slide titles, and repeated heading terms into keywords.
- Do not infer deck topic beyond observed titles/headings/text.
- Put slide count in `kvs`.
- Summarize the deck, for example "slide deck with speaker notes and product/roadmap terms".

## html - HTML files

HTML should support web-page search and grouping without storing a full DOM inventory.

How it gets there:

- Parse title, language, meta description, Open Graph data, canonical URL, and visible text sample.
- Add tags such as `html`, `webpage`, `article`, `landing-page`, `form`, `script-heavy`, `has-images`, or `external-links`.
- Promote page title, meta description terms, Open Graph title/description, canonical domain, headings, and visible text terms into keywords.
- Add page-type tags like `article` or `landing-page` only from explicit structured metadata, known HTML markers, or URL/title terms.
- Put link/image/script counts in `kvs` only if they help grouping.
- Summarize the page, for example "HTML article about cats" or "script-heavy landing page".

## xml - XML and SVG

XML should expose document family and schema hints. SVG should also look like an image.

How it gets there:

- Parse safely enough to identify root element, namespace family, and rough structure.
- Add tags such as `xml`, `svg`, `feed`, `rss`, `config`, `manifest`, `vector-image`, or `malformed`.
- Promote root element, namespace family, schema hints, and important attribute names into keywords.
- For SVG, include visual tags such as `image`, `icon`, `illustration`, or `vector`.
- Put element count or SVG dimensions in `kvs` only when useful.
- Summarize the document family, for example "RSS feed XML" or "SVG vector image".

## markdown - Markdown files

Markdown should behave like human-authored text with extra structural hints.

How it gets there:

- Parse headings, frontmatter, links, images, task lists, and fenced code blocks.
- Add tags such as `markdown`, `document`, `notes`, `readme`, `documentation`, `blog-post`, `has-frontmatter`, `has-tasks`, or `has-code`.
- Promote title, headings, selected frontmatter labels, link text, and code fence languages into keywords.
- Add role tags like `readme`, `documentation`, or `blog-post` only from filename, frontmatter, title, or headings.
- Put word count and heading count in `kvs`.
- Summarize the file, for example "markdown documentation with code examples" or "task-list note".

## geo - GeoJSON, KML, GPX, Shapefile

Geo files should make spatial datasets searchable without storing a full spatial index in metadata.

How it gets there:

- Read schema and geometry summary, not full feature contents.
- Add tags such as `geo`, `map`, `spatial-data`, `track`, `route`, `points`, `polygons`, or `gps`.
- Promote layer names, property column names, coordinate system, geometry types, and filename terms into keywords.
- Put feature count and basic bounds in `kvs` only if the UI will use them.
- Summarize the file, for example "GeoJSON point dataset" or "GPX track with waypoints".

## email - EML, MSG

Email should expose conversation/search labels and attachment structure.

How it gets there:

- Parse headers, body type, and attachment headers without deeply parsing every attachment.
- Add tags such as `email`, `message`, `has-attachments`, `html-email`, `plain-email`, `multipart`, or `newsletter`.
- Promote sender name/address, recipients, subject, attachment names, and salient body terms into keywords, capped aggressively.
- Put attachment count and body size in `kvs`.
- Summarize the message, for example "email from Acme with 2 attachments".

## ebook - EPUB, MOBI, AZW3

Ebooks should be searchable as books and grouped by bibliographic labels.

How it gets there:

- Read package metadata and table of contents.
- Add tags such as `ebook`, `book`, `epub`, `mobi`, `fiction`, `nonfiction`, `has-cover`, `short`, or `long`.
- Promote title, author, publisher, language, ISBN, subject/category, and chapter titles into keywords.
- Add `fiction` or `nonfiction` only from explicit subject/category metadata.
- Put chapter count and estimated word count in `kvs`.
- Summarize the book, for example "EPUB ebook by Ursula K. Le Guin".

## font - TTF, OTF, WOFF, WOFF2

Fonts should be searchable by family, style, and broad script support.

How it gets there:

- Read name tables and basic glyph coverage.
- Add tags such as `font`, `typeface`, `serif`, `sans-serif`, `monospace`, `italic`, `bold`, `webfont`, or script tags like `latin`, `cjk`, `cyrillic`.
- Promote family name, style name, foundry/designer if meaningful, and script names into keywords.
- Put glyph count in `kvs`.
- Summarize the face, for example "bold italic webfont with Latin coverage".

## iso - Disc images: ISO, IMG, BIN

Disc images should be searchable as install media, backups, or bootable images.

How it gets there:

- Read volume descriptors and directory summary without mounting.
- Add tags such as `disk-image`, `iso`, `bootable`, `installer`, `backup`, or `media`.
- Promote volume label, boot labels, top-level names, and dominant extensions into keywords.
- Put file count in `kvs`.
- Summarize the image, for example "bootable ISO installer image".

## database - SQLite, DuckDB

Databases should reveal schema/domain shape without querying user data.

How it gets there:

- Read schema catalog only.
- Add tags such as `database`, `sqlite`, `duckdb`, `relational`, `has-fts`, `many-tables`, or `small-db`.
- Promote table names, view names, index names, and column labels into keywords, capped by source.
- Add domain hints from schema labels, such as `contacts`, `messages`, `browser-history`, `analytics`, or `cache`.
- Put table, view, index, and estimated row counts in `kvs`.
- Summarize the database, for example "SQLite database with message/contact-like tables".

## code - .py, .js, .ts, .go, .rs, .java, etc.

Code files should be searchable by language, project role, and recognizable package/framework terms.

How it gets there:

- Detect language primarily from extension, with content fallback where needed.
- Add tags such as `code`, language tag, `test`, `config`, `script`, `component`, `server`, `client`, or `generated`.
- Promote package/import names, framework names, class/function names, shebang command, and filename terms into keywords, capped and language-aware.
- Put line count and rough symbol counts in `kvs` if cheap.
- Summarize the code role, for example "Python test file using pytest" or "React TypeScript component".

## notebook - Jupyter notebooks

Notebooks should be searchable as mixed code/document artifacts.

How it gets there:

- Parse notebook JSON and cell types.
- Add tags such as `notebook`, `jupyter`, `python`, `analysis`, `has-outputs`, `code`, `markdown`, or `tutorial`.
- Promote notebook title/headings, kernel language, imported packages, markdown headings, and output MIME hints into keywords.
- Put cell counts and code/markdown size in `kvs`.
- Summarize the notebook, for example "Python notebook with outputs and data-analysis terms".

## 3d_model - STL, OBJ, GLTF, GLB

3D models should be searchable as assets with coarse complexity and feature tags.

How it gets there:

- Read mesh/container metadata without rendering.
- Add tags such as `3d-model`, `mesh`, `asset`, `textured`, `animated`, `simple`, or `complex`.
- Promote object names, material names, collection names, and filename terms into keywords.
- Put vertex/face counts in `kvs` if cheap.
- Summarize the asset, for example "textured GLB model" or "simple STL mesh".

## cad - DWG, DXF, STEP

CAD should stay on-demand unless there is a clear user need.

How it gets there:

- If implemented, read drawing/model headers and layer/object summaries.
- Add tags such as `cad`, `drawing`, `model`, `engineering`, `layers`, or `technical`.
- Promote layer names, part names, drawing titles, and filename terms into keywords.
- Put object/layer counts in `kvs` if available.
- Summarize the file at a high level.

## dicom - Medical imaging

DICOM is niche but well-defined. It should support grouping medical imaging files without deep clinical interpretation.

How it gets there:

- Read safe header fields only.
- Add tags such as `dicom`, `medical`, `image`, `ct`, `mri`, `xray`, or modality-specific tags.
- Promote modality, study description, series description, body part, and manufacturer into keywords.
- Put image dimensions or series counts in `kvs` if relevant.
- Summarize the image/study family, for example "DICOM MRI image".

## pcap - Network captures

Packet captures should reveal traffic shape without indexing packet contents.

How it gets there:

- Sample or scan packet headers.
- Add tags such as `pcap`, `network-capture`, `tcp`, `udp`, `dns`, `http`, `tls`, `short`, or `long`.
- Promote protocols, ports, hostnames when available, and capture labels into keywords.
- Put packet count and duration in `kvs`.
- Summarize the capture, for example "short packet capture with DNS and TCP traffic".

## executable - ELF, PE, Mach-O

Executables should be searchable by platform, architecture, signing, and broad binary behavior.

How it gets there:

- Read binary headers and import tables.
- Add tags such as `executable`, `binary`, `elf`, `pe`, `mach-o`, `signed`, `stripped`, `library`, `cli`, or target OS tags.
- Promote architecture, target OS, imported library names, product/version labels, and filename terms into keywords.
- Put import count or section count in `kvs` if useful.
- Summarize the binary, for example "signed macOS arm64 executable".

## rom - Game ROMs

ROM support should be shallow and on-demand.

How it gets there:

- Detect console family and read header title where tooling supports it.
- Add tags such as `rom`, `game`, console tag, `cartridge`, or `handheld`.
- Promote game title, region, console, and filename terms into keywords.
- Summarize the ROM, for example "Game Boy Advance ROM".

## subtitle - SRT, VTT, ASS

Subtitles should be searchable as timed text, usually attached to media collections.

How it gets there:

- Parse cues and sample subtitle text.
- Add tags such as `subtitle`, `captions`, `timed-text`, `srt`, `vtt`, `ass`, `short`, or `long`.
- Promote detected language, repeated names/terms, and filename terms into keywords.
- Put cue count and duration in `kvs`.
- Summarize the file, for example "English SRT subtitles with 900 cues".

## Implementation priority

Sprint 1: base, image, text, csv, json, pdf.

Sprint 2: audio, video.

Sprint 3: parquet, archive, office_doc, spreadsheet, presentation, html.

Sprint 4: markdown, notebook, email, xml/svg.

Sprint 5: specialty metadata extractors on demand.

The important architectural concern is consistency. Every parser should use the same output builder, the same tag vocabulary, the same keyword caps, and the same failure behavior. A parser should describe what the file appears to be and what terms help a user find it later. It should not preserve every fact the underlying library can expose.
