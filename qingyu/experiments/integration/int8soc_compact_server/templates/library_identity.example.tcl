# Server-local reviewed identity. Do not fill this from filenames alone.
# Verify the official archive, its family member, conversion log when .lib was
# compiled to .db, resulting DB hash, actual library name and cell inventory.
set official_library_identity [dict create \
 family SCC40NLL_VHSC40_RVT_V0p1 \
 archive_path {} \
 archive_sha256 {} \
 review pending \
 files [dict create]]
# One files entry per absolute normalized .db path, with these keys:
# sha256, library_name, cell_count, archive_member, conversion_provenance.
# archive_member must reside below SCC40NLL_VHSC40_RVT_V0p1/ in S40.tar.gz.
# The trusted archive origin and conversion still require human review; a
# self-authored JSON/Tcl declaration is not cryptographic third-party approval.
