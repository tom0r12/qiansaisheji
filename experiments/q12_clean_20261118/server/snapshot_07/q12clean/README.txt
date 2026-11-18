q12clean server package (no input entropy coding, no shared readcache, no loader)
Candidates: see candidates.json (each has candidate.json with local throughput).
  cd ~/Desktop && rm -rf q12clean && unzip -q q12clean.zip && cd q12clean
  nohup python3 -u run_all.py > ~/Desktop/q12clean_flow.log 2>&1 < /dev/null &
Progress: tail -5 ~/Desktop/q12clean_flow.log     Results: cat ~/Desktop/q12clean_SUMMARY.txt
Per candidate: vendor VCS 12 tasks + SAIF || DC (compile_ultra + clock gating) -> Formality + PT power windows.
