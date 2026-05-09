## base — universal fallback

For any file, regardless of type. Always runs.

- mime_type (sniffed from bytes, not from extension)
- extension (from filename)
- size (already on Blob; included here for completeness)
- content_hash (already on Blob)

## image — JPEG, PNG, WebP, GIF, HEIC, BMP, TIFF, AVIF

Already designed.

- width, height, megapixels, aspect_ratio
- format, color_mode, has_alpha, is_animated, is_grayscale
- frame_count (when animated)
- orientation
- camera_make, camera_model, datetime_original
- gps_latitude, gps_longitude

## csv — CSV, TSV, and other delimited text

Already designed.

- row_count, column_count, columns, column_types
- delimiter, quote_char, has_header
- encoding, line_terminator
- skipped_prefix_rows, empty_cells_pct

## json — JSON and JSON Lines

Two distinct shapes. Auto-detect: if the first non-whitespace char is { or [, it's a single document; if multiple top-level objects separated by newlines, it's JSONL.

- json_kind (object, array, jsonl, scalar)
- size_bytes (already on Blob)
- record_count (number of top-level items for arrays/JSONL; null for object/scalar)
- top_level_keys (for objects: the key names; null otherwise)
- top_level_key_count
- max_depth (nesting depth; useful for spotting deeply nested vs flat data)
- encoding
- is_well_formed (parsed successfully or not)
- array_item_types (for arrays: distinct types of items, e.g. ["object"] or ["object", "null"])

## pdf — PDF documents

Use pypdf or pdfminer.six.

- page_count
- is_encrypted, is_signed
- has_text (any extractable text), has_images (any embedded raster), has_forms
- pdf_version (1.4, 1.7, 2.0)
- producer (software that generated it; e.g., Microsoft Word, LibreOffice)
- creator
- title, author, subject (from PDF metadata, often empty but useful when present)
- created_at, modified_at (from PDF metadata)
- language (when set in metadata)
- page_size (e.g., A4, Letter, or dimensions)

## text — plain text, markdown, code

Generic text fallback for anything that decodes as text but isn't a structured format we recognize.

- encoding
- line_count
- word_count
- char_count
- byte_count (already on Blob, but useful here for comparison with char_count)
- line_terminator
- is_binary_safe (false if non-printable bytes detected; helps catch misidentified binary files)
- language (best-effort from langdetect or similar — only when text is long enough to be confident)

## audio — MP3, FLAC, WAV, AAC, OGG, OPUS, M4A

Use mutagen for everything.

- duration_seconds
- bitrate_kbps
- sample_rate_hz
- channels (1=mono, 2=stereo, etc.)
- codec (mp3, flac, aac, vorbis, opus)
- format (container: mp3, mp4, ogg, flac)
- is_lossless
- title, artist, album, album_artist, track_number, disc_number, genre, year (from ID3/Vorbis tags)
- has_artwork (cover art embedded)

## video — MP4, MOV, MKV, WebM, AVI

Use ffmpeg-python or pymediainfo (the latter is lighter, no ffmpeg binary required).

- duration_seconds
- width, height, aspect_ratio
- frame_rate
- frame_count (where derivable)
- video_codec (h264, hevc, vp9, av1)
- audio_codec (aac, mp3, opus; null if no audio track)
- bitrate_kbps
- format (container: mp4, mkv, webm)
- has_audio
- audio_channels
- creation_time (from container metadata)
- gps_latitude, gps_longitude (some phones embed GPS in MOV/MP4 metadata)

## Tier 2: Common-enough, slightly more work

### parquet — Apache Parquet

Use pyarrow. Read the footer only; don't load the data.

- row_count
- row_group_count
- column_count
- columns (list of column names)
- column_types (Arrow type per column)
- compression (snappy, gzip, zstd, none)
- created_by (writer library/version embedded in footer)
- has_statistics (whether row groups have min/max stats)
- total_byte_size (uncompressed size — meaningfully different from blob size)

### archive — ZIP, TAR, TAR.GZ, 7Z, RAR

Use zipfile, tarfile, py7zr, rarfile.

- format (zip, tar, 7z, rar)
- entry_count (number of files inside)
- total_uncompressed_size
- compression_ratio
- is_encrypted
- has_directories
- top_level_entries (count of root-level entries — distinguishes "many files" from "one folder containing files")
- largest_entry_name, largest_entry_size
- oldest_entry_modified, newest_entry_modified
- dominant_extension (most common file extension inside; gives a hint about the archive's purpose)

### office_doc — DOCX, DOC, ODT, RTF

Use python-docx for docx; for legacy .doc, use olefile. Could split into separate parsers but the catalog-level fields are similar.

- format (docx, doc, odt, rtf)
- page_count_estimate (docx is tricky — there's no real page count without rendering; use word count as a proxy)
- word_count
- char_count
- paragraph_count
- image_count (embedded images)
- table_count
- title, author, subject (from document metadata)
- created_at, modified_at (from metadata)
- application (creator software)
- language
- has_track_changes
- has_comments

### spreadsheet — XLSX, XLS, ODS

Use openpyxl (xlsx), xlrd (xls), odfpy (ods). Can read metadata without loading full data.

- format (xlsx, xls, ods)
- sheet_count
- sheet_names
- total_row_count (sum across sheets — rough)
- largest_sheet_rows, largest_sheet_cols
- has_formulas
- has_charts
- has_macros (genuinely security-relevant)
- created_at, modified_at, author (from metadata)
- application

### presentation — PPTX, PPT, ODP

Use python-pptx, similar approach.

- format
- slide_count
- image_count
- has_speaker_notes
- has_animations
- created_at, modified_at, author
- application
- title (from metadata)

### html — HTML files

Distinct from extraction (which is config-driven). Catalog-level only.

- title (<title> element)
- language (<html lang="">)
- meta_description (<meta name="description">)
- meta_keywords
- og_title, og_description, og_image, og_type (Open Graph tags — extremely common, very useful)
- twitter_card_type
- canonical_url
- link_count (number of <a href> elements)
- image_count (<img> elements)
- script_count
- iframe_count
- word_count (text content, scripts/styles stripped)
- has_forms
- charset
- viewport_meta (mobile-friendly indicator)

### xml — XML and SVG

SVG could be its own parser since it's actually an image, but the catalog-level info overlaps heavily with XML.

- root_element (e.g., svg, rss, feed, book)
- namespace (default xmlns)
- is_well_formed
- element_count
- max_depth
- encoding (from XML declaration)

For SVG specifically: width, height, viewbox

### markdown — Markdown files

Could fold into text but the structural extras are useful.

All text fields, plus:

- heading_count
- heading_outline (top-level headings; up to ~10)
- link_count
- image_count
- code_block_count
- code_languages (languages used in fenced code blocks)
- has_frontmatter (YAML frontmatter at the top)
- frontmatter (parsed as dict if present — small, structured, very useful for things like Hugo/Jekyll posts)
- task_list_count (- [ ] items)

## Tier 3: Specialty formats with real value for specific users

### geo — GeoJSON, KML, GPX, Shapefile

Use fiona or pyogrio for shapefiles, plain JSON for GeoJSON, gpxpy for GPX.

- format
- feature_count
- geometry_types (e.g., ["Point", "LineString"])
- bounding_box (minx, miny, maxx, maxy)
- coordinate_system (CRS / EPSG code if known)
- attribute_columns (for shapefile/GeoJSON properties)

For GPX specifically: track_count, waypoint_count, total_distance_meters, total_duration_seconds, elevation_gain_meters

### email — EML, MSG

Use email (stdlib) for EML, extract-msg for MSG.

- format
- from_address, from_name
- to_addresses (list)
- cc_addresses
- subject
- date
- has_attachments
- attachment_count
- attachment_names
- body_size_chars
- is_multipart
- is_html (HTML body present)
- has_inline_images

### ebook — EPUB, MOBI, AZW3

Use ebooklib for EPUB; MOBI/AZW3 are harder, possibly skip.

- format
- title
- author
- language
- chapter_count
- word_count_estimate
- has_cover
- publisher
- published_date
- isbn

### font — TTF, OTF, WOFF, WOFF2

Use fonttools.

- format
- family_name
- style_name (e.g., Regular, Bold Italic)
- weight (numeric: 400, 700, etc.)
- is_italic
- is_monospace
- glyph_count
- unicode_ranges (which scripts the font covers — Latin, Cyrillic, CJK, etc.)
- version
- designer
- manufacturer

### iso — Disc images: ISO, IMG, BIN

Use pycdlib.

- format
- volume_label
- total_size
- file_count
- is_bootable
- created_at

### database — SQLite, DuckDB

Read schema only, don't query data.

- format (sqlite, duckdb)
- version
- table_count
- tables (list of table names; capped)
- view_count
- index_count
- total_row_count_estimate (sum across tables — rough; from sqlite_master stats)
- has_fts (full-text search tables)

### code — .py, .js, .ts, .go, .rs, .java, etc.

Could fold into text but a few code-specific things are catalog-useful.

All text fields, plus:

- language (from extension, more reliable than guessing from content)
- loc (lines of code, excluding blanks/comments — rough)
- import_count (rough heuristic; varies by language)
- function_count (rough)
- class_count (rough)
- has_shebang
- has_main_block (e.g., if **name** == "**main**")

### notebook — Jupyter notebooks (.ipynb)

JSON internally, but distinct enough to deserve its own parser.

- cell_count
- code_cell_count
- markdown_cell_count
- kernel_name (e.g., python3)
- language (from kernelspec)
- has_outputs (any cells with output)
- total_code_lines
- total_markdown_words

## Tier 4: Probably skip unless you have a specific use case

### 3d_model — STL, OBJ, GLTF, GLB

- format
- vertex_count, face_count
- bounding_box_dimensions
- has_textures, has_animations

### cad — DWG, DXF, STEP

Limited Python tooling; would lean on commercial libs or skip.

### dicom — Medical imaging

Use pydicom. Niche but well-defined.

- modality (CT, MRI, X-ray, etc.)
- patient_age (anonymized; just the field)
- study_date
- manufacturer
- image_dimensions

### pcap — Network captures

Use scapy or dpkt.

- packet_count
- duration_seconds
- protocols_seen (TCP, UDP, etc.)
- unique_src_ips_count, unique_dst_ips_count

### executable — ELF, PE, Mach-O

Use pefile, lief.

- format
- architecture (x86_64, arm64, etc.)
- is_signed
- is_stripped
- imports_count
- target_os

### rom — Game ROMs (NES, SNES, GBA, NDS, etc.)

Niche enthusiast use case; format detection tooling exists but shallow.

### subtitle — SRT, VTT, ASS

- cue_count
- duration_seconds (last cue end time)
- language (detected from content)

## Implementation priority

If I were ordering the build, my honest read:

Sprint 1 (your common files, today): base, image, text, csv, json, pdf. These cover the vast majority of files most users will store.

Sprint 2 (media): audio, video. Significant userbases want these for personal libraries.

Sprint 3 (data and office): parquet, archive, office_doc, spreadsheet, presentation, html. The "structured documents and data" tier.

Sprint 4 (selective specialty): markdown, notebook, email, xml/svg. Common in technical/personal workflows.

Sprint 5 (specialty, on demand): the rest. Build when a user actually has the need.

A pattern that emerges as you look at this list: most parsers are 50-150 lines of Python plus a library dependency. None of them is hard individually. The only architectural concern is keeping them consistent — same interface, same kind of failure handling, same "describe the file, don't extract its content" discipline. If you nail the conventions on image and csv (which you've effectively already done), every subsequent parser is just an evening's work.

The thing to be deliberate about: each parser should declare what fields it always returns. The harness can then guarantee that meta.<kind> always has the same shape regardless of file content. Missing values are None, never absent keys. This stability matters for the UI and for SQL-like querying against the JSONB.
