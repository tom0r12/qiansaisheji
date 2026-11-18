R = [
 ("""source_image[0]!==32'h31513151||source_image[1]==0||source_image[1]>76230)$fatal(1,"wrong frozen Rice source format");""",
  """source_image[0]!==32'h32583151||source_image[1]!==32'd76032)$fatal(1,"wrong fixed12 source format");"""),
 ("""if(source_image[i]==0||source_image[i]>24640)$fatal(1,"wrong Rice weight block length");""",
  """if(source_image[i]!==32'd24576)$fatal(1,"wrong fixed12 weight block length");"""),
 ('"Rice input packet length mismatch"', '"fixed12 input packet length mismatch"'),
 ("PASS real E203 Q12 GPIO no-loader cold task; original GPIOA/B pins, internal peripheral DMA, NP2 original System Bus and frozen input Rice/readcache;",
  "PASS real E203 Q12 GPIO cold task; original GPIOA/B pins, internal peripheral DMA, NP2 original System Bus, fixed12 input (no entropy coding), plain shared SRAM (no readcache);"),
]
