R = [
 ("""        (!offer_valid || m_ready) && descriptor_range_ok && descriptor_committed;""",
  """        (!offer_valid || m_ready) && descriptor_range_ok;
    // v2: descriptors pass once range-checked; the transport enforces the
    // published prefix per word (no word beyond available_end is fetched)."""),
 ("    wire descriptor_committed = descriptor_end<=available_end;\n", ""),
]
