import pandas as pd
from os.path import join as oj
import analyze_utils

save_dir = '/home/chansingh/mntv1/iprompt_revision_xmas/'
# save_dir = '/home/chansingh/mntv1/iprompt_revision_reranked/'
print('aggregating...')
r = analyze_utils.load_results_and_cache_autoprompt_json(
    save_dir, save_file='r.pkl', one_row_only=True)
print('Done aggregating!')